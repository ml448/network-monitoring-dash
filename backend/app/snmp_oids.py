
# =============================================================================
# SYSTEM MIB (1.3.6.1.2.1.1) - RFC 1213
# Basic device identification - supported by virtually ALL SNMP devices
# =============================================================================

SYSTEM = {
    "sysDescr": "1.3.6.1.2.1.1.1.0",      # Full device description string
    "sysObjectID": "1.3.6.1.2.1.1.2.0",   # Vendor's OID for this device type
    "sysUpTime": "1.3.6.1.2.1.1.3.0",     # Uptime in hundredths of a second
    "sysContact": "1.3.6.1.2.1.1.4.0",    # Admin contact info
    "sysName": "1.3.6.1.2.1.1.5.0",       # Device hostname
    "sysLocation": "1.3.6.1.2.1.1.6.0",   # Physical location
    "sysServices": "1.3.6.1.2.1.1.7.0",   # OSI layer services provided
}

# =============================================================================
# INTERFACES MIB (1.3.6.1.2.1.2) - RFC 1213
# Network interface statistics - critical for bandwidth monitoring
# Note: These are table OIDs - append .{ifIndex} to get specific interface
# =============================================================================

INTERFACES = {
    "ifNumber": "1.3.6.1.2.1.2.1.0",          # Total number of interfaces
    "ifDescr": "1.3.6.1.2.1.2.2.1.2",         # Interface description (e.g., "GigabitEthernet0/1")
    "ifType": "1.3.6.1.2.1.2.2.1.3",          # Interface type (ethernet=6, loopback=24, etc.)
    "ifSpeed": "1.3.6.1.2.1.2.2.1.5",         # Interface speed in bits/sec
    "ifAdminStatus": "1.3.6.1.2.1.2.2.1.7",   # Admin status (up=1, down=2, testing=3)
    "ifOperStatus": "1.3.6.1.2.1.2.2.1.8",    # Operational status (up=1, down=2, etc.)
    "ifInOctets": "1.3.6.1.2.1.2.2.1.10",     # Total bytes received (32-bit counter)
    "ifOutOctets": "1.3.6.1.2.1.2.2.1.16",    # Total bytes transmitted (32-bit counter)
    "ifInErrors": "1.3.6.1.2.1.2.2.1.14",     # Inbound packets with errors
    "ifOutErrors": "1.3.6.1.2.1.2.2.1.20",    # Outbound packets with errors
}

# 64-bit counters for high-speed interfaces (IF-MIB, RFC 2863)
INTERFACES_HC = {
    "ifHCInOctets": "1.3.6.1.2.1.31.1.1.1.6",   # 64-bit bytes in
    "ifHCOutOctets": "1.3.6.1.2.1.31.1.1.1.10", # 64-bit bytes out
}

# =============================================================================
# HOST RESOURCES MIB (1.3.6.1.2.1.25) - RFC 2790
# CPU and Memory statistics - mainly for servers/workstations
# Note: Not all network devices support this MIB
# =============================================================================

HOST_RESOURCES = {
    # Processor table - walk to get all CPUs
    "hrProcessorLoad": "1.3.6.1.2.1.25.3.3.1.2",  # CPU load percentage per processor

    # Storage table - walk to get all storage (RAM, disk, etc.)
    "hrStorageDescr": "1.3.6.1.2.1.25.2.3.1.3",   # Storage description
    "hrStorageAllocationUnits": "1.3.6.1.2.1.25.2.3.1.4",  # Block size in bytes
    "hrStorageSize": "1.3.6.1.2.1.25.2.3.1.5",    # Total blocks
    "hrStorageUsed": "1.3.6.1.2.1.25.2.3.1.6",    # Used blocks
}

# =============================================================================
# IP-MIB (1.3.6.1.2.1.4) - RFC 4293
# IP statistics and routing information
# =============================================================================

IP_STATS = {
    "ipForwarding": "1.3.6.1.2.1.4.1.0",     # Is IP forwarding enabled? (router=1, host=2)
    "ipInReceives": "1.3.6.1.2.1.4.3.0",     # Total IP datagrams received
    "ipOutRequests": "1.3.6.1.2.1.4.10.0",   # Total IP datagrams sent
}

# =============================================================================
# COMMON VENDOR ENTERPRISE OIDs
# These are under 1.3.6.1.4.1.{enterprise_id}
# =============================================================================

ENTERPRISE_IDS = {
    "cisco": 9,
    "hp": 11,
    "microsoft": 311,
    "juniper": 2636,
    "dell": 674,
    "netgear": 4526,
    "ubiquiti": 41112,
    "fortinet": 12356,
    "paloalto": 25461,
}

# Cisco-specific OIDs (commonly used)
CISCO = {
    "cpmCPUTotal5min": "1.3.6.1.4.1.9.9.109.1.1.1.1.5",   # 5-min CPU average
    "ciscoMemoryPoolUsed": "1.3.6.1.4.1.9.9.48.1.1.1.5",  # Memory used
    "ciscoMemoryPoolFree": "1.3.6.1.4.1.9.9.48.1.1.1.6",  # Memory free
}


def get_basic_oids() -> dict:
    return {
        "sysDescr": SYSTEM["sysDescr"],
        "sysUpTime": SYSTEM["sysUpTime"],
        "sysName": SYSTEM["sysName"],
    }


def get_interface_oids(if_index: int = 1) -> dict:
    return {
        "ifDescr": f"{INTERFACES['ifDescr']}.{if_index}",
        "ifOperStatus": f"{INTERFACES['ifOperStatus']}.{if_index}",
        "ifInOctets": f"{INTERFACES['ifInOctets']}.{if_index}",
        "ifOutOctets": f"{INTERFACES['ifOutOctets']}.{if_index}",
        "ifSpeed": f"{INTERFACES['ifSpeed']}.{if_index}",
    }