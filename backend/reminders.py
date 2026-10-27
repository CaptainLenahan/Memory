"""In-process event bus (feeds the SSE stream) and the background loop for reminders, re-scoring and Planner sync."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, datetime

from . import db, engine

log = logging.getLogger("memory.reminders")


class Bus:
    def __init__(self) -> None:
        self.subscribers: set[asyncio.Queue] = set()
        self.loop: asyncio.AbstractEventLoop | None = None

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        self.subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self.subscribers.discard(q)

    def publish(self, event: str, data: dict | None = None) -> None:
        """Thread-safe: callable from sync endpoints running in the threadpool."""
        payload = json.dumps(data or {})

        def deliver():
            for q in list(self.subscribers):
                if not q.full():
                    q.put_nowait((event, payload))

        if self.loop is None:
            return
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is self.loop:
            deliver()
        else:
            self.loop.call_soon_threadsafe(deliver)


bus = Bus()


def check_reminders() -> list[dict]:
    """Fire due reminders once each. Reminder times are stored as local naive 'YYYY-MM-DDTHH:MM'."""
    now_local = datetime.now().strftime("%Y-%m-%dT%H:%M")
    today = date.today().isoformat()
    fired = []
    with db.connect() as con:
        for r in con.execute("""SELECT id, title, reminder_at, due_at, priority, notify FROM tasks
                                WHERE status != 'done' AND reminded = 0 AND reminder_at IS NOT NULL
                                  AND reminder_at != '' AND reminder_at <= ?""", (now_local,)).fetchall():
            fired.append({"kind": "reminder", "task_id": r["id"], "title": r["title"], "text": f"Reminder: {r['title']}", "task": dict(r)})
            db.update_task(con, r["id"], {"reminded": True}, touch=False)
        if datetime.now().hour >= 8:
            for r in con.execute("""SELECT id, title, due_at, priority, notify FROM tasks
                                    WHERE status != 'done' AND due_notified = 0 AND due_at IS NOT NULL
                                      AND substr(due_at, 1, 10) <= ?""", (today,)).fetchall():
                late = r["due_at"][:10] < today
                fired.append({"kind": "due", "task_id": r["id"], "title": r["title"],
                              "text": f"{'Overdue' if late else 'Due today'}: {r['title']}", "task": dict(r)})
                db.update_task(con, r["id"], {"due_notified": True}, touch=False)
    from . import notify
    for f in fired:
        task = f.pop("task")
        if task.get("notify") == "off":
            continue
        bus.publish("reminder", f)  # in-app toast in any open Memory window
        notify.deliver(task, "Reminder" if f["kind"] == "reminder" else f["text"].split(":")[0], f["text"])
    return fired


async def background_loop() -> None:
    from . import planner_sync, windows  # local imports: msal is optional; windows imports this module

    tick = 0
    last_day = date.today()
    while True:
        try:
            await asyncio.to_thread(check_reminders)
            windows.prune()
            if tick % 20 == 0 or date.today() != last_day:  # ~10 minutes, or at midnight
                last_day = date.today()

                def rescore():
                    with db.connect() as con:
                        engine.recompute(con)

                await asyncio.to_thread(rescore)
                bus.publish("state")
            if tick % 30 == 15 and await asyncio.to_thread(planner_sync.auto_sync_due):  # ~15 minutes
                result = await asyncio.to_thread(planner_sync.sync)
                bus.publish("state")
                bus.publish("planner", result)
        except Exception:  # keep the loop alive no matter what
            log.exception("background loop error")
        tick += 1
        await asyncio.sleep(30)
