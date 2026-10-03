"""Simulation clock + referee for the MQTT demo.
Usage: python mqtt_world.py --robots 3 --tasks 12 --seed 1 [--blocks] [--delay 0.15] [--kill 1@10]
It (1) injects orders, (2) advances phases and waits for every robot's ack (a barrier), (3) counts collisions from
reported positions, (4) publishes a live snapshot for the dashboard. It never decides who yields or who gets a task."""
import argparse, os, queue, time
from common import Grid, make_tasks, make_blocks
from bus import MqttBus
from world import collisions_between, base_id
from baselines import run_baseline

ap = argparse.ArgumentParser()
ap.add_argument("--robots", type=int, default=3); ap.add_argument("--tasks", type=int, default=12)
ap.add_argument("--seed", type=int, default=1); ap.add_argument("--blocks", action="store_true")
ap.add_argument("--kill", default=None, help="robot@tick, e.g. 1@10"); ap.add_argument("--delay", type=float, default=0.15)
ap.add_argument("--max-ticks", type=int, default=600)
a = ap.parse_args()

g, n = Grid(), a.robots
tasks = make_tasks(g, a.tasks, a.seed)
blocks = make_blocks(g, tasks, a.seed) if a.blocks else []
bus = MqttBus(os.getenv("MQTT_HOST", "127.0.0.1"), client_id="world")
seq, events = 0, []


def barrier(phase, t=0, **kw):
    global seq
    seq += 1
    bus.publish({"type": "phase", "src": -1, "phase": phase, "t": t, "seq": seq, **kw})
    acks = {}
    while len(acks) < n:
        m = bus.get(timeout=30)
        if m["type"] == "ack" and m["seq"] == seq: acks[m["src"]] = m
        elif m["type"] == "evt": events.append(m)
    return acks


print(f"waiting for {n} robots..."); hello = set()
while len(hello) < n:
    bus.publish({"type": "ping", "src": -1})                   # robots answer 'hello' -> no start-order problems
    try:
        m = bus.get(timeout=0.5)
        if m["type"] == "hello": hello.add(m["src"])
    except queue.Empty: pass
barrier("init")
for tk in tasks: bus.publish({"type": "task", "src": -1, **tk})
barrier("sync")

pos, blocked, pend, done, collisions, makespan = {}, set(), sorted(blocks), set(), 0, None
kill = tuple(map(int, a.kill.split("@"))) if a.kill else None
for t in range(a.max_ticks):
    for b in list(pend):
        if b[0] <= t and all(p != b[1] for p in pos.values()):
            pend.remove(b); blocked.add(b[1]); bus.publish({"type": "blocked", "src": -1, "cell": list(b[1])})
    if kill and kill[1] <= t: barrier("kill", t, target=kill[0]); kill = None
    barrier("sync", t)
    for _ in range(2 * n + 2):                                   # allocation rounds
        c1 = any(x["changed"] for x in barrier("claim", t).values())
        c2 = any(x["changed"] for x in barrier("resolve", t).values())
        if not (c1 or c2): break
    for _ in range(n + 3):                                       # planning rounds
        barrier("plan", t)
        if not any(x["pending"] for x in barrier("sync", t).values()): break
    acks = barrier("move", t)
    new = {i: (x["x"], x["y"]) for i, x in acks.items()}
    if pos: collisions += collisions_between(pos, new)
    pos = new
    conflicts = [e["cell"] for e in events if e["kind"] == "yield" and e["t"] == t]
    for e in events:
        if e["kind"] == "done": done.add(base_id(e["tid"]))
    log = [f"t={e['t']} R{e['robot']} {e['kind']} {e.get('tid', '')}" for e in events[-8:]]
    bus.publish_to("swarm/state", {"t": t, "robots": sorted(acks.values(), key=lambda x: x["id"]),
                                   "blocked": [list(c) for c in blocked], "conflicts": conflicts,
                                   "collisions": collisions, "done": len(done), "total": len(tasks), "log": log,
                                   "map": [list(c) for c in g.free]})
    time.sleep(a.delay)
    if len(done) == len(tasks): makespan = t + 1; break

base = run_baseline(g, tasks, n, "central", blocks=blocks); unc = run_baseline(g, tasks, n, "uncoord", blocks=blocks)
rep = {"swarm_makespan": makespan, "swarm_collisions": collisions, "tasks_done": len(done), "tasks_total": len(tasks),
       "central_makespan": base["makespan"], "central_collisions": base["collisions"],
       "uncoordinated_collisions": unc["collisions"],
       "improvement_pct": round(100 * (base["makespan"] - makespan) / base["makespan"], 1) if makespan else None,
       "robots": n, "seed": a.seed}
bus.publish_to("swarm/report", rep, retain=True)
print("REPORT", rep)
