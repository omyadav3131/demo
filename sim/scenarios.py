"""Hand-built scenarios that exercise each of the three PS capabilities. Run: python scenarios.py"""
from common import Grid
from world import run_swarm

g = Grid()
def T(i, p, d, prio=1): return {"id": f"T{i}", "pickup": p, "drop": d, "prio": prio, "excl": []}

print("1) HEAD-ON in a 1-wide aisle + simultaneous claims (tie-breaker / deadlock resolution)")
r = run_swarm(g, [T(0, (1, 4), (17, 4)), T(1, (17, 4), (1, 4))], 2, depth=1)
print("   makespan", r["makespan"], "collisions", r["collisions"], "yields", r["yields"], "deadlock", r["deadlock"])

print("2) CASE A - unloaded robot, aisle blocked -> task broadcast & re-claimed")
r = run_swarm(g, [T(0, (17, 7), (1, 7))], 3, depth=1, blocks=[(3, (9, 7)), (3, (13, 7))])
print("   done", r["done"], "released", r["released"], "collisions", r["collisions"], "makespan", r["makespan"])

print("3) CASE B - LOADED robot, aisle blocked -> re-route (alternate path exists)")
r = run_swarm(g, [T(0, (1, 1), (17, 7))], 1, depth=1, blocks=[(4, (10, 1)), (4, (17, 4))])
print("   done", r["done"], "reroutes", r["reroutes"], "staged", r["staged"], "collisions", r["collisions"], "makespan", r["makespan"])

print("4) CASE B fallback - loaded robot, destination cut off -> staging hand-off, finished after it re-opens")
cut = [(6, (16, 7), 60), (6, (17, 6), 60)]
r = run_swarm(g, [T(0, (1, 1), (17, 7))], 2, depth=1, blocks=cut)
print("   done", r["done"], "staged", r["staged"], "collisions", r["collisions"], "makespan", r["makespan"], "deadlock", r["deadlock"])
print("   ", [(e["t"], e["robot"], e["kind"], e.get("tid")) for e in r["events"] if e["kind"] in ("no_route_to_staging", "staged", "done")])

print("5) BATTERY FAILURE of an unloaded robot -> it becomes an obstacle, its tasks re-enter the queue")
from common import make_tasks
r = run_swarm(g, make_tasks(g, 10, 3), 3, depth=1, kill=(1, 3))
print("   done", r["done"], "/", r["total"], "released", r["released"], "collisions", r["collisions"], "makespan", r["makespan"])

print("6) MESSAGE LOSS 10% with heartbeat re-broadcast (experiment - collisions are reported, not hidden)")
tot = 0
for seed in range(10):
    r = run_swarm(g, make_tasks(g, 12, seed), 3, depth=1, loss=0.10, seed=seed); tot += r["collisions"]
print("   collisions over 10 runs:", tot)
