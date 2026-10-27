"""SQLite storage for Memory. One connection per call; WAL so the reminder loop and API can share."""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("MEMORY_DATA_DIR", ROOT / "data"))
DB_PATH = DATA_DIR / "memory.db"
ATTACH_DIR = DATA_DIR / "attachments"

DEFAULT_SETTINGS = {
    "ram_slots": 7,
    "weekly_capacity_hours": 20,
    "auto_fill": True,
    "model": "claude-opus-5-5",
    "anthropic_api_key": "",
    "azure_client_id": "",
    "azure_tenant_id": "organizations",
    "planner_auto_sync": True,
    "briefing_enabled": True,
    "theme": "blue",
    "notify_email": "",
    "slot_positions": {},  # synapse index -> [x, y, z, nx, ny, nz] where the user dragged it (Arrange mode)  # where email notifications go; blank = the signed-in Microsoft account
    # quick links on the desktop wallpaper / left rail: web addresses, app links (ms-teams:) or file/folder paths
    "quick_links": [
        {"label": "Outlook", "target": "https://outlook.office.com/mail/"},
        {"label": "Teams", "target": "https://teams.microsoft.com/"},
        {"label": "Planner", "target": "https://tasks.office.com/"},
        {"label": "OneDrive", "target": "https://www.office.com/onedrive"},
        {"label": "Documents", "target": "~\\Documents"},
        {"label": "Downloads", "target": "~\\Downloads"},
    ],
}
SECRET_SETTINGS = {"anthropic_api_key"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    notes_html TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'basket',
    slot_index INTEGER,
    region TEXT NOT NULL DEFAULT 'balanced',
    creative_score INTEGER NOT NULL DEFAULT 50,
    creative_locked INTEGER NOT NULL DEFAULT 0,
    priority TEXT NOT NULL DEFAULT 'medium',
    important INTEGER NOT NULL DEFAULT 0,
    my_day TEXT,
    effort TEXT NOT NULL DEFAULT 'M',
    due_at TEXT,
    reminder_at TEXT,
    reminded INTEGER NOT NULL DEFAULT 0,
    due_notified INTEGER NOT NULL DEFAULT 0,
    repeat TEXT,
    assigned_week TEXT,
    week_locked INTEGER NOT NULL DEFAULT 0,
    at_risk INTEGER NOT NULL DEFAULT 0,
    pinned INTEGER NOT NULL DEFAULT 0,
    growth REAL NOT NULL DEFAULT 0,
    score REAL NOT NULL DEFAULT 0,
    tags TEXT NOT NULL DEFAULT '[]',
    source TEXT NOT NULL DEFAULT 'local',
    external_id TEXT,
    etag TEXT,
    details_etag TEXT,
    plan_name TEXT,
    bucket_name TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    activated_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_tasks_status ON tasks(status);
CREATE UNIQUE INDEX IF NOT EXISTS ix_tasks_external ON tasks(external_id) WHERE external_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS checklist_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    done INTEGER NOT NULL DEFAULT 0,
    position INTEGER NOT NULL DEFAULT 0,
    external_id TEXT
);
CREATE INDEX IF NOT EXISTS ix_check_task ON checklist_items(task_id);

CREATE TABLE IF NOT EXISTS attachments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    stored_name TEXT NOT NULL,
    mime TEXT NOT NULL DEFAULT 'application/octet-stream',
    size INTEGER NOT NULL DEFAULT 0,
    is_screenshot INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_attach_task ON attachments(task_id);

CREATE TABLE IF NOT EXISTS links (
    a_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    b_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    kind TEXT NOT NULL DEFAULT 'auto',
    strength REAL NOT NULL DEFAULT 0.5,
    PRIMARY KEY (a_id, b_id)
);

-- task_id can't really start until depends_on_id is done (directed; cycles are refused by the API)
CREATE TABLE IF NOT EXISTS dependencies (
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    depends_on_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    PRIMARY KEY (task_id, depends_on_id)
);

CREATE TABLE IF NOT EXISTS insights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER REFERENCES tasks(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_activity_task ON activity(task_id);

CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sync_state (key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    title TEXT NOT NULL,
    notes_html TEXT NOT NULL DEFAULT '',
    priority TEXT NOT NULL DEFAULT 'medium',
    effort TEXT NOT NULL DEFAULT 'M',
    tags TEXT NOT NULL DEFAULT '[]',
    checklist TEXT NOT NULL DEFAULT '[]',
    creative_score INTEGER,
    repeat TEXT NOT NULL DEFAULT '',
    notify TEXT NOT NULL DEFAULT 'desktop',
    due_in_days INTEGER,
    created_at TEXT NOT NULL
);
"""

BUILTIN_TEMPLATES = [
    {"name": "Meeting prep", "title": "Prep for meeting", "effort": "S", "tags": ["meeting"], "due_in_days": 1,
     "notes_html": "<h2>Agenda</h2><ul><li></li></ul><h2>Notes</h2><p></p><h2>Actions</h2><ul class=\"checks\"><li data-checked=\"false\"></li></ul>",
     "checklist": ["Confirm agenda and attendees", "Review last notes and open actions", "Draft talking points", "Send the pre-read"]},
    {"name": "Weekly report", "title": "Weekly report", "effort": "S", "repeat": "weekly", "tags": ["report"], "due_in_days": 4, "creative_score": 35,
     "checklist": ["Gather this week's numbers", "Summarise wins, risks and blockers", "Draft the report", "Send to stakeholders"]},
    {"name": "Bug fix", "title": "Fix: ", "priority": "high", "effort": "M", "tags": ["bug"], "creative_score": 15,
     "checklist": ["Reproduce the issue", "Find the root cause", "Fix and test", "Deploy and verify", "Update the ticket"]},
    {"name": "Creative brief", "title": "Creative brief: ", "effort": "L", "tags": ["creative"], "creative_score": 85,
     "checklist": ["Define the audience and goal", "Gather references", "Sketch three directions", "Review and refine", "Hand off the final version"]},
    {"name": "Email follow-up", "title": "Follow up: ", "effort": "S", "tags": ["email"], "due_in_days": 2, "notify": "both",
     "checklist": ["Clarify what's being asked", "Reply or delegate", "Set a reminder for their response"]},
]


def insert_template(con, t: dict) -> int:
    cur = con.execute(
        """INSERT INTO templates(name, title, notes_html, priority, effort, tags, checklist, creative_score, repeat, notify,
                                 due_in_days, created_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (t["name"], t["title"], t.get("notes_html") or "", t.get("priority") or "medium", t.get("effort") or "M",
         json.dumps(t.get("tags") or []), json.dumps(t.get("checklist") or []), t.get("creative_score"),
         t.get("repeat") or "", t.get("notify") or "desktop", t.get("due_in_days"), now_iso()))
    return cur.lastrowid


def list_templates(con) -> list[dict]:
    out = []
    for r in con.execute("SELECT * FROM templates ORDER BY name COLLATE NOCASE"):
        d = dict(r)
        d["tags"], d["checklist"] = json.loads(d["tags"]), json.loads(d["checklist"])
        out.append(d)
    return out


def _migrate(con) -> None:
    """Add columns introduced after a database was created, and seed the built-in templates once."""
    cols = {r["name"] for r in con.execute("PRAGMA table_info(tasks)")}
    if "notify" not in cols:
        con.execute("ALTER TABLE tasks ADD COLUMN notify TEXT NOT NULL DEFAULT 'desktop'")
    if not get_sync(con, "templates_seeded"):
        for t in BUILTIN_TEMPLATES:
            insert_template(con, t)
        set_sync(con, "templates_seeded", True)

TASK_FIELDS = {
    "title", "notes_html", "status", "slot_index", "region", "creative_score", "creative_locked",
    "priority", "important", "my_day", "effort", "due_at", "reminder_at", "reminded", "due_notified",
    "repeat", "assigned_week", "week_locked", "at_risk", "pinned", "growth", "score", "tags", "source",
    "external_id", "etag", "details_etag", "plan_name", "bucket_name", "completed_at", "activated_at", "notify",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def init() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ATTACH_DIR.mkdir(parents=True, exist_ok=True)
    with connect() as con:
        con.executescript(SCHEMA)
        _migrate(con)


@contextmanager
def connect():
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


# ---------- settings ----------

def get_settings(con, include_secrets: bool = False) -> dict:
    out = dict(DEFAULT_SETTINGS)
    for row in con.execute("SELECT key, value FROM settings"):
        out[row["key"]] = json.loads(row["value"])
    if not out.get("anthropic_api_key"):
        out["anthropic_api_key"] = os.environ.get("ANTHROPIC_API_KEY", "")
    if not out.get("azure_client_id"):
        out["azure_client_id"] = os.environ.get("AZURE_CLIENT_ID", "")
    env_tenant = os.environ.get("AZURE_TENANT_ID")
    if env_tenant and out.get("azure_tenant_id") in ("", "organizations"):
        out["azure_tenant_id"] = env_tenant
    if not include_secrets:
        for k in SECRET_SETTINGS:
            out["has_" + k] = bool(out.pop(k))
    return out


def set_settings(con, values: dict) -> None:
    for key, value in values.items():
        if key not in DEFAULT_SETTINGS:
            continue
        con.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value)),
        )


def get_sync(con, key: str, default=None):
    row = con.execute("SELECT value FROM sync_state WHERE key = ?", (key,)).fetchone()
    return json.loads(row["value"]) if row else default


def set_sync(con, key: str, value) -> None:
    con.execute(
        "INSERT INTO sync_state(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, json.dumps(value)),
    )


# ---------- tasks ----------

def row_to_task(row: sqlite3.Row) -> dict:
    t = dict(row)
    t["tags"] = json.loads(t.get("tags") or "[]")
    for k in ("important", "pinned", "at_risk", "week_locked", "creative_locked", "reminded", "due_notified"):
        t[k] = bool(t[k])
    return t


def list_tasks(con, include_done: bool = True) -> list[dict]:
    sql = """
        SELECT t.*,
          (SELECT COUNT(*) FROM checklist_items c WHERE c.task_id = t.id) AS checklist_total,
          (SELECT COUNT(*) FROM checklist_items c WHERE c.task_id = t.id AND c.done = 1) AS checklist_done,
          (SELECT COUNT(*) FROM attachments a WHERE a.task_id = t.id) AS attachment_count
        FROM tasks t
    """
    if not include_done:
        sql += " WHERE t.status != 'done'"
    return [row_to_task(r) for r in con.execute(sql + " ORDER BY t.score DESC, t.id")]


def get_task(con, task_id: int) -> dict | None:
    row = con.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return row_to_task(row) if row else None


def insert_task(con, fields: dict) -> int:
    data = {k: v for k, v in fields.items() if k in TASK_FIELDS}
    if "tags" in data and not isinstance(data["tags"], str):
        data["tags"] = json.dumps(data["tags"])
    ts = now_iso()
    data.setdefault("created_at", ts)
    data["updated_at"] = ts
    cols = ", ".join(data)
    marks = ", ".join("?" for _ in data)
    cur = con.execute(f"INSERT INTO tasks({cols}) VALUES({marks})", tuple(data.values()))
    return cur.lastrowid


def update_task(con, task_id: int, fields: dict, touch: bool = True) -> None:
    data = {k: v for k, v in fields.items() if k in TASK_FIELDS}
    if not data and not touch:
        return
    if "tags" in data and not isinstance(data["tags"], str):
        data["tags"] = json.dumps(data["tags"])
    for k, v in list(data.items()):
        if isinstance(v, bool):
            data[k] = int(v)
    if touch:
        data["updated_at"] = now_iso()
    sets = ", ".join(f"{k} = ?" for k in data)
    con.execute(f"UPDATE tasks SET {sets} WHERE id = ?", (*data.values(), task_id))


def log_activity(con, task_id: int, text: str) -> None:
    con.execute("INSERT INTO activity(task_id, text, created_at) VALUES(?, ?, ?)", (task_id, text, now_iso()))


def task_detail(con, task_id: int) -> dict | None:
    t = get_task(con, task_id)
    if not t:
        return None
    t["checklist"] = [dict(r) | {"done": bool(r["done"])} for r in con.execute(
        "SELECT * FROM checklist_items WHERE task_id = ? ORDER BY position, id", (task_id,))]
    t["attachments"] = [dict(r) | {"is_screenshot": bool(r["is_screenshot"])} for r in con.execute(
        "SELECT * FROM attachments WHERE task_id = ? ORDER BY id", (task_id,))]
    t["links"] = [dict(r) for r in con.execute(
        """SELECT l.kind, l.strength, o.id, o.title, o.status FROM links l
           JOIN tasks o ON o.id = CASE WHEN l.a_id = ? THEN l.b_id ELSE l.a_id END
           WHERE l.a_id = ? OR l.b_id = ? ORDER BY l.strength DESC""", (task_id, task_id, task_id))]
    t["needs"] = [dict(r) for r in con.execute(
        """SELECT o.id, o.title, o.status FROM dependencies d JOIN tasks o ON o.id = d.depends_on_id
           WHERE d.task_id = ? ORDER BY o.title""", (task_id,))]
    t["unlocks"] = [dict(r) for r in con.execute(
        """SELECT o.id, o.title, o.status FROM dependencies d JOIN tasks o ON o.id = d.task_id
           WHERE d.depends_on_id = ? ORDER BY o.title""", (task_id,))]
    t["insights"] = [dict(r) for r in con.execute(
        "SELECT * FROM insights WHERE task_id = ? ORDER BY id DESC LIMIT 10", (task_id,))]
    t["activity"] = [dict(r) for r in con.execute(
        "SELECT * FROM activity WHERE task_id = ? ORDER BY id DESC LIMIT 30", (task_id,))]
    t["checklist_total"] = len(t["checklist"])
    t["checklist_done"] = sum(1 for c in t["checklist"] if c["done"])
    t["attachment_count"] = len(t["attachments"])
    return t
