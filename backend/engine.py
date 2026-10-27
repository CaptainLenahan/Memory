"""Scheduling brain: priority scores, RAM-slot allocation, week auto-assignment, growth and links.

The pure functions take plain task dicts so they are easy to test; `recompute` applies them to the DB.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone

from . import db
from .classifier import region_for, tokens

EFFORT_HOURS = {"S": 2, "M": 6, "L": 12, "XL": 24}
PRIORITY_WEIGHT = {"low": 0, "medium": 10, "high": 22, "urgent": 35}
SIDE_FOR_REGION = {"logical": -1, "creative": 1, "balanced": 0}
SIDE_SCORE = {-1: 25, 1: 75}  # creative score a task takes on when the user places it on that hemisphere


def side_ok(region: str, side: int) -> bool:
    """Logical work only on the left hemisphere, creative only on the right; the centre slot and balanced tasks fit
    anywhere. Classification decides the side; a user's drop onto a side decides the classification (see place)."""
    return side == 0 or region == "balanced" or SIDE_FOR_REGION.get(region, 0) == side
STOPWORDS = {
    "the", "a", "an", "and", "or", "to", "of", "for", "in", "on", "with", "at", "by", "from", "my",
    "our", "is", "be", "it", "this", "that", "up", "new", "do", "get", "make", "task", "into", "about",
}


# ---------- dates ----------

def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def iso_week(d: date) -> str:
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def week_start(week: str) -> date:
    y, w = week.split("-W")
    return date.fromisocalendar(int(y), int(w), 1)


def next_weeks(today: date, count: int) -> list[str]:
    monday = today - timedelta(days=today.weekday())
    return [iso_week(monday + timedelta(weeks=i)) for i in range(count)]


# ---------- scoring ----------

def priority_score(task: dict, today: date, now: datetime | None = None) -> float:
    now = now or datetime.now(timezone.utc)
    score = PRIORITY_WEIGHT.get(task.get("priority") or "medium", 10)
    due = parse_date(task.get("due_at"))
    if due:
        days = (due - today).days
        if days < 0:
            score += 45 + min(-days, 10) * 1.5
        else:
            score += 40 * math.exp(-days / 7)
    if task.get("important"):
        score += 15
    if task.get("my_day") == today.isoformat():
        score += 12
    created = parse_dt(task.get("created_at"))
    if created:
        score += min((now - created).days, 30) * 0.3
    total = task.get("checklist_total") or 0
    if task.get("status") == "active" and total and (task.get("checklist_done") or 0) > 0:
        score += 3  # momentum: started work stays near the front
    return round(score, 2)


def growth(task: dict, link_count: int = 0, now: datetime | None = None) -> float:
    now = now or datetime.now(timezone.utc)
    notes_chars = len(task.get("notes_html") or "")
    total = task.get("checklist_total") or 0
    done = task.get("checklist_done") or 0
    activated = parse_dt(task.get("activated_at"))
    days_active = (now - activated).days if activated and task.get("status") == "active" else 0
    g = (
        0.25 * min(notes_chars / 800, 1)
        + 0.2 * min(total / 6, 1)
        + 0.2 * (done / total if total else 0)
        + 0.15 * min((task.get("attachment_count") or 0) / 3, 1)
        + 0.1 * min(days_active / 14, 1)
        + 0.1 * min(link_count / 3, 1)
    )
    return round(min(g, 1.0), 3)


# ---------- slots ----------

def slot_layout(n: int) -> list[dict]:
    """Slots ordered front-to-back. Odd counts get a centre executive slot at the frontal pole;
    the rest sit in left (logical) / right (creative) pairs."""
    slots: list[dict] = []
    if n <= 0:
        return slots
    if n % 2:
        slots.append({"index": 0, "side": 0, "frontness": 0.0, "region": "executive"})
    pairs = n // 2
    offset = 1 if n % 2 else 0
    for r in range(pairs):
        f = (r + offset) / max(pairs - 1 + offset, 1) if pairs + offset > 1 else 0.0
        for side in (-1, 1):
            slots.append({
                "index": len(slots), "side": side, "frontness": round(f, 3),
                "region": "logical" if side < 0 else "creative",
            })
    return slots


def _side_target(task: dict) -> int:
    return SIDE_FOR_REGION.get(region_for(task.get("creative_score", 50)), 0)


def allocate(candidates: list[dict], n: int) -> dict[int, tuple[str, int | None]]:
    """Decide which tasks hold RAM slots. Pinned active tasks keep theirs; the rest are filled by
    score, placing the most pressing nearest the front and on the matching hemisphere.
    Returns {task_id: (status, slot_index)}."""
    slots = slot_layout(n)
    result: dict[int, tuple[str, int | None]] = {}
    taken: set[int] = set()
    for t in candidates:
        if t.get("status") == "active" and t.get("pinned") and t.get("slot_index") is not None \
                and t["slot_index"] < n and t["slot_index"] not in taken:
            taken.add(t["slot_index"])
            result[t["id"]] = ("active", t["slot_index"])
    rest = sorted((t for t in candidates if t["id"] not in result), key=lambda t: -t.get("score", 0))
    free = [s for s in slots if s["index"] not in taken]
    span = max(len(free) - 1, 1)
    placed = 0
    for t in rest:
        region = region_for(t.get("creative_score", 50))
        fits = [s for s in free if side_ok(region, s["side"])]
        if not fits:  # its hemisphere is full: wait in the queue rather than sit on the wrong side
            result[t["id"]] = ("backlog", None)
            continue
        r_norm = min(placed / span, 1)
        target = _side_target(t)
        best = min(fits, key=lambda s: 2 * abs(s["frontness"] - r_norm) + (0.4 if s["side"] == 0 and target else 0))
        free.remove(best)
        placed += 1
        result[t["id"]] = ("active", best["index"])
    return result


# ---------- weeks ----------

def assign_weeks(tasks: list[dict], capacity_hours: float, today: date, horizon: int = 26) -> dict[int, tuple[str, bool]]:
    """Schedule open tasks into ISO weeks by score against a weekly hour budget.
    A due date caps the week; if nothing fits before it the task lands in its due week (or this
    week when overdue) and is flagged at risk. Locked weeks are honoured and consume capacity."""
    weeks = next_weeks(today, horizon)
    remaining = {w: float(capacity_hours) for w in weeks}
    out: dict[int, tuple[str, bool]] = {}
    current = weeks[0]

    def hours(t):
        return EFFORT_HOURS.get(t.get("effort") or "M", 6)

    for t in tasks:
        if t.get("week_locked") and t.get("assigned_week"):
            w = t["assigned_week"]
            if w in remaining:
                remaining[w] -= hours(t)
            due = parse_date(t.get("due_at"))
            out[t["id"]] = (w, bool(due and w > iso_week(due)))

    for t in sorted((t for t in tasks if t["id"] not in out), key=lambda t: -t.get("score", 0)):
        h = hours(t)
        due = parse_date(t.get("due_at"))
        last = iso_week(due) if due else weeks[-1]
        placed = None
        for w in weeks:
            if w > last:
                break
            if remaining[w] >= h or remaining[w] >= capacity_hours:  # big tasks may take a whole empty week
                placed = w
                break
        at_risk = False
        if placed is None:
            if due:
                placed = max(iso_week(due), current)
                at_risk = True
            else:
                placed = weeks[-1]
        if placed in remaining:
            remaining[placed] -= h
        out[t["id"]] = (placed, at_risk)
    return out


# ---------- links ----------

def keywords(task: dict) -> set[str]:
    words = {w for w in tokens(task.get("title", "")) if len(w) > 2 and w not in STOPWORDS}
    return words | {"#" + t.lower() for t in task.get("tags") or []}


def related_pairs(tasks: list[dict], threshold: float = 0.25) -> list[tuple[int, int, float]]:
    kws = [(t["id"], keywords(t)) for t in tasks]
    pairs = []
    for i, (a, ka) in enumerate(kws):
        if not ka:
            continue
        for b, kb in kws[i + 1:]:
            if not kb:
                continue
            j = len(ka & kb) / len(ka | kb)
            if j >= threshold:
                pairs.append((min(a, b), max(a, b), round(j, 3)))
    return pairs


# ---------- insights ----------

def computed_insights(tasks: list[dict], settings: dict, today: date, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    out = []
    open_tasks = [t for t in tasks if t["status"] != "done"]
    active = [t for t in open_tasks if t["status"] == "active"]
    overdue = [t for t in open_tasks if (d := parse_date(t.get("due_at"))) and d < today]
    if overdue:
        out.append({"kind": "overdue", "severity": "high",
                    "text": f"{len(overdue)} task(s) overdue — oldest: “{min(overdue, key=lambda t: t['due_at'])['title']}”."})
    risky = [t for t in open_tasks if t.get("at_risk")]
    if risky:
        out.append({"kind": "risk", "severity": "high",
                    "text": f"{len(risky)} task(s) won't fit before their due date at {settings['weekly_capacity_hours']}h/week. Consider raising capacity or trimming scope."})
    for t in active:
        upd = parse_dt(t.get("updated_at"))
        if upd and (now - upd).days >= 7:
            out.append({"kind": "stalled", "severity": "medium", "task_id": t["id"],
                        "text": f"“{t['title']}” has held a synapse for {(now - upd).days} days without changes. Re-think or break it down?"})
    week_ago = now - timedelta(days=7)
    done_week = [t for t in tasks if t["status"] == "done" and (c := parse_dt(t.get("completed_at"))) and c >= week_ago]
    created_week = [t for t in tasks if (c := parse_dt(t.get("created_at"))) and c >= week_ago]
    if done_week or created_week:
        trend = "keeping pace" if len(done_week) >= len(created_week) else "growing faster than you complete it"
        out.append({"kind": "velocity", "severity": "info",
                    "text": f"Last 7 days: {len(done_week)} completed vs {len(created_week)} added — your memory is {trend}."})
    backlog = [t for t in open_tasks if t["status"] == "backlog"]
    if len(backlog) > 2 * settings["ram_slots"]:
        out.append({"kind": "pressure", "severity": "medium",
                    "text": f"Backlog holds {len(backlog)} tasks — more than twice your {settings['ram_slots']} RAM slots. Archive or delegate some."})
    if len(active) >= 3:
        creative = sum(1 for t in active if region_for(t["creative_score"]) == "creative")
        logical = sum(1 for t in active if region_for(t["creative_score"]) == "logical")
        if creative == 0 or logical == 0:
            side = "creative" if logical else "logical"
            out.append({"kind": "balance", "severity": "info",
                        "text": f"Your active brain has no {side} work. Mixing in one can keep focus fresh."})
    basket = [t for t in open_tasks if t["status"] == "basket"]
    if basket:
        out.append({"kind": "basket", "severity": "info",
                    "text": f"{len(basket)} task(s) waiting in the basket. Drag them onto a synapse or press “Sort basket”."})
    return out


# ---------- apply to DB ----------

def dependency_pairs(con) -> list[tuple[int, int]]:
    """(task_id, depends_on_id) pairs."""
    return [(r["task_id"], r["depends_on_id"]) for r in con.execute("SELECT task_id, depends_on_id FROM dependencies")]


def creates_cycle(pairs: list[tuple[int, int]], task_id: int, depends_on_id: int) -> bool:
    """Would "task_id needs depends_on_id" close a loop, i.e. does depends_on_id already (indirectly) need task_id?"""
    needs: dict[int, list[int]] = {}
    for a, b in pairs:
        needs.setdefault(a, []).append(b)
    stack, seen = [depends_on_id], set()
    while stack:
        cur = stack.pop()
        if cur == task_id:
            return True
        if cur in seen:
            continue
        seen.add(cur)
        stack.extend(needs.get(cur, []))
    return False


def sequence(tasks: list[dict], pairs: list[tuple[int, int]]) -> dict[int, dict]:
    """Number each dependency chain in completion order. A task's step is 1 + the longest run of prerequisites
    before it; `of` is the chain's length; `goal` is the chain's final task. Done tasks keep their numbers, so a
    chain reads "1 ✓ → 2 → 3". `waiting` counts prerequisites that aren't done yet."""
    by_id = {t["id"]: t for t in tasks}
    pairs = [(a, b) for a, b in pairs if a in by_id and b in by_id]
    if not pairs:
        return {}
    needs: dict[int, list[int]] = {}
    adj: dict[int, set[int]] = {}
    for a, b in pairs:
        needs.setdefault(a, []).append(b)
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)
    step: dict[int, int] = {}

    def depth(i: int, trail: frozenset = frozenset()) -> int:
        if i in step:
            return step[i]
        if i in trail:  # defensive: cycles are refused on insert
            return 1
        step[i] = 1 + max((depth(p, trail | {i}) for p in needs.get(i, [])), default=0)
        return step[i]

    out: dict[int, dict] = {}
    seen: set[int] = set()
    for start in adj:
        if start in seen:
            continue
        comp, stack = [], [start]
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            comp.append(cur)
            stack.extend(adj[cur])
        for i in comp:
            depth(i)
        total = max(step[i] for i in comp)
        goal = max(comp, key=lambda i: (step[i], by_id[i]["status"] != "done", -i))
        for i in comp:
            out[i] = {"step": step[i], "of": total, "goal": goal,
                      "waiting": sum(1 for p in needs.get(i, []) if by_id[p]["status"] != "done")}
    return out


def recompute(con, reallocate: bool = False, include_basket: bool = False, fill: bool = False) -> None:
    """Refresh scores, growth, links and weeks. `reallocate` reshuffles synapses by score; `fill` pulls the
    top of the queue into empty synapses (used when one frees up, never after the user parks a task)."""
    settings = db.get_settings(con)
    n = int(settings["ram_slots"])
    today = date.today()
    now = datetime.now(timezone.utc)
    tasks = db.list_tasks(con, include_done=False)

    # links (auto) — keep manual ones untouched
    con.execute("DELETE FROM links WHERE kind = 'auto'")
    for a, b, s in related_pairs(tasks):
        con.execute("INSERT OR IGNORE INTO links(a_id, b_id, kind, strength) VALUES(?, ?, 'auto', ?)", (a, b, s))
    link_counts: dict[int, int] = {}
    for r in con.execute("SELECT a_id, b_id FROM links"):
        link_counts[r["a_id"]] = link_counts.get(r["a_id"], 0) + 1
        link_counts[r["b_id"]] = link_counts.get(r["b_id"], 0) + 1

    for t in tasks:
        t["score"] = priority_score(t, today, now)
        t["growth"] = growth(t, link_counts.get(t["id"], 0), now)
        t["region"] = region_for(t["creative_score"])

    # a prerequisite is at least as pressing as anything waiting on it, so it gets a synapse and a week first
    open_ids = {t["id"] for t in tasks}
    pairs = [(a, b) for a, b in dependency_pairs(con) if a in open_ids and b in open_ids]
    by_id = {t["id"]: t for t in tasks}
    for _ in range(len(pairs)):
        bumped = False
        for a, b in pairs:
            if by_id[b]["score"] < by_id[a]["score"] + 0.5:
                by_id[b]["score"] = round(by_id[a]["score"] + 0.5, 2)
                bumped = True
        if not bumped:
            break

    weeks = assign_weeks(tasks, settings["weekly_capacity_hours"], today)

    placements: dict[int, tuple[str, int | None]] = {}
    evicted = False
    if reallocate:
        cands = [t for t in tasks if t["status"] in ("active", "backlog") or (include_basket and t["status"] == "basket")]
        placements = allocate(cands, n)
    else:
        # keep placements, but evict anything outside the slot range or doubled up, and move tasks whose
        # classification no longer matches their hemisphere to a free slot on the right side (or the queue)
        layout = {s["index"]: s for s in slot_layout(n)}
        active = sorted((t for t in tasks if t["status"] == "active"), key=lambda t: (not t["pinned"], -t["score"]))
        used: set[int] = set()
        wrong_side = []
        for t in active:
            si = t["slot_index"]
            if si is None or si >= n or si in used:
                placements[t["id"]] = ("backlog", None)
            elif not side_ok(t["region"], layout[si]["side"]):
                wrong_side.append(t)
            else:
                used.add(si)
        for t in wrong_side:
            free = [s for s in layout.values() if s["index"] not in used and side_ok(t["region"], s["side"])]
            if free:
                best = min(free, key=lambda s: abs(s["frontness"] - layout[t["slot_index"]]["frontness"]))
                used.add(best["index"])
                placements[t["id"]] = ("active", best["index"])
            else:
                placements[t["id"]] = ("backlog", None)
                evicted = True

    for t in tasks:
        fields = {"score": t["score"], "growth": t["growth"], "region": t["region"]}
        w, risk = weeks[t["id"]]
        fields["at_risk"] = risk
        if not t["week_locked"]:
            fields["assigned_week"] = w
        if t["id"] in placements:
            status, slot = placements[t["id"]]
            if status != t["status"] or slot != t["slot_index"]:
                fields.update(status=status, slot_index=slot)
                if status == "active" and t["status"] != "active":
                    fields["activated_at"] = db.now_iso()
                if status != "active":
                    fields["pinned"] = False
                    db.log_activity(con, t["id"], "Moved to backlog queue" if status == "backlog" else f"Placed on synapse {slot + 1}")
                elif t["status"] != "active":
                    db.log_activity(con, t["id"], f"Delegated to synapse {slot + 1}")
                else:
                    db.log_activity(con, t["id"], f"Moved to synapse {slot + 1} on its hemisphere")
        db.update_task(con, t["id"], fields, touch=False)

    if (fill or evicted) and settings.get("auto_fill") and not reallocate:
        fill_free_slots(con, n)


def free_slots(con, n: int) -> list[int]:
    used = {r["slot_index"] for r in con.execute("SELECT slot_index FROM tasks WHERE status = 'active' AND slot_index IS NOT NULL")}
    return [s["index"] for s in slot_layout(n) if s["index"] not in used]


def fill_free_slots(con, n: int) -> None:
    """Pull the top of the backlog queue into any empty synapses (front-most first), each from tasks that belong on
    that synapse's hemisphere."""
    free = free_slots(con, n)
    if not free:
        return
    side_of = {s["index"]: s["side"] for s in slot_layout(n)}
    queue = [dict(r) for r in con.execute("SELECT id, creative_score FROM tasks WHERE status = 'backlog' ORDER BY score DESC, id")]
    for slot in free:
        pick = next((r for r in queue if side_ok(region_for(r["creative_score"]), side_of[slot])), None)
        if not pick:
            continue
        queue.remove(pick)
        db.update_task(con, pick["id"], {"status": "active", "slot_index": slot, "activated_at": db.now_iso(), "pinned": False})
        db.log_activity(con, pick["id"], f"Pulled from queue into synapse {slot + 1}")


def place(con, task_id: int, slot_index: int) -> None:
    """User dropped a task on a synapse. An occupant swaps into the mover's old slot, or goes to backlog."""
    n = int(db.get_settings(con)["ram_slots"])
    if not 0 <= slot_index < n:
        raise ValueError("slot out of range")
    task = db.get_task(con, task_id)
    if not task:
        raise KeyError(task_id)
    side_of = {s["index"]: s["side"] for s in slot_layout(n)}
    occupant = con.execute("SELECT id, creative_score FROM tasks WHERE status = 'active' AND slot_index = ? AND id != ?",
                           (slot_index, task_id)).fetchone()
    if occupant:
        # swap into the mover's old synapse only if that one is on the occupant's hemisphere; else to the queue
        if task["status"] == "active" and task["slot_index"] is not None \
                and side_ok(region_for(occupant["creative_score"]), side_of.get(task["slot_index"], 0)):
            db.update_task(con, occupant["id"], {"slot_index": task["slot_index"]})
            db.log_activity(con, occupant["id"], f"Swapped to synapse {task['slot_index'] + 1}")
        else:
            db.update_task(con, occupant["id"], {"status": "backlog", "slot_index": None, "pinned": False})
            db.log_activity(con, occupant["id"], "Bumped to backlog queue")
    fields = {"status": "active", "slot_index": slot_index, "pinned": True, "completed_at": None}
    if task["status"] != "active":
        fields["activated_at"] = db.now_iso()
    side = side_of[slot_index]
    if not side_ok(region_for(task["creative_score"]), side):
        # the user put it on the other hemisphere on purpose: it now counts as that kind of work
        kind = region_for(SIDE_SCORE[side])
        fields.update(creative_score=SIDE_SCORE[side], creative_locked=True, region=kind)
        db.log_activity(con, task_id, f"Re-classified as {kind} work (placed on the {'right' if side > 0 else 'left'} hemisphere)")
    db.update_task(con, task_id, fields)
    db.log_activity(con, task_id, f"Placed on synapse {slot_index + 1}")


def unplace(con, task_id: int, to: str) -> None:
    if to not in ("backlog", "basket"):
        raise ValueError("bad destination")
    db.update_task(con, task_id, {"status": to, "slot_index": None, "pinned": False})
    db.log_activity(con, task_id, "Moved to backlog queue" if to == "backlog" else "Returned to basket")
