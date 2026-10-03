"""ONE robot = ONE process. Usage: python mqtt_robot.py <robot_id>
It hears only the shared MQTT topic; it never talks to a coordinator. The 'phase' messages are just a simulation
clock (so the demo is repeatable) - they carry no decisions."""
import os, sys, time
from common import Grid
from agent import Agent
from bus import MqttBus

rid = int(sys.argv[1])
g = Grid()
bus = MqttBus(os.getenv("MQTT_HOST", "127.0.0.1"), client_id=f"robot-{rid}")
agent = Agent(rid, g, g.bays[rid], bus, int(os.getenv("DEPTH", "1")))
time.sleep(1.0)
bus.publish({"type": "hello", "src": rid})
print(f"robot {rid} online at bay {g.bays[rid]}", flush=True)

while True:
    m = bus.get()
    if m.get("src") == rid: continue                       # ignore my own echo
    ty = m["type"]
    if ty == "phase":
        if m["phase"] == "init": agent.publish_res(); r = agent.snapshot() | {"changed": False, "pending": False}
        elif m["phase"] == "kill":
            if m["target"] == rid: agent.die()
            r = {"changed": False, "pending": False, **agent.snapshot()}
        else: r = agent.on_phase(m["phase"], m["t"])
        for e in agent.events: bus.publish({"type": "evt", "src": rid, **e})
        agent.events = []
        bus.publish({"type": "ack", "src": rid, "seq": m["seq"], **r})
    elif ty == "ping": bus.publish({"type": "hello", "src": rid})
    elif ty in ("task", "claim", "res", "blocked", "unblocked", "dead"):
        agent.on_msg(m)
