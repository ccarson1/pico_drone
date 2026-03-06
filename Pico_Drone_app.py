# Pico_Drone_app.py
# FastAPI + BLE + WebSocket server → live dashboard for PicoDrone MPU6050 data
# Includes "Connect to Drone" button to trigger BLE scan/connection

import asyncio
import json
import struct
import time
from collections import deque
from contextlib import asynccontextmanager
from typing import List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from bleak import BleakScanner, BleakClient
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="PicoDrone Live Dashboard")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# ────────────── Configuration ──────────────
DEVICE_NAME = "PicoDrone"
SERVICE_UUID = "19b10000-e8f2-537e-4f6c-d104768a1214"
TX_UUID = "19b10002-e8f2-537e-4f6c-d104768a1214"

# Shared state
data_history = deque(maxlen=200)  # keep last 200 readings
latest_reading = None
connected_clients: List[WebSocket] = []

# Connection control
connecting = False
connection_task = None


# ────────────── BLE connection task ──────────────
async def connect_to_pico():
    global latest_reading, connecting

    print(f"\n[BLE] Starting scan for {DEVICE_NAME} ...")

    while True:  # retry loop
        try:
            devices = await BleakScanner.discover(timeout=12.0)
            target = next((d for d in devices if d.name == DEVICE_NAME), None)

            if not target:
                print(f"[BLE] Device '{DEVICE_NAME}' not found. Retrying in 5s...")
                await asyncio.sleep(5)
                continue

            print(f"[BLE] Found: {target.address} ({target.name})")

            async with BleakClient(target.address) as client:
                print("[BLE] Connected to PicoDrone!")

                def notification_handler(sender, data):
                    global latest_reading
                    if len(data) != 24:
                        print(f"[BLE] Unexpected data length: {len(data)} bytes")
                        return

                    try:
                        ax, ay, az, gx, gy, gz = struct.unpack("6f", data)
                        timestamp = time.strftime("%H:%M:%S")

                        reading = {
                            "timestamp": timestamp,
                            "accel": {
                                "x": round(ax, 3),
                                "y": round(ay, 3),
                                "z": round(az, 3),
                            },
                            "gyro": {
                                "x": round(gx, 3),
                                "y": round(gy, 3),
                                "z": round(gz, 3),
                            },
                            "level": abs(ax) < 0.15
                            and abs(ay) < 0.15
                            and 0.9 < az < 1.1,
                        }

                        latest_reading = reading
                        data_history.append(reading)

                        asyncio.create_task(broadcast_data(reading))

                        print(
                            f"[{timestamp}] Acc: {ax:6.3f} {ay:6.3f} {az:6.3f} g | "
                            f"Gyro: {gx:6.3f} {gy:6.3f} {gz:6.3f} °/s "
                            f"{'(level)' if reading['level'] else ''}"
                        )

                    except struct.error as e:
                        print(f"[BLE] Unpack error: {e}")

                await client.start_notify(TX_UUID, notification_handler)
                print("[BLE] Notifications enabled")

                # Stay connected until dropped
                await asyncio.sleep(86400)  # long sleep or until exception

        except Exception as e:
            print(f"[BLE] Connection error: {e}")
            print("[BLE] Reconnecting in 5 seconds...")
            await asyncio.sleep(5)

        finally:
            connecting = False


# ────────────── WebSocket broadcast ──────────────
async def broadcast_data(reading: dict):
    if not connected_clients:
        return
    message = json.dumps(reading)
    dead = []
    for ws in connected_clients[:]:
        try:
            await ws.send_text(message)
        except:
            dead.append(ws)
    for ws in dead:
        connected_clients.remove(ws)


# ────────────── Lifespan ──────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Optional: start BLE automatically on server start (comment out if you want button-only)
    # asyncio.create_task(connect_to_pico())
    yield
    print("Shutting down server...")


app.lifespan = lifespan

# ────────────── Routes ──────────────


@app.post("/connect")
async def trigger_connect():
    global connecting, connection_task

    if connecting:
        return {
            "status": "already_connecting",
            "message": "Connection attempt already in progress",
        }

    connecting = True
    print("[API] Web button pressed → starting BLE connection")

    if connection_task and not connection_task.done():
        connection_task.cancel()

    connection_task = asyncio.create_task(connect_to_pico())

    return {
        "status": "connection_started",
        "message": "Starting connection to drone...",
    }

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request}
    )




@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.append(websocket)
    try:
        # Send latest data to new client immediately
        if latest_reading:
            await websocket.send_text(json.dumps(latest_reading))
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        connected_clients.remove(websocket)
