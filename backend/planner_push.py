"""One-way Planner sync pushed by a Power Automate cloud flow:
Microsoft Planner → Power Automate (Recurrence → List my tasks → Filter array → Select) → POST /api/planner/sync.

The flow sends a full snapshot of your ACTIVE Planner tasks as {"tasks": [...]}. For each task:
- (source="planner", external_id=<Planner id>) exists → its Planner-managed fields are updated
  (title, percent complete, priority, due date, start date, plan id, bucket id); everything you keep in Memory
  (notes, steps, files, links, synapse placement, tags...) is left alone. Unchanged tasks are skipped.
- otherwise → a new task is created in the Basket.
Planner tasks that Memory still shows as open but that are missing from the snapshot were completed or removed in
Planner, so they're archived (marked done, flagged sync_archived) rather than deleted. If such a task shows up again
(reopened in Planner), it's restored. Tasks you completed yourself in Memory stay completed. Manually created
tasks are never touched. An empty snapshot archives nothing unless the caller says so (?allow_empty=true), in case
the flow misfired.

Authentication: a bearer token compared in constant time with MEMORY_PLANNER_SYNC_TOKEN, read from the environment
or the .env file in Memory's data folder. It is never stored in the database, sent to the browser or logged.
Nothing is written back to Planner for these tasks.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone

from . import db, engine
from .classifier import creative_score, region_for
from .planner_sync import _priority

log = logging.getLogger("memory.planner_push")
TOKEN_ENV = "MEMORY_PLANNER_SYNC_TOKEN"
MIN_TOKEN_LENGTH = 32
MAX_BODY_BYTES = 2 * 1024 * 1024
MAX_TASKS = 5000
VIA = "power-automate"

_lock = threading.Lock()
_failures: dict[str, list[float]] = {}  # client address -> recent failed-auth times
MAX_FAILURES, FAIL_WINDOW = 10, 60.0


# ---------- authentication ----------

def _configured_token() -> str:
    """The shared secret, or "" if it's missing or too short to be safe."""
    token = (os.environ.get(TOKEN_ENV) or "").strip()
    if token and len(token) < MIN_TOKEN_LENGTH:
        log.warning("%s is set but shorter than %d characters, so Planner sync stays disabled", TOKEN_ENV, MIN_TOKEN_LENGTH)
        return ""
    return token


def configured() -> bool:
    return bool(_configured_token())


def throttled(client: str) -> bool:
    now = time.monotonic()
    recent = [t for t in _failures.get(client, []) if now - t < FAIL_WINDOW]
    _failures[client] = recent
    return len(recent) >= MAX_FAILURES


def authorize(header: str | None, client: str) -> bool:
    """True if the Authorization header carries the right bearer token."""
    expected = _configured_token()
    scheme, _, presented = (header or "").partition(" ")
    ok = bool(expected) and scheme.lower() == "bearer" and hmac.compare_digest(presented.strip().encode(), expected.encode())
    if ok:
        _failures.pop(client, None)
    else:
        _failures.setdefault(client, []).append(time.monotonic())
        log.warning("rejected Planner sync from %s: %s", client, "no Authorization header" if not header else "wrong token")
    return ok


# ---------- the sync ----------

def _utc_date(value: datetime | None) -> str | None:
    """Planner's UTC timestamp as a local calendar date, like the Graph sync does."""
    return value.astimezone().date().isoformat() if value else None


def apply(tasks: list, allow_empty: bool = False) -> dict:
    """Apply one snapshot of active Planner tasks (validated PlannerPushTask models)."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    created = updated = unchanged = archived = restored = kept_done = 0
    warnings: list[str] = []
    seen: set[str] = set()
    with _lock, db.connect() as con:
        for t in tasks:
            if t.id in seen:
                warnings.append(f"Task {t.id} appeared more than once; the first copy was used.")
                continue
            seen.add(t.id)
            managed = {
                "title": t.title,
                "percent_complete": t.percentComplete,
                "priority": _priority(t.priority),
                "due_at": _utc_date(t.dueDate),
                "start_at": _utc_date(t.startDate),
                "plan_id": t.planId,
                "bucket_id": t.bucketId,
            }
            fingerprint = "pa:" + hashlib.sha1(json.dumps(managed, sort_keys=True).encode()).hexdigest()
            row = con.execute("SELECT id, status, etag, sync_archived FROM tasks WHERE source = 'planner' AND external_id = ?",
                              (t.id,)).fetchone()
            if row is None:
                score = creative_score(t.title, "", [])
                task_id = db.insert_task(con, {
                    **managed, "source": "planner", "external_id": t.id, "sync_via": VIA, "status": "basket",
                    "plan_name": "Planner", "bucket_name": "", "etag": fingerprint, "last_synced_at": now,
                    "creative_score": score, "region": region_for(score)})
                db.log_activity(con, task_id, "Synced from Microsoft Planner")
                created += 1
                continue
            sync_fields = {"last_synced_at": now, "sync_via": VIA}
            if row["status"] == "done" and row["sync_archived"]:
                # archived by an earlier sync, active in Planner again: bring it back
                db.update_task(con, row["id"], {**managed, **sync_fields, "etag": fingerprint, "status": "basket",
                                                "completed_at": None, "sync_archived": False})
                db.log_activity(con, row["id"], "Active again in Microsoft Planner")
                restored += 1
            elif row["status"] == "done":
                db.update_task(con, row["id"], sync_fields, touch=False)
                kept_done += 1  # you completed it in Memory: that stays your call
            elif row["etag"] == fingerprint:
                db.update_task(con, row["id"], sync_fields, touch=False)
                unchanged += 1
            else:
                db.update_task(con, row["id"], {**managed, **sync_fields, "etag": fingerprint})
                db.log_activity(con, row["id"], "Updated from Microsoft Planner")
                updated += 1

        # Planner tasks Memory still shows as open, but no longer in Planner's active list
        stale = [r for r in con.execute("SELECT id, external_id FROM tasks WHERE source = 'planner' AND status != 'done' "
                                        "AND external_id IS NOT NULL").fetchall() if r["external_id"] not in seen]
        if stale and not seen and not allow_empty:
            warnings.append(f"The request had no tasks, so {len(stale)} open Planner task(s) were left as they are. "
                            "To archive them anyway, call again with ?allow_empty=true.")
        else:
            for r in stale:
                db.update_task(con, r["id"], {"status": "done", "completed_at": db.now_iso(), "slot_index": None,
                                              "pinned": False, "sync_archived": True, "last_synced_at": now})
                db.log_activity(con, r["id"], "No longer active in Microsoft Planner (completed or removed there)")
                archived += 1

        result = {"success": True, "received": len(tasks), "created": created, "updated": updated, "unchanged": unchanged,
                  "archived": archived, "restored": restored, "kept_done": kept_done, "warnings": warnings, "synced_at": now}
        db.set_sync(con, "planner_last_sync", now)
        db.set_sync(con, "planner_last_result", {**result, "ok": True, "fetched": len(tasks), "completed": archived, "via": VIA})
        if created or updated or archived or restored:
            engine.recompute(con, fill=True)
    log.info("Planner sync: %s", {k: v for k, v in result.items() if k not in ("warnings",)})
    return result
