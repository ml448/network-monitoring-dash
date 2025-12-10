def get_demo():
    """Returns list of demo network devices"""
    return [
        {
            "id": "001",
            "name": "Router-main",
            "ip": "142.62.147.56",
            "type": "router",
            "status": "Online",
            "metrics": {
                "cpu_usage": 42.1,
                "mem_usage": 63.7
            }
        },
        {
            "id": "010",
            "name": "Switch-3rdFloor",
            "ip": "234.218.156.241",
            "type": "switch",
            "status": "Offline",
            "metrics": None
        },
        {
            "id": "002",
            "name": "Firewall-Primary",
            "ip": "192.168.1.1",
            "type": "firewall",
            "status": "Online",
            "metrics": {
                "cpu_usage": 28.4,
                "mem_usage": 45.2
            }
        },
        {
            "id": "003",
            "name": "Server-Web01",
            "ip": "10.0.0.15",
            "type": "server",
            "status": "Online",
            "metrics": {
                "cpu_usage": 67.8,
                "mem_usage": 81.3
            }
        },
        {
            "id": "006",
            "name": "AccessPoint-Floor2",
            "ip": "192.168.2.20",
            "type": "access_point",
            "status": "Online",
            "metrics": {
                "cpu_usage": 15.2,
                "mem_usage": 32.1
            }
        },
        {
            "id": "008",
            "name": "Switch-Backup",
            "ip": "172.16.2.50",
            "type": "switch",
            "status": "Maintenance",
            "metrics": None
        }
    ]
