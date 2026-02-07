import os

# Use host.docker.internal for Docker containers to reach host machine
# Fall back to localhost for local development
SNMP_HOST = os.getenv("SNMP_SIMULATOR_HOST", "host.docker.internal")


def get_demo():
    return [
        {
            "id": "001",
            "name": "Router-main",
            "ip": f"{SNMP_HOST}:11610",
            "type": "router",
            "status": "Unknown",
            "metrics": {}
        },
        {
            "id": "002",
            "name": "Switch-3rdfloor",
            "ip": f"{SNMP_HOST}:11620",
            "type": "switch",
            "status": "Unknown",
            "metrics": {}
        },
        {
            "id": "003",
            "name": "Firewall-primary",
            "ip": f"{SNMP_HOST}:11630",
            "type": "firewall",
            "status": "Unknown",
            "metrics": {}
        },
        {
            "id": "004",
            "name": "Server-web01",
            "ip": f"{SNMP_HOST}:11640",
            "type": "server",
            "status": "Unknown",
            "metrics": {}
        },
        {
            "id": "005",
            "name": "Accesspoint-floor2",
            "ip": f"{SNMP_HOST}:11650",
            "type": "accesspoint",
            "status": "Unknown",
            "metrics": {}
        },
        {
            "id": "006",
            "name": "Switch-backup",
            "ip": f"{SNMP_HOST}:11660",
            "type": "switch",
            "status": "Unknown",
            "metrics": {}
        },
    ]