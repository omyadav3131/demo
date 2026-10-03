"""Before/after comparison.  python benchmark.py [--seeds 20] [--penalty 2] [--blocks] [--loss 0.0] [--depth 1]
Averages are taken ONLY over seeds where every mode finished all tasks (a deadlocked baseline is reported, never averaged in)."""
import argparse, json, statistics as st
from common import Grid, make_tasks, make_blocks
from world import run_swarm
from baselines import run_baseline

ap = argparse.ArgumentParser()
ap.add_argument("--seeds", type=int, default=20); ap.add_argument("--penalty", type=int, default=2)
ap.add_argument("--blocks", action="store_true"); ap.add_argument("--loss", type=float, default=0.0)
ap.add_argument("--depth", type=int, default=1)
a = ap.parse_args()

g, rows = Grid(), []
print(f"stop-and-wait penalty={a.penalty} ticks | blockages={a.blocks} | msg loss={a.loss} | queue depth={a.depth}\n")
print(f"{'robots':>6} {'tasks':>5} | {'uncoord':>8} {'central':>8} {'swarm':>8} | {'swarm gain':>10} | collisions unc/cen/swarm | deadlocks cen/swarm | avg wait cen/swarm")
for n in (3, 4, 5):
    ok = {"uncoord": [], "central": [], "swarm": []}; wait = {"central": [], "swarm": []}
    coll = dict.fromkeys(ok, 0); dl = dict.fromkeys(ok, 0)
    for seed in range(a.seeds):
        tasks = make_tasks(g, 4 * n, seed)
        blocks = make_blocks(g, tasks, seed) if a.blocks else []
        r = {"uncoord": run_baseline(g, tasks, n, "uncoord", blocks=blocks),
             "central": run_baseline(g, tasks, n, "central", penalty=a.penalty, blocks=blocks),
             "swarm": run_swarm(g, tasks, n, depth=a.depth, loss=a.loss, blocks=blocks, seed=seed)}
        for k, v in r.items():
            coll[k] += v["collisions"]; dl[k] += v["deadlock"]
        rows.append({"n": n, "seed": seed, **{k: (None if v["deadlock"] else v["makespan"]) for k, v in r.items()}})
        if not any(v["deadlock"] for v in r.values()):
            for k, v in r.items(): ok[k].append(v["makespan"])
            for k in wait: wait[k].append(r[k]["wait_ticks"] / n)
    m = {k: st.mean(v) if v else float("nan") for k, v in ok.items()}
    gain = 100 * (m["central"] - m["swarm"]) / m["central"]
    print(f"{n:>6} {4*n:>5} | {m['uncoord']:>8.1f} {m['central']:>8.1f} {m['swarm']:>8.1f} | {gain:>9.1f}% | "
          f"{coll['uncoord']:>7}/{coll['central']}/{coll['swarm']:<7} | {dl['central']:>8}/{dl['swarm']:<8} | "
          f"{st.mean(wait['central']):.1f}/{st.mean(wait['swarm']):.1f}   (n={len(ok['swarm'])} seeds)")
json.dump(rows, open("results.json", "w"), indent=1)
