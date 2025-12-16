from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.base import BaseHTTPMiddleware
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
from typing import Optional, Annotated
import ipaddress

# Load environment variables
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global instances
manager = ConnectionManager()
influx_client = None
poller = None

# Validate IP addresses
def validate_ip(ip_string: str) -> str:
    try:
        ipaddress.ip_address(ip_string)
        return ip_string
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid IP: {ip_string}")

# Security headers middleware
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

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

# Add security headers to all responses
app.add_middleware(SecurityHeadersMiddleware)

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
        raise HTTPException(status_code=500, detail="Internal server error")
    
@app.get("/api/devices/{device_ip}")
async def get_device_detail(device_ip: str):
    """Get detailed info for a specific device"""
    try:
        device_ip = validate_ip(device_ip)

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
        raise HTTPException(status_code=500, detail="Internal server error")
    
@app.get("/api/devices/{device_ip}/history")
async def get_device_history(
    device_ip: str,
    hours: Annotated[int, Query(ge=1, le=168, description="Hours of history (1-168)")] = 1
):
    """Get historical metrics for a device from InfluxDB"""
    try:
        device_ip = validate_ip(device_ip)

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
        raise HTTPException(status_code=500, detail="Internal server error")

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



