from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import asyncio
from datetime import datetime

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
    devices = [
        {"id": "1", "name": "Router-1", "ip": "192.168.1.1", "status": "online"},
        {"id": "2", "name": "Switch-1", "ip": "192.168.1.10", "status": "online"},
        {"id": "3", "name": "Firewall-1", "ip": "192.168.1.2", "status": "warning"}
    ]
    return {"data": devices}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    
    try:
        await websocket.send_json({
            "type": "connected",
            "message": "WebSocket is connected"
        })
        
        while True:
            await asyncio.sleep(10)
            
            # Send demo update
            await websocket.send_json({
                "type": "update",
                "timestamp": datetime.now().isoformat(),
                "data": {"message": "Timely update"}
            })
            
    except WebSocketDisconnect:
        active_connections.remove(websocket)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)



