import asyncio
import re
import logging 
import os
import socket
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional
from collections import deque

if TYPE_CHECKING:
    from .influx_client import InfluxClient
    from .alert_manager import AlertManager
    from .websocket import ConnectionManager

logger = logging.getLogger(__name__)

# Syslog facility names from RFC 5424
FACILITIES = {
    0: "kernel", 1: "user", 3: "daemon", 4: "auth",
    5: "syslogd", 9: "cron", 16: "local0", 17:"local1",
    18: "local2", 19: "local3", 20: "local4", 23: "local7"
}

# Syslog severity levels (RFC 5424: 0-7 only)
SEVERITY = {
    0: "EMERGENCY", 1: "ALERT", 2: "CRITICAL", 3: "ERROR",
    4: "WARNING", 5: "NOTICE", 6: "INFO", 7: "DEBUG"
}

# Typical Alert Patterns
ALERT_PATTERNS = [
    (re.compile(r'authentication failure', re.I), "AUTH_FAILURE"),
    (re.compile(r'interface.*down',        re.I), "INTERFACE_DOWN"),
    (re.compile(r'link.*down',             re.I), "LINK_DOWN"),
    (re.compile(r'config.*change',         re.I), "CONFIG_CHANGE"),
    (re.compile(r'login.*fail',            re.I), "LOGIN_FAILED"),
    (re.compile(r'unauthorized',           re.I), "UNAUTHORIZED"),
    (re.compile(r'critical',               re.I), "CRITICAL_KEYWORD"),
]

#RFC 5424: TIMESTAMP, HOSTNAME, APP, PROCID, MSGID, STRUCTURED-DATA, MESSAGE
_RFC5424_PATTERN = re.compile(
    r'^<(\d+)>1 ' 
    r'(\S+) '     
    r'(\S+) '     
    r'(\S+) '     
    r'(\S+) '     
    r'(\S+) '     
    r'(\S+) '     
    r'(.*)$',     
    re.DOTALL
)

#RFC 3164: TIMESTAMP, HOSTNAME, MESSAGE
_RFC3164_PATTERN = re.compile(
    r'^<(\d+)>'
    r'(\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}) '  
    r'(\S+) '                                  
    r'(.*)$',                                  
    re.DOTALL
)

@dataclass
class SyslogMessage:
    timestamp: datetime
    hostname: str
    facility: int
    severity: int
    app_name: str
    message: str
    format: str
    raw: str = ""
    source_ip: str = ""

    @property
    def facility_name(self) -> str:
        return FACILITIES.get(self.facility, f"facility{self.facility}")
    
    @property
    def severity_name(self) -> str:
        return SEVERITY.get(self.severity, "UNKNOWN")
    
    @property
    def priority(self) -> int:
        # Priority value measured by facility * 8 + severity
        return self.facility * 8 + self.severity
    
    def to_dict(self) -> dict:
        return {
            "timestamp":     self.timestamp.isoformat(),
            "hostname":      self.hostname,
            "facility":      self.facility,
            "facility_name": self.facility_name,
            "severity":      self.severity,
            "severity_name": self.severity_name,
            "app_name":      self.app_name,
            "message":       self.message,
            "source_ip":     self.source_ip,
            "format":        self.format,
        }


class SyslogListener:
    def __init__(
        self,
        influx_client: "InfluxClient",
        alert_manager: "AlertManager",
        ws_manager: "ConnectionManager"
    ):
        self.influx_client = influx_client
        self.alert_manager = alert_manager
        self.ws_manager = ws_manager

        #Syslog port configs
        self.port = int(os.getenv("SYSLOG_PORT", "514"))
        self.buffer_size = int(os.getenv("SYSLOG_BUFFER_SIZE", "1000"))

        #Buffer recent messages
        self.recent_messages: deque[SyslogMessage] = deque(maxlen=self.buffer_size)

        #Threading management
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._transport: Optional[asyncio.DatagramTransport] = None
        self._running = False

        # Statistics
        self.stats = {
            "messages_received": 0,
            "parse_errors": 0,
            "alerts_triggered": 0,
        }

    # Start listener in the background
    def start(self) -> None:
        if self._running:
            logger.warning("Syslog listener is already running")
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_server, daemon=True)
        self._thread.start()
        logger.info(f"Syslog is running on UDP port: {self.port}")

    # Stop the listener
    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._loop and self._transport:
            self._loop.call_soon_threadsafe(self._transport.close)

        if self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None

        logger.info("Syslog listener stopped")

    def _run_server(self) -> None:
        # Thread entry point - creates event loop and runs UDP server
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        try:
            self._loop.run_until_complete(self._start_udp_server())
            self._loop.run_forever()
        except Exception as e:
            logger.error(f"Syslog listener error: {e}")
        finally:
            self._loop.close()

    # Create and start the UDP server
    async def _start_udp_server(self) -> None:
        self._transport, _ = await self._loop.create_datagram_endpoint(
            lambda: SyslogProtocol(self),
            local_addr=("0.0.0.0", self.port),
            family=socket.AF_INET,
        )
        logger.info(f"Syslog UDP server listening on port {self.port}")

    @staticmethod
    # Parsing CSV format syslog messages
    def parse_filterlog(message: str) -> str:
        fields = message.split(",")
        if len(fields) < 20:
            return message
        try:
            action = fields[6]
            direction = fields[7]
            protocol = fields[16]
            src_ip = fields[18]
            dst_ip = fields[19]

            summary = f"{action} {direction} {protocol} {src_ip}"

            has_ports = protocol.lower() in ("tcp", "udp") and len(fields) > 21
            if has_ports:
                summary += f":{fields[20]} -> {dst_ip}:{fields[21]}"
            else:
                summary += f" -> {dst_ip}"
            if protocol.lower() == "tcp" and len(fields) > 24:
                summary += f" [{fields[24]}]"
            return summary
        except (IndexError, ValueError):
            return message


    def parse_message(self, data: bytes, source_ip: str) -> Optional[SyslogMessage]:
        raw = data.decode("utf-8", errors="replace").strip()
        now = datetime.now(timezone.utc)

        m = _RFC5424_PATTERN.match(raw)

        if m:
            pri = int(m.group(1))
            hostname = m.group(3) if m.group(3) != '-' else source_ip
            app_name = m.group(4) if m.group(4) != '-' else ""
            message = m.group(8).strip()
            return SyslogMessage(
                timestamp=now,
                hostname=hostname,
                facility=pri >> 3,
                severity=pri & 0x7,
                app_name=app_name,
                message=message,
                format="RFC5424",
                raw=raw,
                source_ip=source_ip,
            )

        m = _RFC3164_PATTERN.match(raw)
        if m:
            pri = int(m.group(1))
            hostname = m.group(3) if m.group(3) != '-' else source_ip
            # RFC 3164 group 4 contains "TAG: MESSAGE" or just message
            raw_msg = m.group(4).strip()

            # Detect when a hostname is a process name
            pid_in_hostname = re.match(r'^(\S+?)\[(\d+)\]:?$', hostname)
            if pid_in_hostname:
                app_name = pid_in_hostname.group(1)
                hostname = source_ip
                message = raw_msg
            else:
                # Try to extract app_name from TAG
                tag_match = re.match(r'^(\S+?)(?:\[\d+\])?:\s*(.*)$', raw_msg)
                if tag_match:
                    app_name = tag_match.group(1)
                    message = tag_match.group(2)
                else:
                    app_name = ""
                    message = raw_msg

            if app_name == "filterlog":
                message = self.parse_filterlog(message)
            return SyslogMessage(
                timestamp=now,
                hostname=hostname,
                facility=pri >> 3,
                severity=pri & 0x7,
                app_name=app_name,
                message=message,
                format="RFC3164",
                raw=raw,
                source_ip=source_ip,
            )

        # Fallback: Unrecognized format returns whole payload as message
        logger.debug(f"Unrecognized syslog format from {source_ip}: {raw[:80]}")
        return SyslogMessage(
            timestamp=now,
            hostname=source_ip,
            facility=1,
            severity=6,
            app_name="",
            message=raw,
            format="UNKNOWN",
            raw=raw,
            source_ip=source_ip,
        )

    async def handle_message(self, msg: SyslogMessage) -> None:
        # Routes messages to all destinations and stores in buffer
        self.recent_messages.append(msg)
        self.stats["messages_received"] += 1

        # Write to InfluxDB
        try:
            self.influx_client.write_syslog(msg)
        except Exception as e:
            logger.error(f"Failed to write syslog to InfluxDB: {e}")

        # Check for alerts
        try:
            alert = self.alert_manager.check_syslog_message(msg)
            if alert:
                self.stats["alerts_triggered"] += 1
                await self.alert_manager.process_alert(alert)
        except Exception as e:
            logger.error(f"Failed to process syslog alert: {e}")

        # Broadcast via WebSocket
        try:
            if self.ws_manager.get_connection_count() > 0:
                await self.ws_manager.broadcast_connection({
                    "type": "syslog",
                    "timestamp": datetime.now().isoformat(),
                    "data": msg.to_dict(),
                })
        except Exception as e:
            logger.error(f"Failed to broadcast syslog: {e}")

    def get_recent_messages(self, count: int = 100) -> list[dict]:
        """Get recent messages for API endpoint."""
        messages = list(self.recent_messages)[-count:]
        return [m.to_dict() for m in messages]

    def get_stats(self) -> dict:
        """Get listener statistics."""
        return {
            **self.stats,
            "buffer_size": len(self.recent_messages),
            "buffer_max": self.buffer_size,
            "running": self._running,
            "port": self.port,
        }

# Asyncio protocol handler for UDP syslog packets
class SyslogProtocol(asyncio.DatagramProtocol):
    def __init__(self, listener: SyslogListener):
        self.listener = listener

    def datagram_received(self, data: bytes, addr: tuple) -> None:
        # Called when a UDP packet is received
        source_ip = addr[0]

        try:
            msg = self.listener.parse_message(data, source_ip)
            if msg:
                # Schedule async handling in the event loop
                asyncio.ensure_future(self.listener.handle_message(msg))
            else:
                self.listener.stats["parse_errors"] += 1
        except Exception as e:
            logger.error(f"Error processing syslog from {source_ip}: {e}")
            self.listener.stats["parse_errors"] += 1

    def error_received(self, exc: Exception) -> None:
        # Called when a send/receive operation raises an OSError
        logger.error(f"Syslog UDP error: {exc}")
        