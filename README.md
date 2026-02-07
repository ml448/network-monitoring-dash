# Network Monitoring Dashboard

A real-time dashboard for keeping an eye on network devices. Built this to learn more about SNMP and real-time data visualization with Grafana.

## What's Working

- **SNMP Polling**: Real SNMP implementation using pysnmp (queries system info, CPU, memory, bandwidth)
  - Still using demo/mock device IPs for testing
  - Runs every 60 seconds by default (configurable)
  - Handles timeouts and retries gracefully

- **FastAPI Backend**: RESTful API + WebSocket support for real-time updates

- **InfluxDB**: Time-series storage for all the metrics

- **Grafana Dashboard**: Visualizing the data in real-time

- **Demo Devices**: Hardcoded device list for testing (database integration coming later)

## Tech Stack

- **Backend**: Python 3.x, FastAPI, pysnmp 7.1.22
- **Database**: InfluxDB 2.x for time-series data
- **Frontend**: Grafana for dashboards and visualization
- **Deployment**: Docker-ready

## Quick Start

1. Copy `.env.example` to `.env` and fill in your settings:
   ```bash
   SNMP_COMMUNITY=public
   SNMP_TIMEOUT=5
   SNMP_RETRIES=3
   SNMP_POLL_INTERVAL=60
   INFLUXDB_URL=http://localhost:8086
   INFLUXDB_TOKEN=your-token
   INFLUXDB_ORG=your-org
   INFLUXDB_BUCKET=network-metrics
   ```

2. Start it up:
   ```bash
   cd backend
   pip install -r requirements.txt
   python -m app.main
   ```

3. Check the API docs at `http://localhost:8000/docs`

## API Endpoints

- `GET /api/devices` - List all monitored devices
- `GET /api/devices/{ip}` - Get current stats for a device
- `GET /api/devices/{ip}/history?hours=24` - Historical data
- `WebSocket /ws` - Real-time updates

## Notes

- Using pysnmp
- SNMP community string is read from env vars, keep it secret!
- All IP addresses are validated before use
- Polls run in the background, won't block API requests

## Current Status

**Core functionality working!** The SNMP polling is live and storing metrics in InfluxDB. Grafana dashboards are visualizing the data in real-time.