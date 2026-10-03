"""Two interchangeable message buses. Agents only see publish()/on_msg(), so the SAME agent code
runs in-process (fast benchmarks) and over real MQTT (separate processes)."""
import json, queue, random

COUNTED = ("res", "claim", "task")


class InProcessBus:
    def __init__(self, loss=0.0, seed=0):
        self.subs, self.q, self.loss = {}, [], loss
        self.rnd = random.Random(seed)
        self.sent = self.dropped = 0

    def subscribe(self, rid, cb): self.subs[rid] = cb

    def publish(self, msg):
        if msg["type"] in COUNTED: self.sent += 1
        self.q.append(json.loads(json.dumps(msg)))      # force JSON round-trip, exactly like MQTT

    def flush(self):
        """Deliver everything queued so far (one 'network round')."""
        batch, self.q = self.q, []
        for m in batch:
            for rid, cb in self.subs.items():
                if rid == m["src"]: continue
                if self.loss and m["type"] in COUNTED and self.rnd.random() < self.loss:
                    self.dropped += 1; continue
                cb(m)
        return len(batch)


class MqttBus:
    """All robots share ONE topic on a LOCAL Mosquitto broker. A single topic gives every subscriber
    the same total order of messages, which the phase barrier in mqtt_world.py relies on."""
    TOPIC = "swarm/bus"

    def __init__(self, host="localhost", port=1883, client_id=""):
        import paho.mqtt.client as mqtt
        self.inbox = queue.Queue()
        self.c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
        self.c.on_message = lambda cl, ud, msg: self.inbox.put(json.loads(msg.payload))
        self.c.connect(host, port)
        self.c.subscribe(self.TOPIC, qos=1)
        self.c.loop_start()

    def publish(self, msg): self.c.publish(self.TOPIC, json.dumps(msg), qos=1)

    def publish_to(self, topic, msg, retain=False):      # side channels (dashboard feed), not part of the robot bus
        self.c.publish(topic, json.dumps(msg), qos=1, retain=retain)

    def get(self, timeout=None): return self.inbox.get(timeout=timeout)
