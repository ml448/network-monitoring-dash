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
from .alert_manager import AlertManager

logger = logging.getLogger(__name__)

DEVICE_COMMUNITIES = {
    "Core-Router-01": "core-router-01",
    "Core-Switch-01": "core-switch-01",
    "Dist-Firewall-Primary": "dist-firewall-primary",
    "Dist-Firewall-Secondary": "dist-firewall-secondary",
    "Dist-Switch-01": "dist-switch-01",
    "Dist-Switch-02": "dist-switch-02",
    "Access-Switch-Floor1": "access-switch-floor1",
    "Access-Switch-Floor2": "access-switch-floor2",
    "Access-Switch-Floor3": "access-switch-floor3",
    "AP-Floor1": "ap-floor1",
    "AP-Floor2": "ap-floor2",
    "AP-Floor3": "ap-floor3",
    "Server-Web-01": "server-web-01",
    "Server-DB-01": "server-db-01",
    "Server-Auth-01": "server-auth-01",
}

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
        self.alert_manager = AlertManager(influx_client=influx_client)

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
        # Start the background polling thread
        if self.running:
            logger.warning("Poller already running")
            return

        self.running = True
        self.thread = Thread(target=self._run_async_loop, daemon=True)
        self.thread.start()
        logger.info("✓ SNMP Poller started")

    def stop(self):
        # Stop the polling thread gracefully
        self.running = False
        if self.loop and self.loop.is_running():
            # Schedule graceful shutdown
            self.loop.call_soon_threadsafe(self._shutdown_loop)
        if self.thread:
            self.thread.join(timeout=10)
        logger.info("✓ SNMP Poller stopped")

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
        # Run the async event loop in a background thread
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._poll_loop())

    async def _poll_loop(self):
        # Main polling loop - runs asynchronously
        while self.running:
            try:
                await self._poll_all_devices()
                await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in polling loop: {e}")
                await asyncio.sleep(5)

    async def _poll_all_devices(self):
        # Poll all configured devices concurrently
        devices = get_demo()

        # Poll all devices concurrently using asyncio.gather
        tasks = [self._poll_device(device) for device in devices]
        await asyncio.gather(*tasks, return_exceptions=True)

    def _parse_ip_port(self, ip_string: str) -> tuple[str, int]:
        # Parse IP:port format, returns (ip, port). Defaults to port 161
        if ":" in ip_string:
            ip, port_str = ip_string.rsplit(":", 1)
            try:
                return ip, int(port_str)
            except ValueError:
                return ip_string, 161
        return ip_string, 161

    async def _poll_device(self, device: Dict[str, Any]):
        # Poll a single device for SNMP data
        dev_ip_raw = device["ip"]
        dev_ip, dev_port = self._parse_ip_port(dev_ip_raw)
        dev_name = device.get("name", dev_ip_raw)
        dev_community = DEVICE_COMMUNITIES.get(dev_name, self.community)

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
                port=dev_port,
                community=dev_community,
            )

            response_time = round((time.time() - start_time) * 1000, 2)  # ms

            # Query additional metrics (CPU, memory, bandwidth)
            snmp_data["cpu_usage"] = await self._get_cpu_usage(dev_ip, port=dev_port, community=dev_community)
            snmp_data["mem_usage"] = await self._get_memory_usage(dev_ip, port=dev_port, community=dev_community)
            bandwidth = await self._get_bandwidth(dev_ip, port=dev_port, community=dev_community)
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
            self.device_data[dev_ip_raw] = device_update

            # Write to InfluxDB
            if self.influx_client:
                self.influx_client.write_metrics(device_update)

            await self.alert_manager.process_device(device_update)

        except Exception as e:
            logger.error(f"Error polling {dev_name} ({dev_ip_raw}): {e}")
            self.device_data[dev_ip_raw] = {
                **device,
                "status": "Error",
                "metrics": {},
                "last_polled": datetime.now().isoformat(),
                "error": str(e),
            }

    # Query multiple OIDs from a device
    async def _snmp_get_multi(
        self, ip: str, oids: Dict[str, str], port: int = 161, community: str = None
    ) -> Dict[str, Any]:
        try:
            comm_str = community if community is not None else self.community
            
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
                        CommunityData(comm_str), 
                        transport,
                        ContextData(),
                        *oid_objects,
                    ),
                    timeout=self.timeout * (self.retries + 1)  # Total timeout
                )
            except asyncio.TimeoutError:
                #Return dictionary of {name: converted_value}
                return {}

            # Handle errors
            if error_indication:
                raise Exception(f"SNMP error: {error_indication}")
            if error_status:
                raise Exception(f"SNMP error: {error_status.prettyPrint()}")

            # Convert results by matching by OID string, not position
            results = {}
            # Reverse lookup
            oid_to_name = {v: k for k, v in oids.items()}

            for oid, value in var_binds:
                oid_str = str(oid)
                value_str = str(value)

                # Skip SNMP error responses (noSuchObject, noSuchInstance, endOfMibView)
                if 'noSuch' in value_str or 'endOfMib' in value_str:
                    continue

                # Find matching name by comparing OID strings
                name = oid_to_name.get(oid_str)
                if name is None:
                    # Try matching with/without leading dot
                    oid_normalized = oid_str.lstrip('.')
                    for req_oid, req_name in oid_to_name.items():
                        req_normalized = req_oid.lstrip('.')
                        if oid_normalized == req_normalized:
                            name = req_name
                            break

                if name:
                    results[name] = convert_snmp_value(value)

            return results

        except Exception:
            return {}

    async def _snmp_walk(
        self, ip: str, base_oid: str, port: int = 161, community: str = None
    ) -> List[tuple]:
        #SNMP WALK operation - iterate through OID tree starting at base_oid
        results = []
        try:
            comm_str = community if community is not None else self.community

            transport = await UdpTransportTarget.create(
                (ip, port), timeout=self.timeout, retries=self.retries
            )

            # Use next_cmd to iterate through OID tree
            current_oid = ObjectIdentity(base_oid)
            max_iterations = 100

            for iteration in range(max_iterations):
                try:
                    error_indication, error_status, error_index, var_binds = await asyncio.wait_for(
                        next_cmd(
                            SnmpEngine(),
                            CommunityData(comm_str),
                            transport,
                            ContextData(),
                            ObjectType(current_oid),
                        ),
                        timeout=self.timeout * (self.retries + 1)
                    )
                except asyncio.TimeoutError:
                    break

                if error_indication:
                    break
                if error_status:
                    break

                for oid, value in var_binds:
                    oid_str = str(oid)
                    # Stop if we've left the base OID subtree
                    if not oid_str.startswith(base_oid):
                        return results

                    results.append((oid_str, convert_snmp_value(value)))
                    current_oid = oid

        except Exception:
            pass

        return results

    async def _get_cpu_usage(self, ip: str, port: int = 161, community: str = None) -> float:
        try:
            # Query hrProcessorLoad for CPU indices 1-8
            cpu_base = HOST_RESOURCES["hrProcessorLoad"]
            cpu_oids = {f"cpu_{i}": f"{cpu_base}.{i}" for i in range(1, 9)}

            cpu_data = await self._snmp_get_multi(
                ip,
                cpu_oids,
                port=port,
                community=community,
            )

            # Filter valid numeric CPU values
            cpu_values = [v for v in cpu_data.values() if isinstance(v, (int, float)) and v >= 0]

            if not cpu_values:
                return 0.0

            # Calculate average across all processors
            avg_cpu = sum(cpu_values) / len(cpu_values)
            return round(avg_cpu, 2)

        except Exception:
            return 0.0
        
    async def _get_memory_usage(self, ip: str, port: int = 161, community: str = None) -> float:
        try:
            # Direct query for memory at index 1 (bypass walk issues with simulator)
            idx = "1"
        
            storage_data = await self._snmp_get_multi(
                ip,
                {
                    "allocationUnits": f"1.3.6.1.2.1.25.2.3.1.4.{idx}",
                    "size": f"1.3.6.1.2.1.25.2.3.1.5.{idx}",
                    "used": f"1.3.6.1.2.1.25.2.3.1.6.{idx}",
                },
                port=port,
                community=community,
            )
        
            if not storage_data:
                return 0.0

            alloc_units = storage_data.get("allocationUnits", 0)
            total_blocks = storage_data.get("size", 0)
            used_blocks = storage_data.get("used", 0)

            if total_blocks == 0:
                return 0.0

            mem_percent = (used_blocks / total_blocks) * 100
            return round(mem_percent, 2)

        except Exception:
            return 0.0

    # Calculate bandwidth rate for specified interface
    async def _get_bandwidth(self, ip: str, if_index: int = 1, port: int = 161, community: str = None) -> Dict[str, float]:
        try:
            current_time = time.time()

            #ip:port format as device key
            device_key = f"{ip}:{port}"

            # Query current interface counters
            counters = await self._snmp_get_multi(
                ip,
                {
                    "ifInOctets": f"{INTERFACES['ifInOctets']}.{if_index}",
                    "ifOutOctets": f"{INTERFACES['ifOutOctets']}.{if_index}",
                },
                port=port,
                community=community,
            )

            if not counters:
                return {"bandwidth_in": 0.0, "bandwidth_out": 0.0}
            
            in_octets = counters.get("ifInOctets", 0)
            out_octets = counters.get("ifOutOctets", 0)

            # Get previous counters for this device
            prev = self.previous_counters.get(device_key)

            # Store current counters for next poll
            self.previous_counters[device_key] = {
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
            
            # Returns: Dict with bandwidth_in and bandwidth_out in Mbps
            return {
                "bandwidth_in": round(bandwidth_in, 2),
                "bandwidth_out": round(bandwidth_out, 2),
            }

        except Exception:
            return {"bandwidth_in": 0.0, "bandwidth_out": 0.0}

    # Device status
    def _determine_status(self, snmp_data: Dict[str, Any], response_time: float) -> str:

        # Set Thresholds
        UPTIME_WARNING = 5000
        REBOOT_THRESHOLD_MINUTES = 10 

        # Check if we got ANY valid SNMP response - device is responding
        # sysDescr is preferred but cpu_usage/mem_usage/sysUpTime also indicate the device is online
        has_valid_response = (
            "sysDescr" in snmp_data or
            "sysUpTime" in snmp_data or
            "cpu_usage" in snmp_data or
            "mem_usage" in snmp_data
        )
        if not has_valid_response:
            return "Offline"
        
        # Slow response time indicates a warning
        if response_time > UPTIME_WARNING:
            return "Warning"
        
        #Check for reboot
        sys_uptime = snmp_data.get('sysUpTime', None)
        if sys_uptime is not None:
            # Ensure numeric type before division
            if isinstance(sys_uptime, str):
                try:
                    sys_uptime = int(sys_uptime)
                except ValueError:
                    sys_uptime = None
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
        # Get current status for a device
        return self.device_data.get(dev_ip, {}).get("status", "unknown")

    def get_last_update(self, dev_ip: str) -> Optional[str]:
        # Get timestamp of last poll for a device
        return self.device_data.get(dev_ip, {}).get("last_polled")

    def get_metrics(self, dev_ip: str) -> Dict[str, Any]:
        # Get current metrics for a device
        return self.device_data.get(dev_ip, {}).get("metrics", {})

    def get_all_devices(self) -> Dict[str, Dict[str, Any]]:
        # Get all device data
        return self.device_data