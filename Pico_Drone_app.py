# Pico_Drone_app.py
# FastAPI + BLE + WebSocket server → live dashboard for PicoDrone MPU6050 data
# Includes "Connect to Drone" button to trigger BLE scan/connection

import asyncio
from http import client
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
ble_client: BleakClient | None = None

# ────────────── Configuration ──────────────
DEVICE_NAME = "PicoDrone"
SERVICE_UUID = "19b10000-e8f2-537e-4f6c-d104768a1214"
RX_UUID = "19b10001-e8f2-537e-4f6c-d104768a1214"
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

    while connecting:  # retry loop
        try:
            devices = await BleakScanner.discover(timeout=12.0)
            target = next((d for d in devices if d.name == DEVICE_NAME), None)

            if not target:
                print(f"[BLE] Device '{DEVICE_NAME}' not found. Retrying in 5s...")
                await asyncio.sleep(5)
                continue

            print(f"[BLE] Found: {target.address} ({target.name})")

            async with BleakClient(target.address) as client:
                global ble_client
                ble_client = client
                print("[BLE] Connected to PicoDrone!")

                def notification_handler(sender, data):
                    global latest_reading, ble_client

                    if ble_client is None or not ble_client.is_connected:
                        return

                    # ---------- Check for text status messages ----------
                    try:
                        text = data.decode().strip()

                        if text in ["calibrating", "calibrated"]:
                            print(f"[BLE STATUS] {text}")
                            return

                    except:
                        pass


                    # ---------- Handle normal sensor packet ----------
                    FORMAT = "8fB4B64s"
                    SIZE = struct.calcsize(FORMAT)
                    if len(data) != SIZE:
                        print(f"[BLE] Unexpected size: {len(data)}")
                        return

                    try:
                        unpacked = struct.unpack(FORMAT, data)
                        ax, ay, az, gx, gy, gz, heading, distance, battery, m1, m2, m3, m4, log_bytes = unpacked
                        
                        log_message = log_bytes.decode("utf-8").rstrip('\x00')
                        #print(log_message)
                        timestamp = time.strftime("%H:%M:%S")

                        if log_message:
                            log_message = f"[DRONE {timestamp}] {log_message}"

                        reading = {
                            "timestamp": timestamp,
                            "accel": {"x": round(ax,3), "y": round(ay,3), "z": round(az,3)},
                            "gyro": {"x": round(gx,3), "y": round(gy,3), "z": round(gz,3)},
                            "heading": heading,
                            "distance": distance,
                            "battery": battery,
                            "motors": {
                                "motor1": m1,
                                "motor2": m2,
                                "motor3": m3,
                                "motor4": m4,
                            },
                            "log": log_message
                        }

                        #print(f"[BLE] Battery: {battery}%")
                        #print("Heading:", round(heading,1))
                        #print("Distance:", distance, "mm")
                        if log_message:

                            print(f"[DRONE {timestamp}] {log_message}")

                        latest_reading = reading
                        data_history.append(reading)

                        asyncio.create_task(broadcast_data(reading))

                    except struct.error as e:
                        print(f"[BLE] Unpack error: {e}")

                await client.start_notify(TX_UUID, notification_handler)
                print("[BLE] Notifications enabled")

                # Stay connected until dropped
                await asyncio.sleep(86400)  # long sleep or until exception

        except Exception as e:
            print(f"[BLE] Connection error: {e}")

            if not connecting:
                break

            print("[BLE] Reconnecting in 5 seconds...")
            await asyncio.sleep(5)

        # finally:
        #     connecting = False


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

@app.post("/disconnect")
async def disconnect_drone():
    global ble_client, connection_task, connecting

    print("[API] Disconnect requested")

    connecting = False

    if ble_client and ble_client.is_connected:
        try:
            await ble_client.stop_notify(TX_UUID)
        except:
            pass

        await ble_client.disconnect()

    if connection_task and not connection_task.done():
        connection_task.cancel()

    ble_client = None
    connection_task = None

    return {"status": "disconnected"}

    
#calibrate
@app.post("/calibrate")
async def calibrate_drone():
    global ble_client

    print("[API] Calibrate requested")

    if ble_client and ble_client.is_connected:
        try:
            # Send a specific command to trigger calibration (e.g., 0xFF)
            await ble_client.write_gatt_char(RX_UUID, bytes([0xFF]), response=False)
            print("[API] Sent calibrate command")
            return {"status": "calibrate_command_sent"}
        except Exception as e:
            print(f"[API] Error sending calibrate command: {e}")
            return {"status": "error", "message": str(e)}
    else:
        print("[API] Cannot calibrate - BLE not connected")
        return {"status": "error", "message": "Not connected to drone"}




@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request}
    )

@app.websocket("/controls")
async def controls_websocket(websocket: WebSocket):
    await websocket.accept()
    print("[WebSocket] Control client connected")

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)

            # if not ble_client or not ble_client.is_connected:
            #     continue  # skip if not connected

            #print(f"[WebSocket] Received control message: {msg}")
            # Send wheel
            if msg.get("type") == "wheel":
                wheel_value = msg["value"]
                if ble_client and ble_client.is_connected:
                    await ble_client.write_gatt_char(RX_UUID, bytes([wheel_value]), response=False)
                    #print(f"[WebSocket] Sent wheel command: {wheel_value}")
                else:
                    print("BLE not connected")
                

            # Send keys
            elif msg.get("key"):
                key = msg["key"]
                state = msg["state"]
                # convert to a single byte or small JSON-like payload
                payload = json.dumps({"key": key, "state": state}).encode()
                if ble_client and ble_client.is_connected:
                    await ble_client.write_gatt_char(RX_UUID, payload, response=False)
                    print(f"[WebSocket] Sent key command: {key} = {state}")
                else:
                    print("BLE not connected")

    except WebSocketDisconnect:
        print("[WebSocket] Control client disconnected")

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
