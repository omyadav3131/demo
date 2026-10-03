"""Baselines the swarm is compared against. Same map, same tasks, same nearest-task assignment rule.
  uncoord : every robot follows its own A* path, no coordination at all  -> shows collisions happen
  central : ONE server grants each move; denied robot must stop and wait (stop-and-wait)"""
from common import astar
from world import collisions_between


def run_baseline(grid, tasks, n, mode="central", penalty=2, patience=6, blocks=(), max_ticks=700):
    pos = {i: grid.bays[i] for i in range(n)}
    open_ = [dict(t) for t in tasks]
    job = {i: None for i in range(n)}; carrying = {i: False for i in range(n)}
    path = {i: [] for i in range(n)}; cool = {i: 0 for i in range(n)}; streak = {i: 0 for i in range(n)}
    blocked, pending = set(), sorted(blocks)
    done, collisions, wait_ticks, stall = 0, 0, 0, 0

    def goal(i): return job[i]["drop"] if carrying[i] else job[i]["pickup"] if job[i] else grid.bays[i]
    def replan(i, extra=frozenset()):
        p = astar(grid, pos[i], goal(i), frozenset(blocked) | extra)
        if p is not None: path[i] = p
        return p is not None

    for t in range(max_ticks):
        for bt, c in list(pending):
            if bt <= t and c not in pos.values():
                pending.remove((bt, c)); blocked.add(c)
                for i in range(n):
                    if c in path[i]: replan(i)
        for i in range(n):                              # central assignment: nearest open task
            if job[i] is None and open_:
                tk = min(open_, key=lambda k: (abs(k["pickup"][0]-pos[i][0]) + abs(k["pickup"][1]-pos[i][1]), k["id"]))
                open_.remove(tk); job[i] = tk; carrying[i] = False; replan(i)
            elif job[i] is None and pos[i] != grid.bays[i] and not path[i]:
                replan(i)
        old, want = dict(pos), {}
        for i in range(n):
            if path[i]: want[i] = path[i][0]
        if mode == "uncoord":
            for i, c in want.items(): pos[i] = c; path[i].pop(0)
        else:                                           # centralized stop-and-wait
            occupied, taken, moved = set(pos.values()), set(), 0
            for i in sorted(want):
                if cool[i] > 0: cool[i] -= 1; wait_ticks += job[i] is not None; continue
                c = want[i]
                if c in occupied or c in taken:         # denied: stop and wait for a fresh grant
                    cool[i] = penalty; streak[i] += 1; wait_ticks += job[i] is not None
                    if streak[i] >= patience:           # server timeout -> re-route around parked robots
                        replan(i, frozenset(pos[j] for j in pos if j != i) - {goal(i)}); streak[i] = 0
                else:
                    taken.add(c); pos[i] = c; path[i].pop(0); streak[i] = 0; moved += 1
            stall = 0 if moved else stall + 1
            if stall >= 4:                              # server-side deadlock breaker: lowest-id stuck robot backs off
                for i in sorted(want):
                    others = frozenset(pos[j] for j in pos if j != i) - {goal(i)}
                    if replan(i, others) and path[i] and path[i][0] not in occupied:
                        pos[i] = path[i].pop(0); stall = 0; break
                    free = [c for c in grid.nbrs(pos[i], blocked) if c not in occupied]
                    if free:                            # no detour exists: retreat one cell, then re-plan
                        pos[i] = free[0]; replan(i); stall = 0; break
        collisions += collisions_between(old, pos)
        for i in range(n):
            if job[i] and pos[i] == goal(i) and not path[i]:
                if not carrying[i]: carrying[i] = True; replan(i)
                else: done += 1; job[i] = None; carrying[i] = False
        if done == len(tasks):
            return {"mode": mode, "makespan": t + 1, "done": done, "total": len(tasks), "collisions": collisions,
                    "wait_ticks": wait_ticks, "deadlock": False}
        if stall > 80:
            break
    return {"mode": mode, "makespan": max_ticks, "done": done, "total": len(tasks), "collisions": collisions,
            "wait_ticks": wait_ticks, "deadlock": True}
