from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from .demo_devices import get_demo
from .poller import SNMPPoller
from .influx_client import InfluxClient
from .websocket import ConnectionManager
import logging
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global instances
manager = ConnectionManager()
influx_client = None
poller = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    global influx_client, poller

    # Startup
    logger.info("Starting Network Monitoring API...")

    # Initialize InfluxDB client
    influx_client = InfluxClient()

    # Initialize and start poller
    poller = SNMPPoller(influx_client=influx_client)
    poller.start()

    logger.info("Application started successfully")

    # Background task to broadcast updates
    asyncio.create_task(broadcast_updates())

    yield

    # Shutdown
    logger.info("🛑 Shutting down...")
    if poller:
        poller.stop()
    if influx_client:
        influx_client.close()
    logger.info("✅ Shutdown complete")

# Initialize the FastAPI app
app = FastAPI(
    title="Network Monitoring API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None,          # Disable Swagger UI (/docs)
    openapi_url=None,       # Disable OpenAPI schema (/openapi.json)
    redoc_url=None          # Disable ReDoc (/redoc)
)

# CORS Permissions - Restrict to Grafana only
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["Content-Type"],
    max_age=600,
)

async def broadcast_updates():
    """Background task to broadcast device updates via WebSocket"""
    while True:
        try:
            await asyncio.sleep(10)

            if poller and manager.get_connection_count() > 0:
                devices = poller.get_all_devices()
                await manager.broadcast_connection({
                    "type": "update",
                    "timestamp": datetime.now().isoformat(),
                    "data": list(devices.values())
                })

        except Exception as e:
            logger.error(f"Error in broadcast_updates: {e}")

@app.get("/")
async def root():
    """API root"""
    return {
        "message": "Network Monitoring API",
        "status": "running",
        "version": "0.1.0",
        "endpoints": {
            "health": "/api/health",
            "devices": "/api/devices",
            "device_detail": "/api/devices/{ip}",
            "device_history": "/api/devices/{ip}/history",
            "websocket": "/ws"
        }
    }

@app.get("/api/health")
async def health():
    """Health Check"""
    return {
        "status": "ok",
        "timestamp":datetime.now().isoformat(),
        "poller_running": poller.running if poller else False,
        "influxdb_connected": influx_client.client is not None if influx_client else False,
        "websocket_connections": manager.get_connection_count()
    }


@app.get("/api/devices")
async def get_devices():
    """Get all devices with current status"""
    try:
        if not poller:
            # Fallback to demo data if poller not initialized
            logger.warning("Poller not initialized, returning demo data")
            devices = get_demo()
        else:
            devices_dict = poller.get_all_devices()
            if not devices_dict:
                # If poller hasn't collected data yet, return demo data
                devices = get_demo()
            else:
                devices = list(devices_dict.values())

        logger.info(f"Returning {len(devices)} devices")
        return {"success": True, "data": devices, "count": len(devices)}

    except Exception as e:
        logger.error(f"Error fetching devices: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/devices/{device_ip}")
async def get_device_detail(device_ip: str):
    """Get detailed info for a specific device"""
    try:
        if not poller:
            raise HTTPException(status_code=503, detail="Poller not initialized")

        device_data = poller.device_data.get(device_ip)

        if not device_data:
            raise HTTPException(status_code=404, detail=f"Device {device_ip} not found")

        return {"success": True, "data": device_data}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching device {device_ip}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/devices/{device_ip}/history")
async def get_device_history(device_ip: str, hours: int = 1):
    """Get historical metrics for a device from InfluxDB"""
    try:
        if not influx_client or not influx_client.client:
            raise HTTPException(
                status_code=503,
                detail="InfluxDB not available. Historical data not accessible."
            )

        history = influx_client.query_device_history(device_ip, hours)

        return {
            "success": True,
            "device_ip": device_ip,
            "hours": hours,
            "data": history,
            "count": len(history)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching history for {device_ip}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)

    try:
        # Send initial connection message
        await websocket.send_json({
            "type": "connected",
            "message": "WebSocket connected",
            "timestamp": datetime.now().isoformat()
        })

        # Send current device data immediately
        if poller:
            devices = poller.get_all_devices()
            await websocket.send_json({
                "type": "initial",
                "timestamp": datetime.now().isoformat(),
                "data": list(devices.values())
            })

        # Keep connection alive and wait for messages
        while True:
            data = await websocket.receive_text()
            logger.info(f"Received message from client: {data}")

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT"))
    uvicorn.run(app, host="0.0.0.0", port=port)



