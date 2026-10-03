import asyncio
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import paho.mqtt.client as mqtt
import threading

app = FastAPI()

# Store latest state and report
store = {"state": None, "report": None}
connected_clients = set()
loop = None

# Read index.html
with open("backend/src/main/resources/static/index.html", "r", encoding="utf-8") as f:
    html_content = f.read()

@app.on_event("startup")
def startup_event():
    global loop
    loop = asyncio.get_running_loop()

@app.get("/")
async def get():
    return HTMLResponse(html_content)

@app.websocket("/ws/fleet")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.add(websocket)
    try:
        if store["state"]:
            await websocket.send_text(store["state"])
        if store["report"]:
            await websocket.send_text(json.dumps({"report": store["report"]}))
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        connected_clients.remove(websocket)

def on_connect(client, userdata, flags, rc, properties=None):
    client.subscribe("swarm/state", qos=1)
    client.subscribe("swarm/report", qos=1)

def on_message(client, userdata, msg):
    topic = msg.topic
    payload = msg.payload.decode('utf-8')
    if topic == "swarm/state":
        store["state"] = payload
        # Broadcast
        for ws in list(connected_clients):
            if loop:
                asyncio.run_coroutine_threadsafe(ws.send_text(payload), loop)
    elif topic == "swarm/report":
        store["report"] = json.loads(payload)
        for ws in list(connected_clients):
            if loop:
                asyncio.run_coroutine_threadsafe(ws.send_text(json.dumps({"report": store["report"]})), loop)

mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="fastapi-backend")
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message
mqtt_client.connect("localhost", 1883)
mqtt_client.loop_start()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
