"""Warehouse map, static A*, space-time A* and reservation objects."""
import heapq, itertools, random
from collections import deque
from dataclasses import dataclass

MAP = [
    "#B###B###B###B###B#",   # B = robot bay (parking / charging)
    "#.................#",
    "#.###.###.###.###.#",
    "#.###.###.###.###.#",
    "#.................#",
    "#.###.###.###.###.#",
    "#.###.###.###.###.#",
    "#.................#",
    "#########S#########",   # S = staging / hand-off point
]


class Grid:
    def __init__(self, rows=MAP):
        self.h, self.w = len(rows), len(rows[0])
        self.free, self.bays, self.staging = set(), [], None
        for y, r in enumerate(rows):
            for x, ch in enumerate(r):
                if ch != "#":
                    self.free.add((x, y))
                    if ch == "B": self.bays.append((x, y))
                    if ch == "S": self.staging = (x, y)
        self.bays.sort()
        self.aisle = sorted(c for c in self.free if c not in self.bays and c != self.staging)
        self._cache = {}

    def nbrs(self, c, blocked=frozenset()):
        x, y = c
        return [n for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1))
                if n in self.free and n not in blocked]

    def dist_map(self, target, blocked=frozenset()):
        """BFS distances to `target` (exact heuristic for A*)."""
        key = (target, frozenset(blocked))
        if key not in self._cache:
            d, q = {target: 0}, deque([target])
            while q:
                c = q.popleft()
                for n in self.nbrs(c, blocked):
                    if n not in d:
                        d[n] = d[c] + 1; q.append(n)
            self._cache[key] = d
        return self._cache[key]

    def connected(self, blocked, must_reach):
        d = self.dist_map(self.bays[0], frozenset(blocked))
        return all(c in d for c in must_reach)


def astar(grid, start, goal, blocked=frozenset()):
    """Classic single-robot A* on the static map. Returns cells AFTER start."""
    if start == goal: return []
    h = lambda c: abs(c[0] - goal[0]) + abs(c[1] - goal[1])
    open_, parent, cnt = [(h(start), 0, 0, start)], {start: None}, itertools.count(1)
    while open_:
        _, g, _, c = heapq.heappop(open_)
        if c == goal:
            out = []
            while c != start: out.append(c); c = parent[c]
            return out[::-1]
        for n in grid.nbrs(c, blocked):
            if n not in parent:
                parent[n] = c
                heapq.heappush(open_, (g + 1 + h(n), g + 1, next(cnt), n))
    return None


# ---------------------------------------------------------------- reservations
@dataclass
class Res:
    rid: int
    t0: int
    path: list          # path[i] = cell occupied at time t0+i ; last cell is HELD afterwards
    prio: float
    ts: int

    def at(self, t):
        return self.path[min(max(t - self.t0, 0), len(self.path) - 1)]

    def end(self): return self.t0 + len(self.path) - 1

    def key(self):      # higher wins: priority, then earlier timestamp, then HIGHER id (lower id yields)
        return (self.prio, -self.ts, self.rid)

    def to_msg(self):
        return {"type": "res", "src": self.rid, "t0": self.t0, "path": self.path, "prio": self.prio, "ts": self.ts}

    @staticmethod
    def from_msg(m):
        return Res(m["src"], m["t0"], [tuple(c) for c in m["path"]], m["prio"], m["ts"])


def conflict(a, b):
    """First cell where two reservations clash (same cell at same time, or head-on swap), else None."""
    for t in range(max(a.t0, b.t0), max(a.end(), b.end()) + 2):
        ca, cb = a.at(t), b.at(t)
        if ca == cb: return ca
        if ca != cb and a.at(t + 1) == cb and b.at(t + 1) == ca: return ca
    return None


def _constraints(others):
    occ, swaps, parked, busy = set(), set(), {}, {}
    for r in others:
        p = r.path
        for i, c in enumerate(p):
            t = r.t0 + i
            occ.add((c, t)); busy[c] = max(busy.get(c, -1), t)
            if i + 1 < len(p) and p[i + 1] != c: swaps.add((c, p[i + 1], t))
        parked[p[-1]] = r.end()        # last cell is occupied from arrival onwards, forever
    return occ, swaps, parked, busy


def st_astar(grid, start, t0, targets, blocked, others, horizon=150):
    """Space-time A*: visit `targets` in order, avoiding every other robot's reservation.
    State = (cell, time, stage). Waiting is a legal move. Returns (path, arrival_times) or (None, None)."""
    occ, swaps, parked, busy = _constraints(others)
    n = len(targets)
    dms = [grid.dist_map(g, frozenset(blocked)) for g in targets]
    suffix = [0] * (n + 1)
    for k in range(n - 2, -1, -1):
        d = dms[k + 1].get(targets[k])
        if d is None: return None, None
        suffix[k] = suffix[k + 1] + d
    if n and start not in dms[0]: return None, None
    h = lambda c, k: 0 if k == n else dms[k][c] + suffix[k]

    def adv(c, k):
        while k < n and c == targets[k]: k += 1
        return k

    s0 = (start, t0, adv(start, 0))
    heap, parent, cnt = [(h(start, s0[2]), 0, 0, s0)], {s0: None}, itertools.count(1)
    while heap:
        _, _, _, st = heapq.heappop(heap)
        c, t, k = st
        if k == n and c not in parked and t > busy.get(c, -1):
            states = []
            while st: states.append(st); st = parent[st]
            states.reverse()
            path = [s[0] for s in states]
            arr = [t0 + next(i for i, s in enumerate(states) if s[2] > j) for j in range(n)]
            return path, arr
        if t - t0 >= horizon: continue
        for nc in [c] + grid.nbrs(c, blocked):
            nt = t + 1
            if (nc, nt) in occ: continue
            if nc in parked and nt >= parked[nc]: continue
            if nc != c and (nc, c, t) in swaps: continue
            ns = (nc, nt, adv(nc, k))
            if ns in parent: continue
            parent[ns] = st
            g = nt - t0
            heapq.heappush(heap, (g + h(nc, ns[2]), -g, next(cnt), ns))
    return None, None


def make_tasks(grid, n, seed):
    rnd = random.Random(seed)
    out = []
    for i in range(n):
        p, d = rnd.sample(grid.aisle, 2)
        out.append({"id": f"T{i}", "pickup": p, "drop": d, "prio": rnd.choice([1, 1, 2]), "excl": []})
    return out


def make_blocks(grid, tasks, seed, count=2, first=12, gap=15):
    """Schedule `count` aisle blockages that keep every task cell reachable."""
    rnd = random.Random(seed + 999)
    must = [c for t in tasks for c in (t["pickup"], t["drop"])] + grid.bays + [grid.staging]
    chosen, out = set(), []
    for i in range(count):
        for _ in range(50):
            c = rnd.choice(grid.aisle)
            if c not in must and grid.connected(chosen | {c}, must):
                chosen.add(c); out.append((first + i * gap, c)); break
    return out
