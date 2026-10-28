from datetime import date, datetime, timedelta, timezone

from backend import engine
from backend.classifier import creative_score, region_for

TODAY = date(2026, 10, 26)  # a Monday
NOW = datetime(2026, 10, 26, 12, tzinfo=timezone.utc)


def task(id, **kw):
    base = {"id": id, "title": f"Task {id}", "status": "backlog", "priority": "medium", "important": False,
            "effort": "M", "due_at": None, "created_at": NOW.isoformat(), "creative_score": 50,
            "pinned": False, "slot_index": None, "week_locked": False, "assigned_week": None, "score": 0}
    base.update(kw)
    return base


def test_overdue_beats_due_soon_beats_undated():
    overdue = task(1, due_at=(TODAY - timedelta(days=2)).isoformat())
    soon = task(2, due_at=(TODAY + timedelta(days=1)).isoformat())
    later = task(3, due_at=(TODAY + timedelta(days=30)).isoformat())
    none = task(4)
    scores = [engine.priority_score(t, TODAY, NOW) for t in (overdue, soon, later, none)]
    assert scores == sorted(scores, reverse=True)


def test_important_and_priority_raise_score():
    assert engine.priority_score(task(1, important=True), TODAY, NOW) > engine.priority_score(task(2), TODAY, NOW)
    assert engine.priority_score(task(1, priority="urgent"), TODAY, NOW) > engine.priority_score(task(2, priority="low"), TODAY, NOW)


def test_slot_layout_odd_has_center_front():
    slots = engine.slot_layout(7)
    assert len(slots) == 7
    assert slots[0]["side"] == 0 and slots[0]["frontness"] == 0
    assert sorted(s["index"] for s in slots) == list(range(7))
    assert {s["side"] for s in slots[1:]} == {-1, 1}


def test_allocate_overflows_to_backlog_and_front_gets_top_score():
    tasks = [task(i, score=100 - i) for i in range(1, 11)]
    result = engine.allocate(tasks, 5)
    active = {tid for tid, (st, _) in result.items() if st == "active"}
    assert active == {1, 2, 3, 4, 5}
    assert all(result[i] == ("backlog", None) for i in range(6, 11))
    front = min(engine.slot_layout(5), key=lambda s: s["frontness"])
    assert result[1][1] == front["index"]


def test_allocate_keeps_pinned_slot():
    pinned = task(9, status="active", pinned=True, slot_index=3, score=1)
    tasks = [pinned] + [task(i, score=100 - i) for i in range(1, 8)]
    result = engine.allocate(tasks, 5)
    assert result[9] == ("active", 3)
    assert sum(1 for st, _ in result.values() if st == "active") == 5


def test_allocate_sends_creative_right_logical_left():
    tasks = [task(1, score=50, creative_score=90), task(2, score=49, creative_score=10)]
    result = engine.allocate(tasks, 4)
    sides = {s["index"]: s["side"] for s in engine.slot_layout(4)}
    assert sides[result[1][1]] == 1
    assert sides[result[2][1]] == -1


def test_weeks_respect_capacity_and_due_dates():
    # capacity 10h: two 6h tasks can't share a week
    a = task(1, score=10, effort="M")
    b = task(2, score=9, effort="M")
    out = engine.assign_weeks([a, b], 10, TODAY)
    assert out[1][0] == "2026-W44" and out[2][0] == "2026-W45"
    # a due-this-week task that can't fit is flagged at risk but stays in its due week
    c = task(3, score=1, effort="M", due_at=(TODAY + timedelta(days=2)).isoformat())
    out = engine.assign_weeks([a, c], 10, TODAY)
    assert out[3] == ("2026-W44", True)


def test_locked_week_kept():
    t = task(1, week_locked=True, assigned_week="2026-W50")
    assert engine.assign_weeks([t], 20, TODAY)[1][0] == "2026-W50"


def test_related_pairs_by_shared_words():
    pairs = engine.related_pairs([task(1, title="Budget report Q4"), task(2, title="Q4 budget review"), task(3, title="Paint fence")])
    assert [(a, b) for a, b, _ in pairs] == [(1, 2)]


def test_classifier():
    assert region_for(creative_score("Brainstorm brand logo concepts")) == "creative"
    assert region_for(creative_score("Reconcile invoice spreadsheet")) == "logical"
    assert creative_score("Call mom") == 50


def test_tasks_only_sit_on_their_own_hemisphere():
    # 3 slots: 0 = centre, 1 = left (logical), 2 = right (creative)
    tasks = [task(1, creative_score=90, score=90), task(2, creative_score=85, score=80),
             task(3, creative_score=80, score=70), task(4, creative_score=10, score=10)]
    side = {s["index"]: s["side"] for s in engine.slot_layout(3)}
    out = engine.allocate(tasks, 3)
    for tid, (status, slot) in out.items():
        if status == "active":
            assert engine.side_ok(region_for(next(t for t in tasks if t["id"] == tid)["creative_score"]), side[slot])
    assert out[4] == ("active", 1)            # the logical task gets the left synapse despite its low score
    assert out[3] == ("backlog", None)        # third creative task waits: no creative/centre slot left


def test_dependency_sequence_numbers_a_chain():
    tasks = [task(1), task(2), task(3, status="done"), task(4), task(9)]
    pairs = [(2, 1), (4, 2), (2, 3)]   # 4 needs 2; 2 needs 1 and 3 (done)
    seq = engine.sequence(tasks, pairs)
    assert seq[1]["step"] == 1 and seq[3]["step"] == 1 and seq[2]["step"] == 2 and seq[4]["step"] == 3
    assert all(seq[i]["of"] == 3 and seq[i]["goal"] == 4 for i in (1, 2, 3, 4))
    assert seq[2]["waiting"] == 1 and seq[4]["waiting"] == 1 and 9 not in seq
    assert engine.creates_cycle(pairs, 1, 4) and not engine.creates_cycle(pairs, 4, 9)


def test_wallpaper_supervisor_retries_steps_aside_and_recovers(monkeypatch):
    import threading
    import time
    from backend import wallpaper as wp
    if not wp.WINDOWS:
        return
    events, lively = [], {"on": False}

    class FakeHost:
        attempts = 0
        def __init__(self, port, screens):
            self.problem, self.alive = "", True
        def start_and_wait(self):
            FakeHost.attempts += 1
            events.append(("start", FakeHost.attempts))
            return FakeHost.attempts >= 3          # the first two tries fail (e.g. Edge slow at sign-in)
        def healthy(self):
            return self.alive
        def stop(self):
            events.append(("stop",))
    monkeypatch.setattr(wp, "_Host", FakeHost)
    monkeypatch.setattr(wp, "lively_running", lambda: lively["on"])
    monkeypatch.setattr(wp, "CHECK_EVERY", 0.02)
    monkeypatch.setattr(wp, "MAX_BACKOFF", 0.05)
    wp.start(8765, "all")
    deadline = time.time() + 5
    while FakeHost.attempts < 3 and time.time() < deadline:
        time.sleep(0.02)
    assert FakeHost.attempts == 3                    # kept retrying until it worked
    lively["on"] = True; time.sleep(0.2)
    assert ("stop",) in events and "Lively" in wp.status()["reason"]
    lively["on"] = False; time.sleep(0.3)
    assert FakeHost.attempts >= 4                    # came back once Lively closed
    wp.stop()
    assert not wp.status()["running"]
