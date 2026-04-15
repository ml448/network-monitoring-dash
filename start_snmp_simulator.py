import subprocess
import sys
import time

DEVICES = {
    "core-router-01": 11610,
    "core-switch-01": 11620,
    "dist-firewall-primary": 11630,
    "dist-firewall-secondary": 11640,
    "dist-switch-01": 11650,
    "dist-switch-02": 11660,
    "access-switch-floor1": 11670,
    "access-switch-floor2": 11680,
    "access-switch-floor3": 11690,
    "ap-floor1": 11700,
    "ap-floor2": 11710,
    "ap-floor3": 11720,
    "server-web-01": 11730,
    "server-db-01": 11740,
    "server-auth-01": 11750,
}

def start_simulators():
    """Start SNMP simulator for each device."""
    processes = []

    print("Starting SNMP simulators...")
    print("-" * 60)

    for device, port in DEVICES.items():
        try:
            cmd = [
                "snmpsim-command-responder",  
                "--data-dir=snmp_data",      
                f"--agent-udpv4-endpoint=0.0.0.0:{port}",
            ]

            print(f"Starting {device} on port {port}...")

            proc = subprocess.Popen(cmd)
            
            processes.append((device, port, proc))
            print(f"   Started PID: {proc.pid}")
            time.sleep(1)

        except Exception as e:
            print(f"   Failed: {e}")

    print("-" * 60)
    print(f"{len(processes)} simulators started.")
    print("Watch output above for 'Listening at...' messages")
    print("Press Ctrl+C to stop all simulators.\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\nStopping simulators...")
        for device, port, proc in processes:
            proc.terminate()
        print("All simulators stopped.")

if __name__ == "__main__":
    start_simulators()