"""One robot's brain. Everything here uses ONLY (a) the static map, (b) messages heard on the bus.
There is no shared state and no coordinator: this is the decentralized part of SwarmSync."""
from common import Res, conflict, st_astar

HOLD_PRIO = 1000        # a robot standing still is physically there, so it always wins
AGING = 0.02            # priority aging: +0.02 per waiting tick -> no starvation
REBROADCAST = 4         # heartbeat: re-send active reservation every N ticks (message-loss recovery)


class Agent:
    def __init__(self, rid, grid, home, bus, depth=2):
        self.id, self.grid, self.home, self.bus, self.depth = rid, grid, home, bus, depth
        self.pos, self.t = home, 0
        self.blocked = frozenset()
        self.table = {}                      # other robots' reservations (what I have heard)
        self.open, self.claims = {}, {}      # open tasks, claims heard per task
        self.queue, self.picked = [], False  # my tasks (max `depth`), is queue[0] already on board
        self.targets, self.arr = [], []      # [(kind,cell,tid)] and arrival time of each
        self.pending_claim = None
        self.need_plan = self.staging = self.stuck = self.dead = False
        self.waited = 0; self.moved = False; self.yield_t = -99
        self.battery = 100.0
        self.events = []
        self.stats = {"yields": 0, "replans": 0, "reroutes": 0, "staged": 0, "released": 0}
        self.res = Res(rid, 0, [home], HOLD_PRIO, 0)

    # ---------------------------------------------------------------- helpers
    def publish(self, m): self.bus.publish({**m, "src": self.id})
    def publish_res(self): self.bus.publish(self.res.to_msg())
    def emit(self, kind, **kw): self.events.append({"t": self.t, "robot": self.id, "kind": kind, **kw})

    def eligible_open(self):
        return [t for t in self.open.values() if self.id not in t["excl"]]

    def rebuild_targets(self):
        if self.staging:
            self.targets = [("stage", self.grid.staging, self.queue[0]["id"])]
        else:
            tg = []
            for i, tk in enumerate(self.queue):
                if not (i == 0 and self.picked): tg.append(("pick", tk["pickup"], tk["id"]))
                tg.append(("drop", tk["drop"], tk["id"]))
            self.targets = tg

    def reopen(self, m):
        tk = {"id": m["id"], "pickup": tuple(m["pickup"]), "drop": tuple(m["drop"]),
              "prio": m["prio"], "excl": list(m.get("excl", []))}
        self.open[tk["id"]] = tk; self.claims.pop(tk["id"], None)

    def release(self, tk):
        """Put a task back on the network (Case A / leftovers) - broadcast-and-claim."""
        self.publish({"type": "task", **tk}); self.reopen(tk); self.stats["released"] += 1
        self.emit("released", tid=tk["id"])

    # ---------------------------------------------------------------- messages
    def on_msg(self, m):
        if self.dead: return
        ty = m["type"]
        if ty == "task": self.reopen(m)
        elif ty == "claim":
            self.claims.setdefault(m["tid"], {})[m["src"]] = tuple(m["key"])
        elif ty == "res":
            other = Res.from_msg(m); self.table[other.rid] = other
            c = conflict(self.res, other)
            if c and other.key() > self.res.key():          # I lose the segment -> yield & replan
                self.need_plan = True; self.yield_t = self.t; self.stats["yields"] += 1
                self.emit("yield", cell=list(c), to=other.rid)
        elif ty == "unblocked":
            self.blocked = self.blocked - {tuple(m["cell"])}
            if self.stuck or self.targets: self.need_plan = True
        elif ty == "blocked" or ty == "dead":
            self.blocked = self.blocked | {tuple(m["cell"])}
            if ty == "dead": self.table.pop(m["src"], None)
            self.check_path_blocked()

    def check_path_blocked(self):
        i = max(0, self.t - self.res.t0)
        if not any(c in self.blocked for c in self.res.path[i:]): return
        if self.picked or (not self.queue):          # Case B (loaded) or homing: re-route
            self.need_plan = True; self.stats["reroutes"] += 1
        else:                                       # Case A: nothing on board -> broadcast task, nearest claims
            for tk in self.queue: self.release(tk)
            self.queue, self.targets, self.arr = [], [], []
            self.need_plan = True

    # ---------------------------------------------------------------- phases (driven by the world / MQTT barrier)
    def on_phase(self, phase, t):
        self.t = t; ch = False
        if not self.dead:
            if phase == "claim": ch = self.phase_claim()
            elif phase == "resolve": ch = self.phase_resolve()
            elif phase == "plan": ch = self.phase_plan()
            elif phase == "move": self.step()
        return {"changed": ch, "pending": self.need_plan and not self.dead, **self.snapshot()}

    def phase_claim(self):
        if self.staging or self.pending_claim or len(self.queue) >= self.depth: return False
        cands = self.eligible_open()
        if not cands: return False
        ref = self.queue[-1]["drop"] if self.queue else self.pos
        dist = lambda tk: self.grid.dist_map(tk["pickup"], self.blocked).get(ref, 10**6)
        tk = min(cands, key=lambda k: (dist(k), k["id"]))
        key = (dist(tk), -self.id)                   # nearest wins; tie -> higher id wins (lower yields)
        self.pending_claim = tk["id"]
        self.claims.setdefault(tk["id"], {})[self.id] = key
        self.publish({"type": "claim", "tid": tk["id"], "key": list(key)})
        return True

    def phase_resolve(self):
        ch = False
        for tid, cl in list(self.claims.items()):
            if tid not in self.open: continue
            winner = min(cl, key=lambda r: cl[r])    # every robot computes the same winner locally
            tk = self.open.pop(tid); ch = True
            if winner == self.id:
                self.queue.append(tk); self.pending_claim = None
                self.rebuild_targets(); self.need_plan = True
                self.emit("claimed", tid=tid)
            elif self.pending_claim == tid:
                self.pending_claim = None
        return ch

    def phase_plan(self):
        if (not self.need_plan and not self.targets and not self.queue and self.pos != self.home
                and not self.eligible_open()):
            self.need_plan = True                    # nothing to do -> go home to the bay
        if not self.need_plan: return False
        self.need_plan = False
        return self.plan()

    def plan(self):
        if not self.targets and not self.queue and self.pos != self.home and not self.eligible_open():
            self.targets = [("home", self.home, None)]
        if not self.targets: return self.hold()
        path, arr = st_astar(self.grid, self.pos, self.t, [g[1] for g in self.targets],
                             self.blocked, list(self.table.values()))
        if path is None: return self.plan_failed()
        prio = HOLD_PRIO if len(path) == 1 else (self.queue[0]["prio"] if self.queue else 0.5) + AGING * min(self.waited, 200)
        self.res = Res(self.id, self.t, path, prio, self.t)
        self.arr, self.stuck = arr, False
        self.stats["replans"] += 1
        self.publish_res(); self.process_arrivals()
        return True

    def hold(self):
        self.res = Res(self.id, self.t, [self.pos], HOLD_PRIO, self.t)
        self.stuck = bool(self.targets); self.publish_res(); return True

    def plan_failed(self):
        if self.picked and self.queue and not self.staging:
            # Case B: loaded and no alternate path -> fall back to the staging / hand-off point
            for tk in self.queue[1:]: self.release(tk)
            self.queue = self.queue[:1]; self.staging = True
            self.rebuild_targets(); self.emit("no_route_to_staging", tid=self.queue[0]["id"])
            return self.plan()
        if self.queue and not self.picked:
            for tk in self.queue:                    # Case A: give the task back, excluding myself
                fleet = set(self.table) | {self.id}
                ex = set(tk["excl"]) | {self.id}
                tk["excl"] = [] if ex >= fleet else sorted(ex)      # everyone failed -> forget, retry later
                self.release(tk)
            self.queue, self.targets, self.arr = [], [], []
        return self.hold()

    # ---------------------------------------------------------------- execution
    def step(self):
        nxt = self.res.at(self.t + 1)
        self.moved = nxt != self.pos
        self.battery = max(0.0, self.battery - (0.08 if self.moved else 0.01))
        self.pos = nxt; self.t += 1
        self.waited = 0 if self.moved else (self.waited + 1 if self.queue else 0)
        if self.stuck: self.need_plan = True
        self.process_arrivals()
        if self.t % REBROADCAST == 0 and len(self.res.path) > 1: self.publish_res()

    def process_arrivals(self):
        while self.targets and self.arr and self.arr[0] <= self.t:
            kind, cell, tid = self.targets.pop(0); self.arr.pop(0)
            if kind == "pick": self.picked = True; self.emit("pick", tid=tid)
            elif kind == "drop":
                self.queue.pop(0); self.picked = False; self.emit("done", tid=tid)
            elif kind == "stage":
                tk = self.queue.pop(0); self.picked = self.staging = False
                new = {**tk, "id": tk["id"] + "~S", "pickup": self.grid.staging, "excl": []}
                self.publish({"type": "task", **new}); self.reopen(new)
                self.stats["staged"] += 1; self.emit("staged", tid=tk["id"])

    def die(self):
        """Battery / hardware failure: stop broadcasting, become a static obstacle, return unloaded tasks."""
        self.dead = True
        if not self.picked:
            for tk in self.queue: self.release(tk)
        self.queue, self.targets = [], []
        self.publish({"type": "dead", "cell": list(self.pos)}); self.emit("dead")

    def snapshot(self):
        if self.dead: st = "dead"
        elif self.t - self.yield_t <= 2: st = "yielding"
        elif self.queue and not self.moved: st = "waiting"
        elif self.moved: st = "moving"
        else: st = "parked" if self.pos == self.home else "idle"
        return {"id": self.id, "x": self.pos[0], "y": self.pos[1], "battery": round(self.battery, 1), "state": st,
                "task": self.queue[0]["id"] if self.queue else None, "carrying": self.picked, "moved": self.moved}
