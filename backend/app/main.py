from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import asyncio
from datetime import datetime
from demo_devices import get_demo
from websocket import ConnectionManager
import logging 

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
manager = ConnectionManager()

#Initialize the FastAPI app
app = FastAPI(title="Network Monitoring API")

#CORS Permissions 
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

active_connections = []

@app.get("/")
async def root():
    """API root"""
    return {
        "message": "Network Monitoring API",
        "status": "development",
        "version": "0.1.0"
    }

@app.get("/api/health")
async def health():
    """Health Check"""
    return {
        "status": "ok",
        "timestamp":datetime.now().isoformat()    
    }

@app.get("/api/devices")
async def get_devices():
    """Get demo devices"""
    try:
        logger.info("Fetching devices...")
        devices = get_demo()
        logger.info(f"Returning {len(devices)} devices")
        return {"success": True, "data": devices}
    except Exception as e:
        logger.error(f"Error fetching devices: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    
    try:
        await websocket.send_json({
            "type": "connected",
            "message": "WebSocket is connected"
        })
        
        while True:
            await asyncio.sleep(10)
            
            # Send demo update
            devices = get_demo()
            await websocket.send_json({
                "type": "update",
                "timestamp": datetime.now().isoformat(),
                "data": devices
            })
            
    except WebSocketDisconnect:
        manager.disconnect(websocket)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)



