import threading
import time
import random
from datetime import datetime
from .demo_devices import get_demo
from .influx_client import InfluxClient
import logging
from typing import Dict, Any

logger = logging.getLogger(" SNMPPoller")
logging.basicConfig(level=logging.INFO)

class SNMPPoller:
    #Simulating SNMP polling of network devices
    def __init__(self, influx_client: InfluxClient = None):
        self.running = False
        self.thread = None
        self.device_data: Dict[str, Dict[str, Any]] = {}
        self.influx_client = influx_client
        logger.info("Mock Poller initialized")

    def start(self):
        if self.running:
            logger.warning(" Poller already running")
            return
        self.running = True
        self.thread = threading.Thread(target=self._poll_loop, daemon=True)
        self.thread.start()
        logger.info(" SNMP Poller started")

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info(" SNMP Poller stopped")

    def _poll_loop(self):
        while self.running:
            try:
                self._poll_devices()
                time.sleep(10)
            except Exception as e:
                logger.error(f"Error in polling loop: {e}")
                time.sleep(5)

    def _poll_devices(self):
        devices = get_demo()
        for device in devices:
            try:
                dev_ip = device["ip"]
                metrics = self.mock_metrics(device)
                timestamp = datetime.now().isoformat()

                device_update = {
                    **device,
                    "status": metrics.get("status", "unknown"),
                    "metrics": {
                        "cpu_usage": metrics.get("cpu_usage", 0),
                        "mem_usage": metrics.get("mem_usage", 0),
                        "bandwidth_in": metrics.get("bandwidth_in", 0),
                        "bandwidth_out": metrics.get("bandwidth_out", 0),
                        "uptime": metrics.get("uptime", 0),
                        "response_time": metrics.get("response_time", 0)
                    },
                    "last_polled": timestamp
                }
                
                self.device_data[dev_ip] = device_update

                # Write to InfluxDB
                if self.influx_client:
                    self.influx_client.write_metrics(device_update)


            except Exception as e:
                dev_ip = device.get("ip", "unknown")
                logger.error(f"Error polling device {dev_ip}:{e}")
                self.device_data[dev_ip] = {
                    **device,
                    "status": "error",
                    "metrics": {},
                    "last_polled": datetime.now().isoformat(),
                    "error": str(e)
                }
    def mock_metrics(self, device: Dict[str, Any]) -> Dict[str, Any]:
        #Create mock metrics for a device
        status = ["Online", "Online", "Online", "Warning", "Offline"]
        current_status = random.choice(status)
        
        if current_status == "Offline":
            return {
                "status": "Offline",
                "cpu_usage": 0,
                "mem_usage": 0,
                "bandwidth_in": 0,
                "bandwidth_out": 0,
                "uptime": 0,
                "response_time": 0
            }
        
        return {
            "status": current_status,
            "cpu_usage": round(random.uniform(10, 90), 1),
            "mem_usage": round(random.uniform(30, 85), 1),
            "bandwidth_in": round(random.uniform(50, 500), 2),
            "bandwidth_out": round(random.uniform(30, 300), 2),
            "uptime": random.randint(3600, 2592000),
            "response_time": round(random.uniform(1, 50), 2)
        }
    def device_status(self, dev_ip: str) -> str:
        return self.device_data.get(dev_ip, {}).get("status", "unknown")
    
    def get_last_update(self, dev_ip: str) -> str:
        return self.device_data.get(dev_ip, {}).get("last_polled", None)
    
    def get_metrics(self, dev_ip: str) -> Dict[str, Any]:
        return self.device_data.get(dev_ip, {}).get("metrics", {})
    
    def get_all_devices(self) -> Dict[str, Dict[str, Any]]:
    #Get all device data
        return self.device_data

if __name__ == "__main__":
    print("Starting SNMP Poller Test....")

    influx = InfluxClient()
    poller = SNMPPoller(influx_client=influx)
    poller.start()
    
    print("\nWaiting 10 seconds for polling...")
    time.sleep(10)
    
    print("\nDevice Status Report:")
    print("=" * 60)
    
    devices = get_demo()
    for device in devices:
        dev_ip = device["ip"]
        status = poller.device_status(dev_ip)
        last_update = poller.get_last_update(dev_ip)
        metrics = poller.get_metrics(dev_ip)
        
        print(f"\n📍 {device['name']} ({dev_ip}):")
        print(f" Status: {status}")
        print(f" Last Update: {last_update}")
        print(f" CPU: {metrics.get('cpu_usage', 'N/A')}%")
        print(f" BandwidthIn: {metrics.get('bandwidth_in', 'N/A')} MBps")
        print(f" BandwidthOut: {metrics.get('bandwidth_out', 'N/A')} MBps")
        print(f" Memory: {metrics.get('mem_usage', 'N/A')}%")
        print(f" Uptime: {metrics.get('uptime', 'N/A')}s")
    
    print("\nStopping poller...")
    poller.stop()
    influx.close()
    print("Test complete!")