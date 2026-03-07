import os
import logging
import aiosmtplib
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from .influx_client import InfluxClient

logger = logging.getLogger(__name__)

@dataclass
class Alert:
    device_ip: str
    device_name: str
    metric: str      
    value: float
    threshold: float
    message: str
    triggered_at: datetime

    def to_dict(self) -> Dict[str, Any]:
        return {
            "device_ip": self.device_ip,
            "device_name": self.device_name,
            "metric": self.metric,
            "value": self.value,
            "threshold": self.threshold,
            "message": self.message,
            "triggered_at": self.triggered_at.isoformat()
        }

class AlertManager():
    def __init__(self, influx_client = None):
        #SMTP Configs
        self.smtp_host = os.getenv("SMTP_HOST")
        self.smtp_port = int(os.getenv("SMTP_PORT"))
        self.smtp_username = os.getenv("SMTP_USERNAME")
        self.smtp_password = os.getenv("SMTP_PASSWORD")
        self.smtp_use_tls = os.getenv("SMTP_USE_TLS")
        self.alert_from = os.getenv("ALERT_FROM_EMAIL", self.smtp_username)
        self.alert_to = os.getenv("ALERT_TO_EMAIL", self.smtp_username)
        
        # Alert Thresholds
        self.cpu_threshold = float(os.getenv("ALERT_CPU_THRESHOLD"))
        self.memory_threshold = float(os.getenv("ALERT_MEMORY_THRESHOLD"))
        self.bandwidth_threshold = float(os.getenv("ALERT_BANDWIDTH_THRESHOLD"))
        self.response_time_threshold = float(os.getenv("ALERT_RESPONSE_TIME_THRESHOLD"))  
        self.cooldown_seconds = int(os.getenv("ALERT_COOLDOWN_TIME"))
        self.last_alert_times: Dict[str, datetime] = {}

        # Syslog alert threshold
        # Alert on messages with severity <= this value
        self.syslog_severity_threshold = int(os.getenv("SYSLOG_SEVERITY_THRESHOLD", "3"))

        self.influx_client = influx_client
    
    def _is_on_cooldown(self, device_ip: str, metric: str) -> bool:
        key = f"{device_ip}:{metric}"

        last_triggered = self.last_alert_times.get(key)
        if not last_triggered:
            return False

        now = datetime.now(timezone.utc)
        elapsed = (now - last_triggered).total_seconds()

        return elapsed < self.cooldown_seconds

    def _mark_alerted(self, device_ip: str, metric: str) -> None:
        key = f"{device_ip}:{metric}"
        self.last_alert_times[key] = datetime.now(timezone.utc)


    def check_device(self, device_data: Dict[str, Any]) -> List[Alert]:
        alerts: List[Alert] = []

        device_ip = device_data.get("ip", "unknown")
        device_name = device_data.get("name", device_ip)
        metrics = device_data.get("metrics", {})
        now = datetime.now(timezone.utc)

        #Check CPU for comparison
        cpu = metrics.get("cpu_usage")
        if cpu is not None and cpu > self.cpu_threshold:
            if not self._is_on_cooldown(device_ip, "cpu_usage"):
                alert = Alert(
                    device_ip=device_ip,
                    device_name=device_name,
                    metric="cpu_usage",
                    value=float(cpu),
                    threshold=self.cpu_threshold,
                    message=f"CPU usage exceeded threshold ({cpu:.2f}% > {self.cpu_threshold}%)",
                    triggered_at=now
                )
                alerts.append(alert)
                self._mark_alerted(device_ip, "cpu_usage")

        #Check Memory for comparison
        mem = metrics.get("mem_usage")
        if mem is not None and mem > self.memory_threshold:
            if not self._is_on_cooldown(device_ip, "mem_usage"):
                alert = Alert(
                    device_ip=device_ip,
                    device_name=device_name,
                    metric="mem_usage",
                    value=float(mem),
                    threshold=self.memory_threshold,
                    message=f"Memory usage exceeded threshold ({mem:.2f}% > {self.memory_threshold}%)",
                    triggered_at=now
                )
                alerts.append(alert)
                self._mark_alerted(device_ip, "mem_usage")
        #Check Response Time for comparison
        response = metrics.get("response_time")
        if response is not None and response > self.response_time_threshold:
            if not self._is_on_cooldown(device_ip, "response_time"):
                alert = Alert(
                    device_ip=device_ip,
                    device_name=device_name,
                    metric="response_time",
                    value=float(response),
                    threshold=self.response_time_threshold,
                    message=f"Response time exceeded threshold ({response:.2f}ms > {self.response_time_threshold}ms)",
                    triggered_at=now
                )
                alerts.append(alert)
                self._mark_alerted(device_ip, "response_time")

        # Check device status (at device_data level, not inside metrics)
        status = device_data.get("status")
        if status in ("Offline", "Error"):
            if not self._is_on_cooldown(device_ip, "status"):
                alert = Alert(
                    device_ip=device_ip,
                    device_name=device_name,
                    metric="status",
                    value=0.0,
                    threshold=1.0,
                    message=f"Device is {status}",
                    triggered_at=now
                )
                alerts.append(alert)
                self._mark_alerted(device_ip, "status")

        return alerts

    async def email_alert(self, alert: Alert) -> None:
        if not self.smtp_username or not self.alert_to:
            logger.warning("SMTP not configured, skipping...")
            return False
        
        try:
            msg = MIMEMultipart()
            msg["From"] = self.alert_from
            msg["To"] = self.alert_to
            msg["Subject"] = f"Alert: {alert.device_name} - {alert.metric}"


            body = f"""
Alert Triggered

Device: {alert.device_name} ({alert.device_ip})
Metric: {alert.metric}
Value: {alert.value}
Threshold: {alert.threshold}
Message: {alert.message}
Time (UTC): {alert.triggered_at.isoformat()}

{alert.message}
"""
            msg.attach(MIMEText(body, "plain"))
            
            await aiosmtplib.send(
                msg,
                hostname=self.smtp_host,
                port=self.smtp_port,
                username=self.smtp_username,
                password=self.smtp_password,
                start_tls=True,
            )

            logger.info(f"Alert sent: {alert.device_name}:{alert.metric}")
            return True
        
        except Exception as e:
            logger.error(f"Failed to send alert: {e}")
            return False
        
    def log_alert(self, alert: Alert, email_sent: bool = False):
        if not self.influx_client or not self.influx_client.write_api:
            return
        
        try:
            from influxdb_client import Point

            point = Point("alerts") \
                .tag("device_ip", alert.device_ip) \
                .tag("device_name", alert.device_name) \
                .tag("metric", alert.metric) \
                .field("value", alert.value) \
                .field("threshold", alert.threshold) \
                .field("email_sent", email_sent) \
                .field("message", alert.message)
            
            self.influx_client.write_api.write(
                bucket=self.influx_client.bucket,
                org=self.influx_client.org,
                record=point
            )

            logger.debug(f"Alert logged to InfluxDB: {alert.device_name}:{alert.metric}")

        except Exception as e:
            logger.error(f"Failed to log alert: {e}")

    
    async def process_device(self, device_data: Dict[str, Any]):
        # Main processing function: checks for device then sends alert then logs to InfluxDB
        alerts = self.check_device(device_data)

        for alert in alerts:
            email_sent = await self.email_alert(alert)
            self.log_alert(alert, email_sent)

    def check_syslog_message(self, msg) -> Optional[Alert]:
        # Check if syslog message should trigger an alert based on severity
        # Alert on severity <= threshold (lower number = more severe)
        if msg.severity > self.syslog_severity_threshold:
            return None

        # Use hostname as device identifier, check cooldown
        cooldown_key = f"syslog:{msg.hostname}"
        if self._is_on_cooldown(msg.hostname, cooldown_key):
            return None

        now = datetime.now(timezone.utc)
        self._mark_alerted(msg.hostname, cooldown_key)

        return Alert(
            device_ip=msg.source_ip,
            device_name=msg.hostname,
            metric="syslog",
            value=float(msg.severity),
            threshold=float(self.syslog_severity_threshold),
            message=f"[{msg.severity_name}] {msg.app_name}: {msg.message[:200]}",
            triggered_at=now,
        )

    async def process_alert(self, alert: Alert) -> None:
        # Process a single alert: send email and log
        email_sent = await self.email_alert(alert)
        self.log_alert(alert, email_sent)

                
    
    
            
            
    


    


    


        
