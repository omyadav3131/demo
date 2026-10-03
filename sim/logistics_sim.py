import time, os, json, random
import paho.mqtt.client as mqtt

broker = os.getenv("MQTT_HOST", "127.0.0.1")
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="logistics_sim")
client.connect(broker, 1883)
client.loop_start()

drivers = ["J. Smith", "M. Jones", "B. Colawn", "D. Lee", "B. Chen"]
types = ["Semi", "Box Truck", "Van"]
locations = ["Dock 4", "Main St", "Current Area", "Dock 2", "Elm St", "Route B"]

# Generate initial fleet
fleet = [
    {"id": "FL-101", "type": "Semi", "status": "Active", "driver": "J. Smith", "loc": "Dock 4", "time": "10s ago", "x": 3, "y": 0, "dock": "Dock 4 - R200"},
    {"id": "R-219", "type": "Box Truck", "status": "En Route", "driver": "M. Jones", "loc": "Main St", "time": "1min ago", "x": 2, "y": 0, "dock": "Dock 4 - R219"},
    {"id": "L-205", "type": "Van", "status": "Maintenance", "driver": "B. Colawn", "loc": "Current Area", "time": "10s ago", "x": 5, "y": 1, "dock": "Grid B - L805"},
    {"id": "FL-102", "type": "Van", "status": "Active", "driver": "J. Smith", "loc": "Dock 2", "time": "10s ago", "x": 1, "y": 0, "dock": None},
    {"id": "L-203", "type": "Van", "status": "Maintenance", "driver": "B. Colawn", "loc": "Current Area", "time": "10m ago", "x": 0, "y": 2, "dock": "Grid C - L805"},
    {"id": "L-805", "type": "Semi", "status": "En Route", "driver": "D. Lee", "loc": "Route B", "time": "2m ago", "x": 3, "y": 3, "dock": "Grid C - L805"}
]

feed = [
    {"driver": "D. Lee (Semi)", "msg": "Cleared from Bay 2, proceeding to Route B.", "time": "2m ago", "sys": False},
    {"driver": "SYSTEM", "msg": "Fleet Map optimized for increased traffic.", "time": "5m ago", "sys": True},
    {"driver": "B. Chen (Van)", "msg": "Stuck in local traffic on Elm St. Estimated delay: 15 mins.", "time": "10m ago", "sys": False}
]

tick = 0
while True:
    tick += 1
    # occasionally update time or locations
    for v in fleet:
        if v["status"] == "En Route" and random.random() < 0.1:
            v["time"] = "Just now"
    
    state = {
        "t": tick, "collisions": 0, "done": 0, "total": 42, # to satisfy java backend
        "fleet": fleet,
        "feed": feed,
        "kpis": { "total": 42, "en_route": 28, "maintenance": 3 }
    }
    client.publish("swarm/state", json.dumps(state), qos=1)
    time.sleep(1)
