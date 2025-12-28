"""
SNMP Helper Functions

Utilities for converting SNMP data types to Python native types.
"""

from typing import Any, Union
from pysnmp.proto.rfc1902 import (
    Integer,
    Integer32,
    Counter32,
    Counter64,
    Gauge32,
    TimeTicks,
    OctetString,
    IpAddress,
    Opaque,
)


def convert_snmp_value(value: Any) -> Union[int, float, str]:

    # Convert pysnmp value types to Python native types
    if isinstance(value, (Integer, Integer32, Gauge32)):
        return int(value)

    elif isinstance(value, (Counter32, Counter64)):
        return int(value)

    elif isinstance(value, TimeTicks):
        # Convert to seconds
        return int(value) // 100

    elif isinstance(value, OctetString):
        try:
            # Try to decode as UTF-8 string
            return value.prettyPrint()
        except:
            # If that fails, return hex representation
            return str(value)

    elif isinstance(value, IpAddress):
        return value.prettyPrint()

    else:
        # Fallback for unknown types
        return str(value)


def format_uptime(seconds: int) -> str:
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    parts = []
    if days > 0:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if hours > 0:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes > 0:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    if secs > 0 or not parts:
        parts.append(f"{secs} second{'s' if secs != 1 else ''}")

    return ", ".join(parts)


def format_bytes(bytes_value: int) -> str:
    for unit in ['B', 'KB', 'MB', 'GB', 'TB', 'PB']:
        if bytes_value < 1024.0:
            return f"{bytes_value:.2f} {unit}"
        bytes_value /= 1024.0
    return f"{bytes_value:.2f} EB"