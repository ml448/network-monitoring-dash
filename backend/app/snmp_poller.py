"""
Real SNMP Poller - Replacement for the mock poller with actual SNMP queries using pysnmp.
"""
import asyncio
import logging
import time
from datetime import datetime
from typing import Dict, Any, Optional, List
from threading import Thread
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(env_path)

from pysnmp.hlapi.v3arch.asyncio import (
    get_cmd,
    next_cmd,
    SnmpEngine,
    CommunityData,
    UdpTransportTarget,
    ContextData,
    ObjectType,
    ObjectIdentity,
)

from .snmp_oids import SYSTEM, HOST_RESOURCES, INTERFACES
from .snmp_helpers import convert_snmp_value, format_uptime
from .influx_client import InfluxClient
from .demo_devices import get_demo

logger = logging.getLogger("RealSNMPPoller")
logging.basicConfig(level=logging.INFO)


class RealSNMPPoller:

    def __init__(
        self,
        influx_client: Optional[InfluxClient] = None,
        community: str = os.getenv("SNMP_COMMUNITY"),
        timeout: int = int(os.getenv("SNMP_TIMEOUT")),
        retries: int = int(os.getenv("SNMP_RETRIES")),
        poll_interval: int = int(os.getenv("SNMP_POLL_INTERVAL")),
    ):
        self.influx_client = influx_client
        self.community = community
        self.timeout = timeout
        self.retries = retries
        self.poll_interval = poll_interval

        # Device data storage
        self.device_data: Dict[str, Dict[str, Any]] = {}

        # Bandwidth tracking: stores previous counter values for delta calculation
        self.previous_counters: Dict[str, Dict[str, Any]] = {}

        # Threading for background polling
        self.running = False
        self.thread: Optional[Thread] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None

        logger.info(
            f"SNMP Poller initialized"
        )

    def start(self):
        """Start the background polling thread."""
        if self.running:
            logger.warning("Poller already running")
            return

        self.running = True
        self.thread = Thread(target=self._run_async_loop, daemon=True)
        self.thread.start()
        logger.info(" SNMP Poller started")

    def stop(self):
        """Stop the polling thread gracefully."""
        self.running = False
        if self.loop and self.loop.is_running():
            # Schedule graceful shutdown
            self.loop.call_soon_threadsafe(self._shutdown_loop)
        if self.thread:
            self.thread.join(timeout=10)
        logger.info(" SNMP Poller stopped")

    def _shutdown_loop(self):
        # Get all tasks except the current one
        pending_tasks = [task for task in asyncio.all_tasks(self.loop)
                         if not task.done()]

        # Cancel all pending tasks
        for task in pending_tasks:
            task.cancel()

        # Schedule the actual loop stop after giving tasks time to cancel
        self.loop.call_later(0.1, self.loop.stop)

    def _run_async_loop(self):
        """Run the async event loop in a background thread."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._poll_loop())

    async def _poll_loop(self):
        """Main polling loop - runs asynchronously."""
        while self.running:
            try:
                await self._poll_all_devices()
                await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                # Task cancelled during shutdown
                logger.debug("Polling loop cancelled during shutdown")
                break
            except Exception as e:
                logger.error(f"Error in polling loop: {e}")
                await asyncio.sleep(5)

    async def _poll_all_devices(self):
        """Poll all configured devices concurrently."""
        devices = get_demo()  # TODO: Replace with database query

        # Poll all devices concurrently using asyncio.gather
        tasks = [self._poll_device(device) for device in devices]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _poll_device(self, device: Dict[str, Any]):
        """Poll a single device for SNMP data."""
        dev_ip = device["ip"]
        dev_name = device.get("name", dev_ip)

        try:
            # Measure response time
            start_time = time.time()

            # Query basic SNMP data
            snmp_data = await self._snmp_get_multi(
                dev_ip,
                {
                    "sysDescr": SYSTEM["sysDescr"],
                    "sysUpTime": SYSTEM["sysUpTime"],
                    "sysName": SYSTEM["sysName"],
                    "sysLocation": SYSTEM["sysLocation"],
                },
            )

            response_time = round((time.time() - start_time) * 1000, 2)  # ms

            # Query additional metrics (CPU, memory, bandwidth)
            snmp_data["cpu_usage"] = await self._get_cpu_usage(dev_ip)
            snmp_data["mem_usage"] = await self._get_memory_usage(dev_ip)
            bandwidth = await self._get_bandwidth(dev_ip)
            snmp_data["bandwidth_in"] = bandwidth["bandwidth_in"]
            snmp_data["bandwidth_out"] = bandwidth["bandwidth_out"]

            # Implement status determination logic
            status = self._determine_status(snmp_data, response_time)

            # Extract metrics from SNMP data
            metrics = self._build_metrics(snmp_data, response_time)

            # Build device update
            device_update = {
                **device,
                "status": status,
                "metrics": metrics,
                "last_polled": datetime.now().isoformat(),
            }

            # Store in memory
            self.device_data[dev_ip] = device_update

            # Write to InfluxDB
            if self.influx_client:
                self.influx_client.write_metrics(device_update)

            logger.debug(f"Polled {dev_name} ({dev_ip}): {status} in {response_time}ms")

        except Exception as e:
            logger.error(f"Error polling {dev_name} ({dev_ip}): {e}")
            self.device_data[dev_ip] = {
                **device,
                "status": "Error",
                "metrics": {},
                "last_polled": datetime.now().isoformat(),
                "error": str(e),
            }

    async def _snmp_get_multi(
        self, ip: str, oids: Dict[str, str], port: int = 161
    ) -> Dict[str, Any]:
        """
        Query multiple OIDs from a device.

        Args:
            ip: Device IP address
            oids: Dictionary of {name: oid_string}
            port: SNMP port (default 161)

        Returns:
            Dictionary of {name: converted_value}
        """
        try:
            # Create transport target
            transport = await UdpTransportTarget.create(
                (ip, port), timeout=self.timeout, retries=self.retries
            )

            # Build OID objects
            oid_objects = [ObjectType(ObjectIdentity(oid)) for oid in oids.values()]

            # Perform SNMP GET with explicit timeout
            try:
                error_indication, error_status, error_index, var_binds = await asyncio.wait_for(
                    get_cmd(
                        SnmpEngine(),
                        CommunityData(self.community),
                        transport,
                        ContextData(),
                        *oid_objects,
                    ),
                    timeout=self.timeout * (self.retries + 1)  # Total timeout
                )
            except asyncio.TimeoutError:
                return {}

            # Handle errors
            if error_indication:
                raise Exception(f"SNMP error: {error_indication}")
            if error_status:
                raise Exception(f"SNMP error: {error_status.prettyPrint()}")

            # Convert results
            results = {}
            oid_names = list(oids.keys())
            for i, (oid, value) in enumerate(var_binds):
                name = oid_names[i] if i < len(oid_names) else f"unknown_{i}"
                results[name] = convert_snmp_value(value)

            return results

        except Exception as e:
            logger.debug(f"SNMP GET failed for {ip}: {e}")
            return {}

    async def _snmp_walk(
        self, ip: str, base_oid: str, port: int = 161
    ) -> List[tuple]:
        #SNMP WALK operation - iterate through OID tree starting at base_oid
        results = []
        try:
            transport = await UdpTransportTarget.create(
                (ip, port), timeout=self.timeout, retries=self.retries
            )

            # Use next_cmd to iterate through OID tree
            current_oid = ObjectIdentity(base_oid)
            max_iterations = 100  # Safety limit

            for _ in range(max_iterations):
                try:
                    error_indication, error_status, error_index, var_binds = await asyncio.wait_for(
                        next_cmd(
                            SnmpEngine(),
                            CommunityData(self.community),
                            transport,
                            ContextData(),
                            ObjectType(current_oid),
                        ),
                        timeout=self.timeout * (self.retries + 1)
                    )
                except asyncio.TimeoutError:
                    break

                if error_indication or error_status:
                    break

                for oid, value in var_binds:
                    oid_str = str(oid)
                    # Stop if we've left the base OID subtree
                    if not oid_str.startswith(base_oid):
                        return results

                    results.append((oid_str, convert_snmp_value(value)))
                    current_oid = oid

        except Exception as e:
            logger.debug(f"SNMP WALK failed for {ip} at {base_oid}: {e}")

        return results

    async def _get_cpu_usage(self, ip: str) -> float:
        """
        Query CPU usage from HOST-RESOURCES-MIB hrProcessorLoad table.

        Walks OID 1.3.6.1.2.1.25.3.3.1.2 to get all processor loads,
        then calculates the average CPU percentage across all cores.

        Returns:
            Average CPU percentage (0-100), or 0.0 if unsupported/error
        """
        try:
            # Walk hrProcessorLoad table
            cpu_loads = await self._snmp_walk(ip, HOST_RESOURCES["hrProcessorLoad"])

            if not cpu_loads:
                return 0.0

            # Calculate average across all processors
            total = sum(value for _, value in cpu_loads if isinstance(value, (int, float)))
            avg_cpu = total / len(cpu_loads) if cpu_loads else 0.0

            return round(avg_cpu, 2)

        except Exception as e:
            logger.debug(f"Failed to get CPU usage for {ip}: {e}")
            return 0.0

    async def _get_memory_usage(self, ip: str) -> float:
        """
        Query memory usage from HOST-RESOURCES-MIB hrStorage tables.

        Walks hrStorageDescr to find RAM entries, then queries allocation units,
        size, and used blocks to calculate percentage.

        Returns:
            Memory usage percentage (0-100), or 0.0 if unsupported/error
        """
        try:
            # Walk storage descriptions to find RAM
            storage_descrs = await self._snmp_walk(ip, HOST_RESOURCES["hrStorageDescr"])

            if not storage_descrs:
                return 0.0

            # Find RAM indices (look for "Physical Memory", "RAM", "Real Memory")
            ram_indices = []
            for oid_str, descr in storage_descrs:
                if isinstance(descr, str):
                    descr_lower = descr.lower()
                    if any(term in descr_lower for term in ["physical memory", "ram", "real memory"]):
                        # Extract index from OID (last number)
                        idx = oid_str.split(".")[-1]
                        ram_indices.append(idx)

            if not ram_indices:
                return 0.0

            # Query size and used for first RAM entry found
            idx = ram_indices[0]
            storage_data = await self._snmp_get_multi(
                ip,
                {
                    "allocationUnits": f"{HOST_RESOURCES['hrStorageAllocationUnits']}.{idx}",
                    "size": f"{HOST_RESOURCES['hrStorageSize']}.{idx}",
                    "used": f"{HOST_RESOURCES['hrStorageUsed']}.{idx}",
                },
            )

            if not storage_data:
                return 0.0

            alloc_units = storage_data.get("allocationUnits", 0)
            total_blocks = storage_data.get("size", 0)
            used_blocks = storage_data.get("used", 0)

            if total_blocks == 0 or alloc_units == 0:
                return 0.0

            # Calculate percentage: (used * units) / (total * units) * 100
            mem_percent = (used_blocks / total_blocks) * 100
            return round(mem_percent, 2)

        except Exception as e:
            logger.debug(f"Failed to get memory usage for {ip}: {e}")
            return 0.0

    async def _get_bandwidth(self, ip: str, if_index: int = 1) -> Dict[str, float]:
        """
        Calculate bandwidth rate for specified interface.

        Queries ifInOctets and ifOutOctets, compares with previous poll,
        and calculates bytes/sec converted to Mbps.

        Args:
            ip: Device IP address
            if_index: Interface index (default 1)

        Returns:
            Dict with bandwidth_in and bandwidth_out in Mbps
        """
        try:
            current_time = time.time()

            # Query current interface counters
            counters = await self._snmp_get_multi(
                ip,
                {
                    "ifInOctets": f"{INTERFACES['ifInOctets']}.{if_index}",
                    "ifOutOctets": f"{INTERFACES['ifOutOctets']}.{if_index}",
                },
            )

            if not counters:
                return {"bandwidth_in": 0.0, "bandwidth_out": 0.0}

            in_octets = counters.get("ifInOctets", 0)
            out_octets = counters.get("ifOutOctets", 0)

            # Get previous counters for this device
            prev = self.previous_counters.get(ip)

            # Store current counters for next poll
            self.previous_counters[ip] = {
                "timestamp": current_time,
                "ifInOctets": in_octets,
                "ifOutOctets": out_octets,
            }

            # First poll - no previous data to compare
            if not prev:
                return {"bandwidth_in": 0.0, "bandwidth_out": 0.0}

            # Calculate time delta
            time_delta = current_time - prev["timestamp"]
            if time_delta <= 0:
                return {"bandwidth_in": 0.0, "bandwidth_out": 0.0}

            # Calculate byte deltas (handle 32-bit counter wraparound)
            MAX_COUNTER = 2**32

            in_delta = in_octets - prev["ifInOctets"]
            if in_delta < 0:
                in_delta += MAX_COUNTER  # Counter wrapped

            out_delta = out_octets - prev["ifOutOctets"]
            if out_delta < 0:
                out_delta += MAX_COUNTER  # Counter wrapped

            # Convert to Mbps: (bytes/sec) * 8 / 1,000,000
            bandwidth_in = (in_delta / time_delta) * 8 / 1_000_000
            bandwidth_out = (out_delta / time_delta) * 8 / 1_000_000

            return {
                "bandwidth_in": round(bandwidth_in, 3),
                "bandwidth_out": round(bandwidth_out, 3),
            }

        except Exception as e:
            logger.debug(f"Failed to get bandwidth for {ip}: {e}")
            return {"bandwidth_in": 0.0, "bandwidth_out": 0.0}

    # Device status
    def _determine_status(self, snmp_data: Dict[str, Any], response_time: float) -> str:

        # Set Thresholds
        UPTIME_WARNING = 5000
        REBOOT_THRESHOLD_MINUTES = 10 

        # No sysDescr means basic SNMP query failed - device is offline
        if "sysDescr" not in snmp_data:
            return "Offline"
        
        # Slow response time indicates a warning
        if response_time > UPTIME_WARNING:
            return "Warning"
        
        #Check for reboot
        sys_uptime = snmp_data.get('sysUpTime', None)
        if sys_uptime is not None:
            uptime_minutes = sys_uptime / 60
            #Convert TimeTicks into minutes
            if uptime_minutes < REBOOT_THRESHOLD_MINUTES:
                return "Warning"
    
        return "Online"




    def _build_metrics(
        self, snmp_data: Dict[str, Any], response_time: float
    ) -> Dict[str, Any]:

        metrics = {
            "response_time": response_time,
            "cpu_usage": snmp_data.get("cpu_usage", 0),
            "mem_usage": snmp_data.get("mem_usage", 0),
            "bandwidth_in": snmp_data.get("bandwidth_in", 0),
            "bandwidth_out": snmp_data.get("bandwidth_out", 0),
        }

        # Extract uptime if available
        uptime = snmp_data.get("sysUpTime")
        if uptime is not None:
            metrics["uptime"] = uptime

        return metrics


    def device_status(self, dev_ip: str) -> str:
        """Get current status for a device."""
        return self.device_data.get(dev_ip, {}).get("status", "unknown")

    def get_last_update(self, dev_ip: str) -> Optional[str]:
        """Get timestamp of last poll for a device."""
        return self.device_data.get(dev_ip, {}).get("last_polled")

    def get_metrics(self, dev_ip: str) -> Dict[str, Any]:
        """Get current metrics for a device."""
        return self.device_data.get(dev_ip, {}).get("metrics", {})

    def get_all_devices(self) -> Dict[str, Dict[str, Any]]:
        """Get all device data."""
        return self.device_data