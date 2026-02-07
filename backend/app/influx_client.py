import os
import re
import logging
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from datetime import datetime
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class InfluxClient:
    # Writes device metrics to InfluxDB
    
    def __init__(self):
        self.url = os.getenv("INFLUXDB_URL")
        self.token = os.getenv("INFLUXDB_TOKEN")
        self.org = os.getenv("INFLUXDB_ORG")
        self.bucket = os.getenv("INFLUXDB_BUCKET")
        
        self.client = None
        self.write_api = None
        self._connect()

    def _connect(self):
        # Initialize DB connection
        try:
            if not self.token:
                logger.warning("INFLUXDB_TOKEN not set, running without InfluxDB")
                return
            
            self.client = InfluxDBClient(
                url=self.url,
                token=self.token,
                org=self.org
            )

            self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
            
            # Test connection
            health = self.client.health()
            if health.status == "pass":
                logger.info(f"Connected to InfluxDB at {self.url}")
            else:
                logger.warning(f"InfluxDB health check returned: {health.status}")
                
        except Exception as e:
            logger.error(f"Failed to connect to InfluxDB: {e}")
            self.client = None
            self.write_api = None

    def write_metrics(self, device_data: Dict[str, Any]):
        # Write metrics to database
        if not self.write_api:
            logger.debug("InfluxDB not available, skipping write")
            return
        
        try:
            dev_ip = device_data.get("ip")
            dev_name = device_data.get("name")
            dev_type = device_data.get("type")
            status = device_data.get("status", "unknown")
            metrics = device_data.get("metrics", {})
            
            point = Point("device_metrics") \
                .tag("device_ip", dev_ip) \
                .tag("device_name", dev_name) \
                .tag("device_type", dev_type) \
                .tag("status", status)
            
            # Add metric fields
            if metrics:
                if "cpu_usage" in metrics:
                    point = point.field("cpu_usage", float(metrics["cpu_usage"]))
                if "mem_usage" in metrics:
                    point = point.field("mem_usage", float(metrics["mem_usage"]))
                if "bandwidth_in" in metrics:
                    point = point.field("bandwidth_in", float(metrics["bandwidth_in"]))
                if "bandwidth_out" in metrics:
                    point = point.field("bandwidth_out", float(metrics["bandwidth_out"]))
                if "uptime" in metrics:
                    point = point.field("uptime", int(metrics["uptime"]))
                if "response_time" in metrics:
                    point = point.field("response_time", float(metrics["response_time"]))
            
            # Write to InfluxDB
            self.write_api.write(bucket=self.bucket, org=self.org, record=point)
            logger.debug(f"Wrote metrics for {dev_name} ({dev_ip})")
            
        except Exception as e:
            logger.error(f"Error writing to InfluxDB: {e}")
    
    def _sanitize_flux_string(self, value: str) -> str:
        """Sanitize string for safe use in Flux queries by escaping special characters"""
        # Escape backslashes first, then quotes
        value = value.replace("\\", "\\\\")
        value = value.replace('"', '\\"')
        # Remove any Flux injection attempts (pipe operators, parentheses)
        if re.search(r'[|>(){}\[\]]', value):
            raise ValueError(f"Invalid characters in query parameter: {value}")
        return value

    def query_device_history(self, device_ip: str, hours: int = 1) -> List[Dict[str, Any]]:
        """Query historical data for a device"""
        if not self.client:
            return []

        # Validate and constrain hours parameter (1 hour to 7 days max)
        if not isinstance(hours, int) or hours < 1:
            hours = 1
        hours = min(hours, 168)  # Cap at 7 days

        try:
            # Sanitize device_ip to prevent Flux injection
            safe_device_ip = self._sanitize_flux_string(device_ip)

            query = f'''
            from(bucket: "{self.bucket}")
                |> range(start: -{hours}h)
                |> filter(fn: (r) => r["_measurement"] == "device_metrics")
                |> filter(fn: (r) => r["device_ip"] == "{safe_device_ip}")
                |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
            '''

            query_api = self.client.query_api()
            result = query_api.query(org=self.org, query=query)

            data = []
            for table in result:
                for record in table.records:
                    data.append({
                        "time": record.get_time().isoformat(),
                        "cpu_usage": record.values.get("cpu_usage"),
                        "mem_usage": record.values.get("mem_usage"),
                        "bandwidth_in": record.values.get("bandwidth_in"),
                        "bandwidth_out": record.values.get("bandwidth_out"),
                        "response_time": record.values.get("response_time"),
                    })

            return data

        except ValueError as e:
            logger.warning(f"Invalid query parameter: {e}")
            return []
        except Exception as e:
            logger.error(f"Error querying InfluxDB: {e}")
            return []
    
    def close(self):
        """Close InfluxDB connection"""
        if self.client:
            self.client.close()
            logger.info("InfluxDB connection closed")