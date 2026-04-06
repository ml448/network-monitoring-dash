import os

# Use host.docker.internal for Docker containers
# Fall back to localhost for local development
SNMP_HOST = os.getenv("SNMP_SIMULATOR_HOST", "host.docker.internal")


def get_demo():
    return [
        {
            "id": "001",
            "name": "Core-Router-01",
            "ip": f"{SNMP_HOST}:11610",
            "type": "router",
            "status": "Unknown",
            "metrics": {}
        },
        {
            "id": "002",
            "name": "Core-Switch-01",
            "ip": f"{SNMP_HOST}:11620",
            "type": "switch",
            "status": "Unknown",
            "metrics": {}
        },
        {
            "id": "003",
            "name": "Dist-Firewall-Primary",
            "ip": f"{SNMP_HOST}:11630",
            "type": "firewall",
            "status": "Unknown",
            "metrics": {}
        },
        {
            "id": "004",
            "name": "Dist-Firewall-Secondary",
            "ip": f"{SNMP_HOST}:11640",
            "type": "firewall",
            "status": "Unknown",
            "metrics": {}
        },
        {
            "id": "005",
            "name": "Dist-Switch-01",
            "ip": f"{SNMP_HOST}:11650",
            "type": "switch",
            "status": "Unknown",
            "metrics": {}
        },
        {
            "id": "006",
            "name": "Dist-Switch-02",
            "ip": f"{SNMP_HOST}:11660",
            "type": "switch",
            "status": "Unknown",
            "metrics": {}
        },
        {
            "id": "007",
            "name": "Access-Switch-Floor1",
            "ip": f"{SNMP_HOST}:11670",
            "type": "switch",
            "status": "Unknown",
            "metrics": {}
        },
        {
            "id": "008",
            "name": "Access-Switch-Floor2",
            "ip": f"{SNMP_HOST}:11680",
            "type": "switch",
            "status": "Unknown",
            "metrics": {}
        },
        {
            "id": "009",
            "name": "Access-Switch-Floor3",
            "ip": f"{SNMP_HOST}:11690",
            "type": "switch",
            "status": "Unknown",
            "metrics": {}
        },
        {
            "id": "010",
            "name": "AP-Floor1",
            "ip": f"{SNMP_HOST}:11700",
            "type": "accesspoint",
            "status": "Unknown",
            "metrics": {}
        },
        {
            "id": "011",
            "name": "AP-Floor2",
            "ip": f"{SNMP_HOST}:11710",
            "type": "accesspoint",
            "status": "Unknown",
            "metrics": {}
        },
        {
            "id": "012",
            "name": "AP-Floor3",
            "ip": f"{SNMP_HOST}:11720",
            "type": "accesspoint",
            "status": "Unknown",
            "metrics": {}
        },
        {
            "id": "013",
            "name": "Server-Web-01",
            "ip": f"{SNMP_HOST}:11730",
            "type": "server",
            "status": "Unknown",
            "metrics": {}
        },
        {
            "id": "014",
            "name": "Server-DB-01",
            "ip": f"{SNMP_HOST}:11740",
            "type": "server",
            "status": "Unknown",
            "metrics": {}
        },
        {
            "id": "015",
            "name": "Server-Auth-01",
            "ip": f"{SNMP_HOST}:11750",
            "type": "server",
            "status": "Unknown",
            "metrics": {}
        },
]