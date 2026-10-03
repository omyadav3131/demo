"""In-process simulator for the SwarmSync (decentralized) mode. The world only:
   (1) injects warehouse orders and blockages, (2) moves nothing itself - robots move themselves,
   (3) OBSERVES positions to count collisions. It makes no coordination decisions."""
from agent import Agent
from bus import InProcessBus


def base_id(tid): return tid.split("~")[0]


def collisions_between(old, new):
    n, ids = 0, list(old)
    for a in range(len(ids)):
        for b in range(a + 1, len(ids)):
            i, j = ids[a], ids[b]
            if new[i] == new[j]: n += 1
            elif old[i] == new[j] and old[j] == new[i] and old[i] != new[i]: n += 1   # head-on swap
    return n


def run_swarm(grid, tasks, n, depth=2, loss=0.0, blocks=(), kill=None, seed=0,
              max_ticks=700, on_tick=None):
    bus = InProcessBus(loss, seed)
    agents = [Agent(i, grid, grid.bays[i], bus, depth) for i in range(n)]
    for a in agents: bus.subscribe(a.id, a.on_msg)
    for a in agents: a.publish_res()
    for tk in tasks: bus.publish({"type": "task", "src": -1, **tk})
    bus.flush()

    done, collisions, wait_ticks, idle_streak, deadlock = set(), 0, 0, 0, False
    blocked, pending_blocks, all_events, clears = set(), sorted(blocks), [], []
    total = len(tasks); makespan = None
    for t in range(max_ticks):
        # -- warehouse events (aisle becomes blocked) ---------------------------------
        for b in list(pending_blocks):
            bt, cell = b[0], b[1]
            if bt <= t and all(a.pos != cell for a in agents):
                pending_blocks.remove(b); blocked.add(cell)
                bus.publish({"type": "blocked", "src": -1, "cell": list(cell)})
                if len(b) > 2: clears.append((b[2], cell))
        for b in list(clears):
            if b[0] <= t:
                clears.remove(b); blocked.discard(b[1])
                bus.publish({"type": "unblocked", "src": -1, "cell": list(b[1])})
        if kill and kill[1] <= t and not agents[kill[0]].picked and not agents[kill[0]].dead:
            agents[kill[0]].die(); blocked.add(agents[kill[0]].pos)
        bus.flush()

        # -- Phase 1: task allocation (broadcast-and-claim), rounds until stable ------
        for _ in range(2 * n + 2):
            ch = [a.on_phase("claim", t)["changed"] for a in agents]
            bus.flush()
            ch2 = [a.on_phase("resolve", t)["changed"] for a in agents]
            if not any(ch) and not any(ch2): break
        # -- Phase 2: reservation planning; conflicts detected on receipt, losers replan
        for _ in range(n + 3):
            out = [a.on_phase("plan", t) for a in agents]
            bus.flush()
            if not any(a.need_plan and not a.dead for a in agents): break
        # -- Phase 3: everybody executes its own reservation --------------------------
        old = {a.id: a.pos for a in agents}
        for a in agents: a.on_phase("move", t)
        new = {a.id: a.pos for a in agents}
        collisions += collisions_between(old, new)
        wait_ticks += sum(1 for a in agents if a.queue and not a.moved and not a.dead)
        for a in agents:
            for e in a.events:
                if e["kind"] == "done": done.add(base_id(e["tid"]))
            all_events += a.events; a.events = []
        if on_tick: on_tick(t, agents, blocked, collisions, len(done), total)
        if len(done) == total: makespan = t + 1; break
        idle_streak = 0 if any(a.moved for a in agents) or pending_blocks or clears else idle_streak + 1
        if idle_streak > 60: deadlock = True; break
    return {"mode": "swarm", "makespan": makespan or max_ticks, "done": len(done), "total": total,
            "collisions": collisions, "wait_ticks": wait_ticks, "deadlock": deadlock or makespan is None,
            "msgs": bus.sent, "dropped": bus.dropped,
            "yields": sum(a.stats["yields"] for a in agents), "replans": sum(a.stats["replans"] for a in agents),
            "reroutes": sum(a.stats["reroutes"] for a in agents), "staged": sum(a.stats["staged"] for a in agents),
            "released": sum(a.stats["released"] for a in agents), "events": all_events}
