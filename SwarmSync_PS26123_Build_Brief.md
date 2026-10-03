# SwarmSync — PS 26123 Prototype Build Brief
**Smart India Hackathon 2026 | Team: The Debuggers | 6 members | BVIMIT, Navi Mumbai**

This document is a complete handoff for starting prototype development in a new conversation. It captures the problem, the finalized design decisions, known edge cases, and the exact build sequence agreed on. Read this fully before writing any code.

---

## 1. The Problem Statement (PS 26123)

**Title:** Edge-AI Based Distributed Fleet Coordination for Autonomous Mobile Robots (AMRs) in Smart Warehouses
**Organization:** Bharat Electronics Limited (BEL)
**Theme:** Smart Automation | **Category:** Software

**Background:** Modern smart warehouses use fleets of AMRs coordinated by a centralized cloud server for path planning. As fleets scale, this causes high network latency, Wi-Fi dead-zone vulnerabilities, and single-point-of-failure risk — the entire fleet can freeze or collide when the central connection drops.

**Objective:** Design a decentralized coordination and collision-avoidance framework for a multi-robot fleet (at least 3 AMRs) operating in a dynamic warehouse environment, running locally on edge hardware (e.g., Raspberry Pi/Jetson Nano onboard each robot).

**Three required capabilities (this is the actual grading rubric — treat these as non-negotiable):**
1. **Decentralized Communication** — inter-robot messaging to share position and intent, without a central server making decisions.
2. **Dynamic Multi-Agent Conflict Resolution** — resolving deadlocks and avoiding collisions at narrow intersections/choke points, in real time.
3. **Task Allocation & Re-routing** — automatically reassigning pickup points or changing paths if a robot encounters a blocked aisle.

**Expected Solution components:**
- Decentralized network stack (P2P protocol sharing localization data)
- Multi-agent path planning algorithm suitable for edge hardware
- Fleet dashboard (live positions + battery status)

**Success criteria (hard, measurable — this is how it will be judged):**
- **Zero inter-robot collisions**
- **Minimum 20% reduction in total task completion time** vs. traditional centralized stop-and-wait coordination, under overlapping paths

---

## 2. Our Idea Name & Positioning

**Name:** SwarmSync
**One-line pitch:** Robots coordinate directly with each other — no central server — so the fleet keeps working even when the network doesn't.

**Scope honesty (say this whenever asked, don't overclaim):** This is a **proof-of-concept simulation validating the coordination mechanism**, not production firmware. We are proving the *approach* — reservation-based priority planning + broadcast-and-claim task allocation — is sound and implementable, using representative tools standing in for what production firmware would eventually use. Moving to actual deployment would require further work against real robot dynamics, sensor noise, and hardware-specific optimization.

---

## 3. Finalized Algorithm Design

### 3.1 Path assignment (how a robot gets its path — two layers)
- **Task assignment:** robots pull jobs from a shared task queue; whichever idle robot is nearest to a job claims it.
- **Path computation:** once a robot has a task, it computes its own route **locally** using standard A* on the warehouse's static map (every robot has the same preloaded map — no communication needed for this step).
- The coordination layer (below) only activates when two independently-computed paths are about to overlap in time and space.

### 3.2 Conflict resolution — Reservation-Based Priority Planning
1. **Broadcast Intent:** Robot 1 and Robot 2 both broadcast their intended path and arrival time for a shared segment.
2. **Local Check:** each robot checks if anyone else reserved that segment for an overlapping time window.
3. **Priority Rule:** whichever robot's reservation timestamp came first (or has higher task priority) wins the segment.
4. **Autonomous Adjustment:** the losing robot holds position or reroutes — decided locally from the broadcast received, no central server involved.
5. **Deadlock Resolution (the tiebreaker):** if two robots reserve at the exact same instant, a **fixed, deterministic tiebreaker — lower robot ID always yields** — resolves it. Both robots compute this independently from shared known IDs; no extra communication round needed. This is what satisfies the PS's explicit "resolving deadlocks" requirement — without it, simultaneous requests cause either a collision or a permanent deadlock.

### 3.3 Task allocation & re-routing — split into TWO distinct cases (do not conflate these)
This was a real gap identified and fixed during design — **the mechanism is different depending on whether the robot is carrying goods:**

- **Case A — Robot hasn't picked up cargo yet, path blocked:** trivial. Broadcast-and-claim: task is broadcast, nearest available robot claims it. Nothing physical to transfer.
- **Case B — Robot is already carrying goods, path blocked mid-delivery:**
  1. **First response: re-route**, not handoff. Recompute an alternate path to the same destination via A* on the same map. This is the primary answer — most blockages have an alternate route.
  2. **Fallback only if truly no alternate path exists:** route to a designated staging/handoff point on the map. Loaded robot drops the item there and broadcasts "delivery to staging" as complete; a new task ("staging to final destination") is created and claimed by another robot via normal broadcast-and-claim.
  3. Direct robot-to-robot cargo transfer (docking, robotic arms) is explicitly **out of scope** — state this clearly if asked, don't pretend it's solved.

### 3.4 Communication layer — MQTT, with an honest caveat about the broker
- Robots publish position/intent/reservation requests to a shared MQTT topic; all subscribed robots receive it directly.
- **Important distinction to hold onto:** MQTT removes the **cloud/internet dependency** (the actual problem named in the PS — Wi-Fi dead zones, latency, single point of failure at the *decision* level). It does **not** remove the **local broker dependency** — the broker is a message relay, not a decision-maker, but if the broker process or local network fails, robots lose the ability to hear each other.
- **If asked "isn't the broker a new single point of failure":** yes, for message transport, not for decision-making. State the limitation honestly; note that a production system would use a redundant broker cluster or direct device-to-device radio mesh to remove this too. For hackathon scope, one local broker (e.g., Mosquitto) is the practical tradeoff.
- **Run the broker locally inside the simulated warehouse network, not in the cloud** — this is what makes the "works during internet outage" claim true.

### 3.5 Known edge cases & mitigations (have these ready, they are your strongest credibility slide)
| Risk | Mitigation |
|---|---|
| **Priority starvation** — low-priority robot waits indefinitely | **Priority aging** — a robot's effective priority increases the longer it waits, guaranteeing eventual access |
| **Message loss** in P2P broadcast (dropped packet, range loss) | **Timeout-based re-broadcast** — if no reservation confirmation within X ms, re-broadcast |
| **Localization drift** — reported position becomes inaccurate over time | **Periodic recalibration** against known warehouse landmarks/checkpoints |
| **Broadcast overhead at scale** — every-robot-to-every-robot messaging doesn't scale | **Zone-based broadcasting** — robots only exchange messages within a defined proximity radius, not the whole fleet |
| **Robot battery dies mid-task** | Robot stops broadcasting active intent; its reservation expires; abandoned task re-enters the queue via the same broadcast-and-claim mechanism (no separate system needed) |

---

## 4. Tech Stack & What Each Piece Does
- **Python** — simulation environment + core algorithm (agent behavior, A* path computation, reservation logic, priority tiebreaking)
- **MQTT** (e.g., Mosquitto broker) — P2P messaging layer for position/intent broadcast between robots
- **Java Spring Boot** — backend REST API aggregating fleet data (positions, task status, metrics) and storing historical logs
- **WebSocket** — pushes live updates to the dashboard so it updates instantly, not via polling
- **Docker** — containerizes simulator + broker + backend so the system runs identically on any machine for a repeatable demo

---

## 5. Build Sequence (agreed order of implementation)
1. Basic multi-robot grid simulator, **no coordination** — establishes the "broken" baseline showing collisions happening (needed later for the before/after comparison)
2. Add A* path computation per robot on a static warehouse map
3. Add reservation-table logic — each robot checks for overlapping space-time claims before committing to a move
4. Add priority rule + fixed tiebreaker for simultaneous conflicts
5. Add broadcast-and-claim for Case A (unloaded robot, blocked path) and re-route + staging fallback for Case B (loaded robot, blocked path)
6. Instrument metrics logging — collision count, task completion time — to produce the before/after comparison against the centralized stop-and-wait baseline
7. Swap in-process/shared-memory prototyping for **real MQTT messaging** between separate robot processes
8. Wire the whole system to the dashboard via Spring Boot + WebSocket

---

## 6. Success Metrics to Actually Instrument (don't just claim these — log and prove them)
- **Collision count** — target: 0, under all simulated conditions
- **Task completion time** — decentralized (SwarmSync) vs. centralized stop-and-wait baseline — target: ≥20% improvement
- Consider also logging: average wait time per robot, deadlock occurrences (should be 0 given the tiebreaker), message loss/re-broadcast frequency

---

## 7. Dashboard Requirements
- Live visualization of all robots' positions on the grid
- Visual indication when a conflict is detected and resolved (e.g., highlight the contested cell, show "proceeding" vs. "yielding" state per robot)
- Battery/task status per robot
- End-of-run report: collision count, completion time vs. baseline — this needs to be visible on screen, not just claimed verbally

---

## 8. Things to Explicitly NOT Overclaim (say these limitations out loud when relevant — it builds credibility, not weakness)
- This is a simulation proving the mechanism, not tested on real robot hardware/dynamics
- The MQTT broker is a real (if minor) dependency — cloud dependency is removed, local broker dependency is not, unless later evolved to device-to-device mesh
- Direct robot-to-robot physical cargo transfer is out of scope
- The "20%+" and "zero collisions" targets must come from actual instrumented test runs against a real baseline implementation you also build — not asserted numbers

---

## 9. Team Structure (6 members)
- **Core Coordination Algorithm** — 2 members (reservation logic, priority/tiebreak, deadlock handling)
- **Simulated Warehouse Environment** — 1 member (grid, robot movement, static map, A*)
- **P2P Messaging Layer** — 1 member (MQTT integration, broker setup)
- **Live Fleet Dashboard** — 1 member (Spring Boot + WebSocket + frontend)
- **Testing, Metrics & Evaluation** — 1 member (baseline implementation, collision/time logging, comparison harness)

---

## 10. Instructions for the Next Chat
When you start the new conversation, paste this whole document as context, then say what you actually need — e.g., "help me set up the Python multi-robot simulator with A* and no coordination yet" (build step 1), or "help me implement the reservation-table conflict resolution logic" (step 3), or "help me set up the MQTT broker and message format." Work through the build sequence in Section 5 in order — each step should be working and testable before moving to the next, especially step 1 (the uncoordinated baseline), since you need it later for the before/after comparison in Section 6.
