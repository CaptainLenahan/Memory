"""Memory — FastAPI app: REST API, SSE event stream and the static frontend."""
from __future__ import annotations

import asyncio
import logging
import mimetypes
import threading
import os
import uuid
import webbrowser
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

from .paths import ENV_FILE, FRONTEND

load_dotenv(ENV_FILE)

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile  # noqa: E402
from fastapi import Path as PathParam  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from . import claude_service, db, desktop, engine, lively, mail, notify, paths, planner_push, planner_sync, sysinfo, tunnel, wallpaper, windows  # noqa: E402
from .classifier import creative_score, region_for  # noqa: E402
from .models import (  # noqa: E402
    ChatBody, ChecklistCreate, ChecklistUpdate, DelegateApply, DependencyBody, InsightBody, LinkBody, LoginBody, OpenBody, PlaceBody,
    TemplateBody, TemplateFromTask, TemplateUse,
    PlannerPushBody, ReorderBody, RethinkBody, SettingsUpdate, TaskCreate, TaskUpdate, UnplaceBody,
)
from .reminders import background_loop, bus  # noqa: E402
from .version import REPO, __version__  # noqa: E402

MAX_UPLOAD = 50 * 1024 * 1024


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init()
    with db.connect() as con:
        engine.recompute(con)
    bus.loop = asyncio.get_running_loop()
    task = asyncio.create_task(background_loop())
    with db.connect() as con:
        s = db.get_settings(con)
    if s.get("desktop_wallpaper"):  # give the server a moment to start listening before Edge asks for the page
        threading.Timer(2, wallpaper.start, args=(wallpaper.port_from_env(), s.get("wallpaper_screens", "all"))).start()
    if s.get("dev_tunnel_id"):
        tunnel.start(s["dev_tunnel_id"])
    if s.get("start_lively") and not s.get("desktop_wallpaper"):
        lively.ensure(wallpaper.port_from_env())
    yield
    task.cancel()
    wallpaper.stop()
    tunnel.stop()


log = logging.getLogger("memory.app")
app = FastAPI(title="Memory", version=__version__, lifespan=lifespan)

# ---------- access guard ----------
# Memory listens on 127.0.0.1 and has no login. Two things could still reach it from outside: web pages in your
# browser (they can send requests to localhost) and a tunnel that forwards the port so a cloud flow can push Planner
# tasks. So: requests from other websites are refused, and anything arriving through a tunnel/proxy (a non-local Host,
# or forwarding headers) may only use POST /api/planner/sync, which needs the sync token.
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]"} | {
    h.strip() for h in os.environ.get("MEMORY_EXTRA_LOCAL_HOSTS", "").split(",") if h.strip()}
_FORWARDED = ("x-forwarded-for", "x-forwarded-host", "forwarded", "x-original-host", "x-real-ip")
_REMOTE_OK = {("POST", "/api/planner/sync")}


def _hostname(netloc: str) -> str:
    netloc = netloc.strip().lower()
    if netloc.startswith("["):
        return netloc.split("]")[0] + "]"
    return netloc.rsplit(":", 1)[0] if netloc.count(":") == 1 else netloc


def is_local_request(request: Request) -> bool:
    return _hostname(request.headers.get("host", "")) in _LOCAL_HOSTS and not any(h in request.headers for h in _FORWARDED)


@app.middleware("http")
async def access_guard(request: Request, call_next):
    origin = request.headers.get("origin")
    if origin is not None:
        o = origin.split("://", 1)[-1]
        if origin == "null" or _hostname(o) not in _LOCAL_HOSTS:
            return JSONResponse({"detail": "Requests from other websites aren't accepted."}, status_code=403)
    if not is_local_request(request) and (request.method, request.url.path) not in _REMOTE_OK:
        return JSONResponse({"detail": "Not available remotely."}, status_code=403)
    return await call_next(request)


def changed(con, fill: bool = False) -> None:
    engine.recompute(con, fill=fill)
    bus.publish("state")


def require_task(con, task_id: int) -> dict:
    t = db.get_task(con, task_id)
    if not t:
        raise HTTPException(404, "Task not found")
    return t


def push_if_planner(background: BackgroundTasks, task: dict) -> None:
    # Tasks pushed by Power Automate are one-way (Planner → Memory): nothing is written back to Planner for them.
    if task.get("source") == "planner" and task.get("sync_via") != planner_push.VIA:
        background.add_task(planner_sync.push_task, task["id"])


PLANNER_MANAGED = {"title", "due_at", "priority"}  # owned by Planner for Power Automate-synced tasks


# ---------- state ----------

@app.get("/api/state")
def get_state():
    with db.connect() as con:
        settings = db.get_settings(con)
        tasks = db.list_tasks(con)
        links = [dict(r) for r in con.execute("SELECT a_id, b_id, kind, strength FROM links")]
        deps = engine.dependency_pairs(con)
    seq = engine.sequence(tasks, deps)
    for t in tasks:
        t["seq"] = seq.get(t["id"])
    today = date.today()
    return {
        "tasks": tasks,
        "links": links,
        "dependencies": [{"task_id": a, "depends_on_id": b} for a, b in deps],
        "slots": engine.slot_layout(int(settings["ram_slots"])),
        "settings": settings,
        "today": today.isoformat(),
        "current_week": engine.iso_week(today),
        "weeks": [{"week": w, "start": engine.week_start(w).isoformat()} for w in engine.next_weeks(today, 12)],
        "windows_open": windows.count(),
        "version": __version__,
    }


# ---------- tasks ----------

@app.post("/api/tasks")
def create_task(body: TaskCreate):
    with db.connect() as con:
        fields = body.model_dump(exclude={"checklist"})
        if fields["creative_score"] is None:
            fields["creative_score"] = creative_score(body.title, body.notes_html, body.tags)
        else:
            fields["creative_locked"] = True
        fields["region"] = region_for(fields["creative_score"])
        if body.status == "active":
            fields["status"] = "backlog"  # placement goes through /place so slots stay consistent
        task_id = db.insert_task(con, fields)
        for pos, text in enumerate(body.checklist):
            con.execute("INSERT INTO checklist_items(task_id, text, position) VALUES(?, ?, ?)", (task_id, text, pos))
        db.log_activity(con, task_id, "Created")
        changed(con)
        return db.task_detail(con, task_id)


@app.get("/api/tasks/{task_id}")
def get_task(task_id: int):
    with db.connect() as con:
        t = db.task_detail(con, task_id)
    if not t:
        raise HTTPException(404, "Task not found")
    return t


@app.patch("/api/tasks/{task_id}")
def update_task(task_id: int, body: TaskUpdate, background: BackgroundTasks):
    with db.connect() as con:
        t = require_task(con, task_id)
        fields = body.model_dump(exclude_unset=True)
        if t.get("sync_via") == planner_push.VIA and PLANNER_MANAGED & fields.keys():
            raise HTTPException(409, "That's managed in Microsoft Planner: change it there and it updates here on the next sync.")
        status = fields.pop("status", None)
        if "creative_score" in fields and "creative_locked" not in fields:
            fields["creative_locked"] = True
        if fields.get("creative_locked") is False and "creative_score" not in fields:
            fields["creative_score"] = creative_score(fields.get("title", t["title"]), t["notes_html"], fields.get("tags", t["tags"]))
        if "creative_score" in fields:
            fields["region"] = region_for(fields["creative_score"])
        if "reminder_at" in fields:
            fields["reminded"] = False
        if "due_at" in fields:
            fields["due_notified"] = False
        if "assigned_week" in fields and "week_locked" not in fields:
            fields["week_locked"] = bool(fields["assigned_week"])
        if fields:
            db.update_task(con, task_id, fields)
        if "due_at" in fields:
            db.log_activity(con, task_id, f"Due date set to {fields['due_at']}" if fields["due_at"] else "Due date cleared")
        if status and status != t["status"]:
            if status == "done":
                claude_service.complete(con, db.get_task(con, task_id))
            elif status == "active":
                free = engine.free_slots(con, int(db.get_settings(con)["ram_slots"]))
                if not free:
                    raise HTTPException(409, "All synapses are full — drop it on one to swap.")
                engine.place(con, task_id, free[0])
            else:
                db.update_task(con, task_id, {"status": status, "slot_index": None, "pinned": False, "completed_at": None})
                db.log_activity(con, task_id, {"backlog": "Moved to backlog queue", "basket": "Returned to basket"}.get(status, "Reopened"))
        changed(con)
        t = db.task_detail(con, task_id)
    if status or {"due_at", "priority", "title"} & fields.keys():
        push_if_planner(background, t)
    return t


@app.delete("/api/tasks/{task_id}")
def delete_task(task_id: int):
    with db.connect() as con:
        require_task(con, task_id)
        files = [r["stored_name"] for r in con.execute("SELECT stored_name FROM attachments WHERE task_id = ?", (task_id,))]
        con.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        changed(con, fill=True)
    for f in files:
        (db.ATTACH_DIR / f).unlink(missing_ok=True)
    return {"ok": True}


@app.post("/api/tasks/{task_id}/place")
def place_task(task_id: int, body: PlaceBody):
    with db.connect() as con:
        require_task(con, task_id)
        try:
            engine.place(con, task_id, body.slot_index)
        except ValueError as e:
            raise HTTPException(400, str(e))
        changed(con)
        return db.get_task(con, task_id)


@app.post("/api/tasks/{task_id}/unplace")
def unplace_task(task_id: int, body: UnplaceBody):
    with db.connect() as con:
        require_task(con, task_id)
        engine.unplace(con, task_id, body.to)
        changed(con)
        return db.get_task(con, task_id)


@app.post("/api/rethink")
def rethink(body: RethinkBody):
    with db.connect() as con:
        if body.include_basket:
            con.execute("UPDATE tasks SET pinned = 0 WHERE status = 'active'")
        engine.recompute(con, reallocate=True, include_basket=body.include_basket)
        bus.publish("state")
    return {"ok": True}


# ---------- checklist ----------

@app.post("/api/tasks/{task_id}/checklist")
def add_check(task_id: int, body: ChecklistCreate):
    with db.connect() as con:
        require_task(con, task_id)
        pos = con.execute("SELECT COALESCE(MAX(position), -1) + 1 AS p FROM checklist_items WHERE task_id = ?", (task_id,)).fetchone()["p"]
        con.execute("INSERT INTO checklist_items(task_id, text, position) VALUES(?, ?, ?)", (task_id, body.text, pos))
        db.update_task(con, task_id, {})
        changed(con)
        return db.task_detail(con, task_id)


@app.patch("/api/checklist/{item_id}")
def update_check(item_id: int, body: ChecklistUpdate, background: BackgroundTasks):
    with db.connect() as con:
        item = con.execute("SELECT * FROM checklist_items WHERE id = ?", (item_id,)).fetchone()
        if not item:
            raise HTTPException(404, "Checklist item not found")
        if body.text is not None:
            con.execute("UPDATE checklist_items SET text = ? WHERE id = ?", (body.text, item_id))
        if body.done is not None:
            con.execute("UPDATE checklist_items SET done = ? WHERE id = ?", (int(body.done), item_id))
            if body.done:
                db.log_activity(con, item["task_id"], f"Checked “{item['text']}”")
        db.update_task(con, item["task_id"], {})
        changed(con)
        t = db.task_detail(con, item["task_id"])
    if body.done is not None and item["external_id"]:
        push_if_planner(background, t)
    return t


@app.delete("/api/checklist/{item_id}")
def delete_check(item_id: int):
    with db.connect() as con:
        item = con.execute("SELECT task_id FROM checklist_items WHERE id = ?", (item_id,)).fetchone()
        if not item:
            raise HTTPException(404, "Checklist item not found")
        con.execute("DELETE FROM checklist_items WHERE id = ?", (item_id,))
        changed(con)
        return db.task_detail(con, item["task_id"])


@app.post("/api/tasks/{task_id}/checklist/reorder")
def reorder_check(task_id: int, body: ReorderBody):
    with db.connect() as con:
        for pos, item_id in enumerate(body.ids):
            con.execute("UPDATE checklist_items SET position = ? WHERE id = ? AND task_id = ?", (pos, item_id, task_id))
        return db.task_detail(con, task_id)


# ---------- attachments ----------

@app.post("/api/tasks/{task_id}/attachments")
async def upload(task_id: int, files: list[UploadFile] = File(...), is_screenshot: bool = Form(False)):
    saved = []
    for f in files:
        data = await f.read()
        if len(data) > MAX_UPLOAD:
            raise HTTPException(413, f"{f.filename} is larger than 50 MB")
        ext = Path(f.filename or "").suffix[:10] or mimetypes.guess_extension(f.content_type or "") or ""
        stored = f"{uuid.uuid4().hex}{ext}"
        (db.ATTACH_DIR / stored).write_bytes(data)
        saved.append((f.filename or stored, stored, f.content_type or "application/octet-stream", len(data)))
    with db.connect() as con:
        require_task(con, task_id)
        ids = []
        for name, stored, mime, size in saved:
            cur = con.execute(
                "INSERT INTO attachments(task_id, filename, stored_name, mime, size, is_screenshot, created_at) VALUES(?, ?, ?, ?, ?, ?, ?)",
                (task_id, name, stored, mime, size, int(is_screenshot), db.now_iso()))
            ids.append(cur.lastrowid)
            db.log_activity(con, task_id, f"Attached {'screenshot' if is_screenshot else name}")
        db.update_task(con, task_id, {})
        changed(con)
        detail = db.task_detail(con, task_id)
    detail["uploaded_ids"] = ids
    return detail


@app.get("/api/attachments/{att_id}")
def get_attachment(att_id: int, download: bool = False):
    with db.connect() as con:
        a = con.execute("SELECT * FROM attachments WHERE id = ?", (att_id,)).fetchone()
    if not a:
        raise HTTPException(404, "Attachment not found")
    path = db.ATTACH_DIR / a["stored_name"]
    if not path.exists():
        raise HTTPException(404, "File missing")
    disposition = "attachment" if download else "inline"
    return FileResponse(path, media_type=a["mime"], filename=a["filename"], content_disposition_type=disposition)


@app.delete("/api/attachments/{att_id}")
def delete_attachment(att_id: int):
    with db.connect() as con:
        a = con.execute("SELECT * FROM attachments WHERE id = ?", (att_id,)).fetchone()
        if not a:
            raise HTTPException(404, "Attachment not found")
        con.execute("DELETE FROM attachments WHERE id = ?", (att_id,))
        changed(con)
        detail = db.task_detail(con, a["task_id"])
    (db.ATTACH_DIR / a["stored_name"]).unlink(missing_ok=True)
    return detail


# ---------- links ----------

@app.post("/api/tasks/{task_id}/links")
def add_link(task_id: int, body: LinkBody):
    if body.other_id == task_id:
        raise HTTPException(400, "A task can't link to itself")
    with db.connect() as con:
        require_task(con, task_id)
        require_task(con, body.other_id)
        a, b = sorted((task_id, body.other_id))
        con.execute("INSERT INTO links(a_id, b_id, kind, strength) VALUES(?, ?, 'manual', 1.0) "
                    "ON CONFLICT(a_id, b_id) DO UPDATE SET kind = 'manual', strength = 1.0", (a, b))
        changed(con)
        return db.task_detail(con, task_id)


@app.delete("/api/tasks/{task_id}/links/{other_id}")
def delete_link(task_id: int, other_id: int):
    with db.connect() as con:
        a, b = sorted((task_id, other_id))
        con.execute("DELETE FROM links WHERE a_id = ? AND b_id = ?", (a, b))
        changed(con)
        return db.task_detail(con, task_id)


# ---------- templates ----------

def _create_from(con, fields: dict, checklist: list[str]) -> int:
    if fields.get("creative_score") is None:
        fields["creative_score"] = creative_score(fields["title"], fields.get("notes_html", ""), fields.get("tags", []))
    else:
        fields["creative_locked"] = True
    fields["region"] = region_for(fields["creative_score"])
    task_id = db.insert_task(con, fields)
    for pos, text in enumerate(checklist):
        con.execute("INSERT INTO checklist_items(task_id, text, position) VALUES(?, ?, ?)", (task_id, text, pos))
    return task_id


@app.get("/api/templates")
def list_templates():
    with db.connect() as con:
        return db.list_templates(con)


@app.post("/api/templates")
def create_template(body: TemplateBody):
    with db.connect() as con:
        tid = db.insert_template(con, body.model_dump())
        return next(t for t in db.list_templates(con) if t["id"] == tid)


@app.post("/api/tasks/{task_id}/template")
def template_from_task(task_id: int, body: TemplateFromTask):
    """Save a task's shape (title, notes, steps, priority, effort, tags, kind, repeat, notifications) as a template."""
    with db.connect() as con:
        t = db.task_detail(con, task_id)
        if not t:
            raise HTTPException(404, "Task not found")
        due_in = None
        if t["due_at"]:
            due_in = max(0, (date.fromisoformat(t["due_at"][:10]) - date.fromisoformat(t["created_at"][:10])).days)
        tid = db.insert_template(con, {
            "name": (body.name or t["title"])[:80], "title": t["title"], "notes_html": t["notes_html"], "priority": t["priority"],
            "effort": t["effort"], "tags": t["tags"], "checklist": [c["text"] for c in t["checklist"]],
            "creative_score": t["creative_score"] if t["creative_locked"] else None, "repeat": t["repeat"] or "",
            "notify": t.get("notify") or "desktop", "due_in_days": due_in})
        return next(x for x in db.list_templates(con) if x["id"] == tid)


@app.delete("/api/templates/{template_id}")
def delete_template(template_id: int):
    with db.connect() as con:
        con.execute("DELETE FROM templates WHERE id = ?", (template_id,))
    return {"ok": True}


@app.post("/api/templates/{template_id}/use")
def use_template(template_id: int, body: TemplateUse):
    with db.connect() as con:
        tpl = next((t for t in db.list_templates(con) if t["id"] == template_id), None)
        if not tpl:
            raise HTTPException(404, "Template not found")
        fields = {k: tpl[k] for k in ("notes_html", "priority", "effort", "tags", "creative_score", "repeat", "notify")}
        fields.update(title=(body.title or tpl["title"]).strip() or tpl["name"], status="basket")
        if tpl["due_in_days"] is not None:
            fields["due_at"] = (date.today() + timedelta(days=tpl["due_in_days"])).isoformat()
        task_id = _create_from(con, fields, tpl["checklist"])
        db.log_activity(con, task_id, f"Created from the “{tpl['name']}” template")
        changed(con)
        return db.task_detail(con, task_id)


# ---------- notifications ----------

@app.post("/api/notify/test")
def notify_test():
    """Send a test desktop notification, plus a test email when Outlook is connected."""
    shown = notify.desktop("Memory", "Notifications are working", "This is what a task reminder looks like.", "http://localhost:8765/")
    email_error = notify.email("[Memory] Test notification", "<p>Email notifications from Memory are working.</p>") if mail.account() else "Outlook isn't connected"
    return {"desktop": shown, "email": email_error is None, "email_error": email_error}


# ---------- Outlook inbox ----------

def _mail(fn, *args):
    try:
        return fn(*args)
    except mail.MailNotConnected as e:
        raise HTTPException(400, str(e))
    except mail.requests.RequestException as e:
        raise HTTPException(502, f"Outlook error: {e}")


@app.get("/api/mail/inbox")
def mail_inbox(top: int = 25):
    messages = _mail(mail.inbox, max(1, min(top, 50)))
    with db.connect() as con:
        made = {r["external_id"][5:]: r["id"] for r in con.execute("SELECT id, external_id FROM tasks WHERE external_id LIKE 'mail:%'")}
    for m in messages:
        m["task_id"] = made.get(m["id"])
    return {"account": mail.account(), "messages": messages}


@app.post("/api/mail/suggest")
def mail_suggest():
    """Ask Claude which recent emails need action, with a suggested task title for each."""
    messages = _mail(mail.inbox, 25)
    return {"suggestions": _claude(claude_service.triage, messages)}


@app.post("/api/mail/{message_id}/task")
def mail_to_task(message_id: str):
    """Turn an email into a basket task. Claude interprets it when a key is set; otherwise subject + preview."""
    ext = f"mail:{message_id}"
    with db.connect() as con:
        existing = con.execute("SELECT id FROM tasks WHERE external_id = ?", (ext,)).fetchone()
        if existing:
            return db.task_detail(con, existing["id"]) | {"ai": False, "existing": True}
    msg = _mail(mail.message, message_id)
    ai = None
    try:
        ai = claude_service.email_to_task(msg)
    except claude_service.NotConfigured:
        pass
    except Exception as e:  # any Claude hiccup: still make the task from the raw email
        log.warning("email interpretation failed: %s", e)
    esc = lambda s: (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")  # noqa: E731
    origin = (f"<p><b>From:</b> {esc(msg['from'])} &lt;{esc(msg['from_address'])}&gt;<br><b>Subject:</b> {esc(msg['subject'])}"
              + (f"<br><a href=\"{esc(msg['link'])}\" target=\"_blank\" rel=\"noopener\">Open in Outlook</a>" if msg.get("link") else "") + "</p>")
    if ai:
        fields = {"title": ai["title"][:500] or msg["subject"], "priority": ai["priority"], "effort": ai["effort"],
                  "tags": [t[:40] for t in ai["tags"][:3]], "creative_score": max(0, min(100, int(ai["creative_score"]))),
                  "notes_html": f"<p>{esc(ai['summary'])}</p>{origin}"}
        if ai.get("due_date"):
            try:
                fields["due_at"] = date.fromisoformat(ai["due_date"]).isoformat()
            except ValueError:
                pass
        steps = [s[:1000] for s in ai["steps"][:6]]
    else:
        fields = {"title": msg["subject"][:500], "priority": "high" if msg.get("important") else "medium", "tags": ["email"],
                  "notes_html": f"<p>{esc(msg['body'][:1500])}</p>{origin}"}
        steps = []
    fields.update(status="basket", source="email", external_id=ext)
    with db.connect() as con:
        task_id = _create_from(con, fields, steps)
        db.log_activity(con, task_id, f"Created from an email from {msg['from']}" + (" (interpreted by Claude)" if ai else ""))
        changed(con)
        return db.task_detail(con, task_id) | {"ai": bool(ai), "actionable": ai.get("actionable", True) if ai else True}


@app.post("/api/tasks/{task_id}/dependencies")
def add_dependency(task_id: int, body: DependencyBody):
    if body.depends_on_id == task_id:
        raise HTTPException(400, "A task can't depend on itself")
    with db.connect() as con:
        task = require_task(con, task_id)
        other = require_task(con, body.depends_on_id)
        if engine.creates_cycle(engine.dependency_pairs(con), task_id, body.depends_on_id):
            raise HTTPException(409, f"“{other['title']}” already depends on “{task['title']}”, so that would make a loop")
        con.execute("INSERT OR IGNORE INTO dependencies(task_id, depends_on_id) VALUES(?, ?)", (task_id, body.depends_on_id))
        db.log_activity(con, task_id, f"Needs “{other['title']}” first")
        changed(con)
        return db.task_detail(con, task_id)


@app.delete("/api/tasks/{task_id}/dependencies/{depends_on_id}")
def delete_dependency(task_id: int, depends_on_id: int):
    with db.connect() as con:
        require_task(con, task_id)
        con.execute("DELETE FROM dependencies WHERE task_id = ? AND depends_on_id = ?", (task_id, depends_on_id))
        changed(con)
        return db.task_detail(con, task_id)


# ---------- dashboard & insights ----------

@app.get("/api/dashboard")
def dashboard():
    with db.connect() as con:
        settings = db.get_settings(con)
        tasks = db.list_tasks(con)
    today = date.today()
    now = datetime.now(timezone.utc)
    this_week = engine.iso_week(today)
    open_tasks = [t for t in tasks if t["status"] != "done"]

    def due(t):
        return engine.parse_date(t.get("due_at"))

    def completed_at(t):
        return engine.parse_dt(t.get("completed_at"))

    kpis = {
        "open": len(open_tasks),
        "active": sum(t["status"] == "active" for t in tasks),
        "ram_slots": int(settings["ram_slots"]),
        "backlog": sum(t["status"] == "backlog" for t in tasks),
        "basket": sum(t["status"] == "basket" for t in tasks),
        "due_this_week": sum(1 for t in open_tasks if due(t) and engine.iso_week(due(t)) == this_week),
        "overdue": sum(1 for t in open_tasks if due(t) and due(t) < today),
        "at_risk": sum(1 for t in open_tasks if t["at_risk"]),
        "done_this_week": sum(1 for t in tasks if t["status"] == "done" and completed_at(t)
                              and engine.iso_week(completed_at(t).astimezone().date()) == this_week),
    }
    weeks = []
    for w in engine.next_weeks(today, 8):
        wt = [t for t in open_tasks if t["assigned_week"] == w]
        weeks.append({
            "week": w, "start": engine.week_start(w).isoformat(), "capacity": settings["weekly_capacity_hours"],
            "hours": sum(engine.EFFORT_HOURS.get(t["effort"], 6) for t in wt),
            "tasks": [{k: t[k] for k in ("id", "title", "status", "region", "due_at", "effort", "at_risk", "priority", "score")}
                      for t in sorted(wt, key=lambda t: -t["score"])],
        })
    horizon_end = engine.week_start(engine.next_weeks(today, 8)[-1]) + timedelta(days=7)
    later = sum(1 for t in open_tasks if t["assigned_week"] and engine.week_start(t["assigned_week"]) >= horizon_end)

    monday = today - timedelta(days=today.weekday())
    calendar = []
    for i in range(42):
        d = monday + timedelta(days=i)
        items = [t for t in open_tasks if due(t) == d]
        calendar.append({"date": d.isoformat(), "count": len(items), "titles": [t["title"] for t in items[:5]]})
    overdue_count = kpis["overdue"]

    regions = {"logical": 0, "balanced": 0, "creative": 0}
    for t in open_tasks:
        regions[region_for(t["creative_score"])] += 1

    trend = []
    for i in range(7, -1, -1):
        start = monday - timedelta(weeks=i)
        end = start + timedelta(days=7)
        trend.append({
            "week": engine.iso_week(start), "start": start.isoformat(),
            "completed": sum(1 for t in tasks if (c := completed_at(t)) and start <= c.astimezone().date() < end),
            "created": sum(1 for t in tasks if (c := engine.parse_dt(t["created_at"])) and start <= c.astimezone().date() < end),
        })
    return {"kpis": kpis, "weeks": weeks, "later": later, "calendar": calendar, "overdue": overdue_count,
            "regions": regions, "trend": trend, "insights": engine.computed_insights(tasks, settings, today, now)}


@app.get("/api/insights")
def insights():
    with db.connect() as con:
        settings = db.get_settings(con)
        tasks = db.list_tasks(con)
        briefing = con.execute("SELECT * FROM insights WHERE kind = 'briefing' ORDER BY id DESC LIMIT 1").fetchone()
    return {"computed": engine.computed_insights(tasks, settings, date.today()),
            "briefing": dict(briefing) if briefing else None}


# ---------- settings ----------

@app.get("/api/settings")
def get_settings():
    with db.connect() as con:
        return db.get_settings(con)


@app.put("/api/settings")
def put_settings(body: SettingsUpdate):
    values = body.model_dump(exclude_unset=True)
    if values.get("anthropic_api_key") == "":
        values.pop("anthropic_api_key")  # blank field means "keep the current key"
    # one desktop wallpaper at a time: Lively, or Memory's built-in one
    if values.get("start_lively"):
        values["desktop_wallpaper"] = False
    elif values.get("desktop_wallpaper"):
        values["start_lively"] = False
    with db.connect() as con:
        db.set_settings(con, values)
        changed(con, fill=True)
        s = db.get_settings(con)
    if "dev_tunnel_id" in values:
        tunnel.start(s.get("dev_tunnel_id") or "")
    if values.get("start_lively"):
        lively.ensure(wallpaper.port_from_env(), delay=0)
    if "desktop_wallpaper" in values or ("wallpaper_screens" in values and s.get("desktop_wallpaper")):
        if s.get("desktop_wallpaper"):
            wallpaper.start(wallpaper.port_from_env(), s.get("wallpaper_screens", "all"))
        else:
            wallpaper.stop()
    return s


@app.get("/api/wallpaper")
def wallpaper_status():
    with db.connect() as con:
        s = db.get_settings(con)
    return {"enabled": bool(s.get("desktop_wallpaper")), **wallpaper.status(),
            "lively": {"enabled": bool(s.get("start_lively")), **lively.status()}}


@app.post("/api/wallpaper/restart")
def wallpaper_restart():
    with db.connect() as con:
        s = db.get_settings(con)
    if not s.get("desktop_wallpaper"):
        raise HTTPException(400, "Turn on the desktop wallpaper in Settings first.")
    wallpaper.start(wallpaper.port_from_env(), s.get("wallpaper_screens", "all"))
    wallpaper.restart()
    return {"ok": True}


@app.delete("/api/settings/anthropic_api_key")
def clear_key():
    with db.connect() as con:
        db.set_settings(con, {"anthropic_api_key": ""})
        return db.get_settings(con)


# ---------- claude ----------

def _claude(fn, *args):
    try:
        return fn(*args)
    except claude_service.NotConfigured as e:
        raise HTTPException(400, str(e))
    except claude_service.anthropic.AuthenticationError:
        raise HTTPException(400, "Anthropic rejected the API key. Check it in Settings.")
    except claude_service.anthropic.RateLimitError:
        raise HTTPException(429, "Claude is rate limited right now. Try again in a minute.")
    except claude_service.anthropic.APIStatusError as e:
        raise HTTPException(502, f"Claude API error ({e.status_code}): {e.message}")
    except claude_service.anthropic.APIConnectionError:
        raise HTTPException(502, "Couldn't reach the Claude API. Check your network.")
    except RuntimeError as e:
        raise HTTPException(502, str(e))


@app.post("/api/claude/chat")
def claude_chat(body: ChatBody):
    return _claude(claude_service.chat, [m.model_dump() for m in body.messages])


@app.post("/api/claude/delegate")
def claude_delegate():
    return _claude(claude_service.delegate)


@app.post("/api/claude/delegate/apply")
def claude_apply(body: DelegateApply):
    claude_service.apply_delegation([a.model_dump() for a in body.assignments])
    bus.publish("state")
    return {"ok": True}


@app.post("/api/claude/insight")
def claude_insight(body: InsightBody):
    try:
        return _claude(claude_service.insight, body.task_id)
    except KeyError:
        raise HTTPException(404, "Task not found")


@app.post("/api/open")
def open_in_browser(body: OpenBody, request: Request):
    """Open Memory on the desktop: a browser tab, a full app window, or a pop-up window for one task / a new task.
    The desktop wallpaper uses this, since a wallpaper host can't open windows itself. Only opens this app's own URL."""
    if body.task_id is not None:
        with db.connect() as con:
            if not db.get_task(con, body.task_id):
                raise HTTPException(404, "Task not found")
    base = f"http://localhost:{request.url.port or 8765}/"
    new = "#new" + (f"&slot={body.new_slot}" if body.new_slot is not None else "") + (f"&after={body.new_after}" if body.new_after is not None else "")
    frag = f"#task={body.task_id}" if body.task_id is not None else new if body.new else f"#{body.view}" if body.view else ""
    if body.window == "tab":
        url = base + frag
        webbrowser.open(url)
        return {"ok": True, "url": url, "opened": "tab"}
    pid = uuid.uuid4().hex[:10]
    windows.alive(pid)  # counts as open straight away, so the wallpaper locks before the window even appears
    if body.window == "app":
        url = f"{base}?win={pid}{frag}"
        return {"ok": True, "url": url, "opened": desktop.open_window(url, "app")}
    # One pop-up at a time: older pop-up windows close themselves when they hear about a newer one.
    url = f"{base}?popup={pid}{frag}"
    bus.publish("popup", {"pid": pid})
    return {"ok": True, "url": url, "opened": desktop.open_window(url, "popup")}


_latest_release: dict = {"at": 0.0, "data": None}


def _version_tuple(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in v.lstrip("v").split("-")[0].split(".") if x.isdigit())


@app.get("/api/version")
def version_info():
    """This version, and the newest GitHub release (checked at most every 6 hours). A private repository's
    releases aren't visible without signing in, so then `latest` is simply unknown."""
    import time
    import requests
    if time.time() - _latest_release["at"] > 6 * 3600:
        _latest_release["at"] = time.time()
        try:
            r = requests.get(f"https://api.github.com/repos/{REPO}/releases/latest", timeout=8,
                             headers={"Accept": "application/vnd.github+json", "User-Agent": f"Memory/{__version__}"})
            if r.ok:
                d = r.json()
                setup = next((a["browser_download_url"] for a in d.get("assets", []) if a["name"].lower().endswith(".exe")), None)
                _latest_release["data"] = {"version": d["tag_name"].lstrip("v"), "url": d["html_url"], "download": setup}
        except requests.RequestException:
            pass
    latest = _latest_release["data"]
    newer = bool(latest and _version_tuple(latest["version"]) > _version_tuple(__version__))
    return {"version": __version__, "latest": latest, "update_available": newer, "frozen": paths.FROZEN}


@app.get("/api/system")
def system_info():
    """Computer specs plus the latest CPU/RAM/GPU/disk/network sample (for the desktop overlay)."""
    return {"specs": sysinfo.specs(), "usage": sysinfo.usage()}


@app.post("/api/quicklinks/{index}/open")
def open_quick_link(index: int):
    """Open one of the saved quick links. Only saved links can be opened, picked by position."""
    with db.connect() as con:
        links = db.get_settings(con).get("quick_links") or []
    if not 0 <= index < len(links):
        raise HTTPException(404, "No such quick link")
    target = links[index]["target"].strip()
    if target.lower().startswith(("http://", "https://")):
        webbrowser.open(target)
        return {"ok": True}
    path = os.path.expandvars(os.path.expanduser(target))
    looks_like_path = path[1:3] in (":\\", ":/") or path.startswith("\\\\")
    if looks_like_path and not os.path.exists(path):
        raise HTTPException(404, f"Couldn't find {target}")
    try:
        os.startfile(path)  # folders open in Explorer, files in their app, app links (ms-teams:) in their app
    except (OSError, AttributeError) as e:
        raise HTTPException(400, f"Couldn't open {target}: {e}")
    return {"ok": True}


@app.post("/api/windows/{pid}/alive")
def window_alive(pid: str = PathParam(pattern=r"^[0-9a-f]{6,32}$")):
    windows.alive(pid)
    return {"ok": True}


@app.post("/api/windows/{pid}/closed")
def window_closed(pid: str = PathParam(pattern=r"^[0-9a-f]{6,32}$")):
    windows.closed(pid)
    return {"ok": True}


@app.post("/api/claude/classify")
def claude_classify():
    n = _claude(claude_service.classify)
    bus.publish("state")
    return {"updated": n}


# ---------- planner ----------

@app.get("/api/planner/status")
def planner_status():
    return planner_sync.status()


@app.post("/api/planner/login")
def planner_login(body: LoginBody | None = None):
    try:
        return planner_sync.start_login() if body and body.method == "code" else planner_sync.start_browser_login()
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    except ValueError as e:  # msal raises ValueError for malformed authority / client id
        raise HTTPException(400, f"Azure configuration problem: {e}")


@app.post("/api/planner/logout")
def planner_logout():
    planner_sync.logout()
    return planner_sync.status()


@app.post("/api/planner/sync")
async def planner_sync_endpoint(request: Request, allow_empty: bool = False):
    """Two ways in. With a {"tasks": [...]} body (Power Automate): a one-way snapshot sync that needs the bearer
    token. With no body (the Planner button in Memory): pull from Microsoft Graph, which only works locally."""
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > planner_push.MAX_BODY_BYTES:
        return JSONResponse({"success": False, "error": "Request too large."}, status_code=413)
    raw = await request.body()
    if raw.strip() or request.headers.get("authorization"):
        return await _planner_push(request, raw, allow_empty)
    if not is_local_request(request):
        return JSONResponse({"success": False, "error": "Unauthorized."}, status_code=401, headers={"WWW-Authenticate": "Bearer"})
    result = await asyncio.to_thread(planner_sync.sync)
    bus.publish("state")
    return result


async def _planner_push(request: Request, raw: bytes, allow_empty: bool):
    client = request.client.host if request.client else "unknown"
    if planner_push.throttled(client):
        return JSONResponse({"success": False, "error": "Too many failed attempts. Try again in a minute."}, status_code=429)
    if not planner_push.configured():
        return JSONResponse({"success": False, "error": "Planner sync isn't configured on this server."}, status_code=503)
    if not planner_push.authorize(request.headers.get("authorization"), client):
        return JSONResponse({"success": False, "error": "Unauthorized."}, status_code=401, headers={"WWW-Authenticate": "Bearer"})
    if len(raw) > planner_push.MAX_BODY_BYTES:
        return JSONResponse({"success": False, "error": "Request too large."}, status_code=413)
    if "json" not in request.headers.get("content-type", "").lower():
        return JSONResponse({"success": False, "error": "Send the body as JSON (Content-Type: application/json)."}, status_code=415)
    try:
        body = PlannerPushBody.model_validate_json(raw)
    except ValidationError as e:
        problems = [f"{'.'.join(str(p) for p in err['loc']) or 'body'}: {err['msg']}" for err in e.errors()[:20]]
        return JSONResponse({"success": False, "error": "Invalid request.", "details": problems}, status_code=400)
    try:
        result = await asyncio.to_thread(planner_push.apply, body.tasks, allow_empty)
    except Exception:
        log.exception("Planner sync failed")
        return JSONResponse({"success": False, "error": "Internal error."}, status_code=500)
    bus.publish("state")
    return result


@app.get("/api/tunnel")
def tunnel_status():
    return tunnel.status()


@app.get("/api/planner/push-status")
def planner_push_status():
    """For Settings: whether the Power Automate token is configured (never the token itself), and the last sync."""
    with db.connect() as con:
        last = db.get_sync(con, "planner_last_result")
        return {"configured": planner_push.configured(), "token_variable": planner_push.TOKEN_ENV, "tunnel": tunnel.status(),
                "last_sync": db.get_sync(con, "planner_last_sync"), "last_result": last if (last or {}).get("via") == planner_push.VIA else None}


# ---------- events ----------

@app.get("/api/events")
async def events(request: Request):
    if request.query_params.get("client") == "wallpaper":
        lively.note_wallpaper_client()
    q = bus.subscribe()

    async def stream():
        try:
            yield "event: hello\ndata: {}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event, payload = await asyncio.wait_for(q.get(), timeout=15)
                    yield f"event: {event}\ndata: {payload}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            bus.unsubscribe(q)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


class FrontendFiles(StaticFiles):
    """Static files that the browser revalidates on every load (a cheap 304), so app updates show up without a hard refresh."""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


app.mount("/", FrontendFiles(directory=FRONTEND, html=True), name="frontend")
