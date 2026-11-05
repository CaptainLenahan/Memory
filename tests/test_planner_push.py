"""Power Automate → Memory Planner sync (POST /api/planner/sync with a {"tasks": [...]} body)."""
import copy
import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend import db
from backend.app import app

TOKEN = "test-token-" + "x" * 40
AUTH = {"Authorization": f"Bearer {TOKEN}"}

SAMPLE = [
    {"id": "KGEFAhIzkUu2r_CGbNO6VmUADrzz", "title": "Microsoft Update Catalog Ingestion", "percentComplete": 0, "priority": 5,
     "dueDate": "2026-10-15T10:00:00Z", "startDate": None, "planId": "oM7TZEj9TUivltGR1o1682UAH2h9", "bucketId": "nRXbhxBR-EiMvRhRXledDGUACBIX"},
    {"id": "KkR6v67MIEGkdiisa0j0x2UADmlB", "title": "EPIC DCS Report", "percentComplete": 50, "priority": 5,
     "dueDate": "2026-10-30T10:00:00Z", "startDate": "2026-10-26T10:00:00Z", "planId": "r0IF8nU7BkCvDMGIIRLy42UABgYS", "bucketId": "k-ZbajqFUE-UHcXnxk5ohGUAJ4xI"},
    {"id": "MwjCQnMSo0qyM4gF4YmF7mUAMbdy", "title": "Add table and visual map of external data transfers in Shippy", "percentComplete": 0,
     "priority": 5, "dueDate": None, "startDate": None, "planId": "gkhLVPB8C0WIA9yU3xRrRWUAEp51", "bucketId": "dVaLZZelaUWgGjA2KS7_HGUAMoLz"},
]
IDS = [t["id"] for t in SAMPLE]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("MEMORY_PLANNER_SYNC_TOKEN", TOKEN)
    from backend import planner_push
    planner_push._failures.clear()
    with TestClient(app) as c:
        yield c
        with db.connect() as con:  # leave other tests a clean slate
            con.execute("DELETE FROM tasks WHERE source = 'planner'")


def push(client, tasks, headers=AUTH, **params):
    return client.post("/api/planner/sync", json={"tasks": tasks}, headers=headers, params=params)


def planner_rows(client):
    return {t["external_id"]: t for t in client.get("/api/state").json()["tasks"] if t["source"] == "planner"}


# ---------- import, idempotency, upsert ----------

def test_first_import_creates_tasks(client):
    r = push(client, SAMPLE)
    assert r.status_code == 200
    body = r.json()
    assert body["success"] and body["received"] == 3 and body["created"] == 3 and body["updated"] == 0 and body["archived"] == 0
    rows = planner_rows(client)
    assert set(rows) == set(IDS)
    epic = rows["KkR6v67MIEGkdiisa0j0x2UADmlB"]
    assert epic["title"] == "EPIC DCS Report" and epic["percent_complete"] == 50 and epic["priority"] == "medium"
    assert epic["plan_id"] == "r0IF8nU7BkCvDMGIIRLy42UABgYS" and epic["bucket_id"] == "k-ZbajqFUE-UHcXnxk5ohGUAJ4xI"
    assert epic["start_at"] and epic["due_at"] and epic["status"] == "basket" and epic["sync_via"] == "power-automate"
    assert epic["last_synced_at"].endswith("+00:00")          # UTC
    assert isinstance(epic["id"], int) and epic["id"] != epic["external_id"]   # local key stays the local key


def test_same_payload_twice_creates_no_duplicates(client):
    push(client, SAMPLE)
    r = push(client, SAMPLE).json()
    assert r["created"] == 0 and r["updated"] == 0 and r["unchanged"] == 3
    with db.connect() as con:
        n = con.execute("SELECT COUNT(*) FROM tasks WHERE source = 'planner'").fetchone()[0]
    assert n == 3


def test_source_and_external_id_are_unique_in_the_database(client):
    push(client, SAMPLE)
    with db.connect() as con, pytest.raises(sqlite3.IntegrityError):
        db.insert_task(con, {"title": "dup", "source": "planner", "external_id": IDS[0]})
    with db.connect() as con:  # same external id from another source is a different record
        db.insert_task(con, {"title": "other source", "source": "email", "external_id": IDS[0]})
        con.execute("DELETE FROM tasks WHERE source = 'email' AND external_id = ?", (IDS[0],))


def test_changed_title_updates_existing_task(client):
    push(client, SAMPLE)
    before = planner_rows(client)[IDS[0]]
    changed = copy.deepcopy(SAMPLE)
    changed[0]["title"] = "Microsoft Update Catalog Ingestion v2"
    r = push(client, changed).json()
    assert r["updated"] == 1 and r["created"] == 0
    after = planner_rows(client)[IDS[0]]
    assert after["title"] == "Microsoft Update Catalog Ingestion v2" and after["id"] == before["id"]


def test_changed_percent_complete_updates_existing_task(client):
    push(client, SAMPLE)
    changed = copy.deepcopy(SAMPLE)
    changed[2]["percentComplete"] = 50
    assert push(client, changed).json()["updated"] == 1
    assert planner_rows(client)[IDS[2]]["percent_complete"] == 50


def test_null_due_date_works(client):
    one = [dict(SAMPLE[0], dueDate=None)]
    assert push(client, one).status_code == 200
    assert planner_rows(client)[IDS[0]]["due_at"] is None


def test_null_start_date_works(client):
    one = [dict(SAMPLE[1], startDate=None)]
    assert push(client, one).status_code == 200
    assert planner_rows(client)[IDS[1]]["start_at"] is None


def test_user_fields_survive_an_update(client):
    push(client, SAMPLE)
    local = planner_rows(client)[IDS[0]]
    client.patch(f"/api/tasks/{local['id']}", json={"notes_html": "<p>my notes</p>", "important": True})
    client.post(f"/api/tasks/{local['id']}/checklist", json={"text": "my step"})
    changed = copy.deepcopy(SAMPLE)
    changed[0]["title"] = "Renamed in Planner"
    push(client, changed)
    detail = client.get(f"/api/tasks/{local['id']}").json()
    assert detail["title"] == "Renamed in Planner"
    assert detail["notes_html"] == "<p>my notes</p>" and detail["important"] and detail["checklist_total"] == 1


# ---------- validation ----------

@pytest.mark.parametrize("bad", [
    [{k: v for k, v in SAMPLE[0].items() if k != "id"}],              # missing id
    [dict(SAMPLE[0], id="")],                                           # empty id
    [dict(SAMPLE[0], id="has spaces/and;semicolons")],                  # not a Planner id
    [{k: v for k, v in SAMPLE[0].items() if k != "title"}],           # missing title
    [dict(SAMPLE[0], title="   ")],                                     # blank title
    [dict(SAMPLE[0], percentComplete=150)],                             # out of range
    [dict(SAMPLE[0], percentComplete=-1)],
    [dict(SAMPLE[0], percentComplete="50")],                            # string, not integer
    [dict(SAMPLE[0], percentComplete=None)],
    [dict(SAMPLE[0], priority="high")],
    [dict(SAMPLE[0], dueDate="next friday")],                           # not ISO-8601
    [dict(SAMPLE[0], dueDate="2026-10-15T10:00:00")],                   # no timezone
    [dict(SAMPLE[0], dueDate="2026-10-15T10:00:00+05:00")],             # not UTC
    "not a list",
])
def test_malformed_requests_are_rejected_with_400(client, bad):
    r = client.post("/api/planner/sync", json={"tasks": bad}, headers=AUTH)
    assert r.status_code == 400 and r.json()["success"] is False and r.json()["details"]
    assert not planner_rows(client)


def test_missing_tasks_key_and_broken_json_are_400(client):
    assert client.post("/api/planner/sync", json={"items": SAMPLE}, headers=AUTH).status_code == 400
    r = client.post("/api/planner/sync", content=b'{"tasks": [', headers={**AUTH, "Content-Type": "application/json"})
    assert r.status_code == 400


def test_request_size_is_limited(client):
    huge = b'{"tasks": [' + b" " * (2 * 1024 * 1024 + 10) + b"]}"
    r = client.post("/api/planner/sync", content=huge, headers={**AUTH, "Content-Type": "application/json"})
    assert r.status_code == 413


# ---------- authentication ----------

def test_unauthorized_requests_are_rejected(client):
    assert push(client, SAMPLE, headers={}).status_code == 401
    assert push(client, SAMPLE, headers={"Authorization": "Bearer wrong-token"}).status_code == 401
    assert push(client, SAMPLE, headers={"Authorization": TOKEN}).status_code == 401          # not "Bearer <token>"
    r = push(client, SAMPLE, headers={"Authorization": "Bearer nope"})
    assert TOKEN not in r.text and r.headers.get("www-authenticate") == "Bearer"
    assert not planner_rows(client)


def test_disabled_without_a_configured_token(client, monkeypatch):
    monkeypatch.delenv("MEMORY_PLANNER_SYNC_TOKEN")
    assert push(client, SAMPLE).status_code == 503
    monkeypatch.setenv("MEMORY_PLANNER_SYNC_TOKEN", "too-short")
    assert push(client, SAMPLE, headers={"Authorization": "Bearer too-short"}).status_code == 503


def test_repeated_bad_tokens_are_throttled(client):
    codes = [push(client, SAMPLE, headers={"Authorization": "Bearer guess"}).status_code for _ in range(12)]
    assert codes[:10] == [401] * 10 and codes[-1] == 429


def test_token_is_never_exposed_to_the_browser(client):
    status = client.get("/api/planner/push-status").json()
    assert status["configured"] is True and TOKEN not in str(status)
    assert TOKEN not in client.get("/api/settings").text and TOKEN not in client.get("/api/state").text


def test_remote_callers_only_reach_the_sync_endpoint(client):
    tunnel = {"X-Forwarded-For": "52.1.2.3", "Host": "memory.example-tunnel.net"}
    assert client.get("/api/state", headers=tunnel).status_code == 403
    assert client.post("/api/tasks", json={"title": "x"}, headers=tunnel).status_code == 403
    assert client.post("/api/planner/sync", headers=tunnel).status_code == 401                 # no body + no token
    assert push(client, SAMPLE, headers={**AUTH, **tunnel}).status_code == 200


def test_other_websites_are_refused(client):
    r = client.post("/api/quicklinks/0/open", headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    assert client.get("/api/state", headers={"Origin": "http://localhost:8765"}).status_code == 200


# ---------- removal / archive / restore ----------

def test_absent_planner_tasks_are_archived_and_restored(client):
    push(client, SAMPLE)
    r = push(client, SAMPLE[:2]).json()                       # the third was completed (or removed) in Planner
    assert r["archived"] == 1
    rows = planner_rows(client)
    assert rows[IDS[2]]["status"] == "done" and rows[IDS[2]]["sync_archived"]
    assert rows[IDS[0]]["status"] != "done" and rows[IDS[1]]["status"] != "done"
    r = push(client, SAMPLE).json()                           # reopened in Planner
    assert r["restored"] == 1 and planner_rows(client)[IDS[2]]["status"] != "done"


def test_manually_created_tasks_are_untouched(client):
    mine = client.post("/api/tasks", json={"title": "My own task"}).json()
    push(client, SAMPLE)
    push(client, SAMPLE[:1])
    after = client.get(f"/api/tasks/{mine['id']}").json()
    assert after["status"] == mine["status"] and after["title"] == "My own task" and after["source"] == "local"
    client.delete(f"/api/tasks/{mine['id']}")


def test_tasks_completed_in_memory_stay_completed(client):
    push(client, SAMPLE)
    local = planner_rows(client)[IDS[0]]
    client.patch(f"/api/tasks/{local['id']}", json={"status": "done"})
    r = push(client, SAMPLE).json()
    assert r["kept_done"] == 1 and planner_rows(client)[IDS[0]]["status"] == "done"


def test_empty_snapshot_does_not_archive_everything(client):
    push(client, SAMPLE)
    r = push(client, []).json()
    assert r["archived"] == 0 and r["warnings"]
    assert all(t["status"] != "done" for t in planner_rows(client).values())
    assert push(client, [], allow_empty="true").json()["archived"] == 3


# ---------- one-way ----------

def test_planner_managed_fields_are_read_only_and_never_pushed_back(client, monkeypatch):
    pushed = []
    monkeypatch.setattr("backend.app.planner_sync.push_task", lambda task_id: pushed.append(task_id))
    push(client, SAMPLE)
    local = planner_rows(client)[IDS[0]]
    assert client.patch(f"/api/tasks/{local['id']}", json={"title": "Edited here"}).status_code == 409
    assert client.patch(f"/api/tasks/{local['id']}", json={"due_at": "2026-12-01"}).status_code == 409
    assert client.patch(f"/api/tasks/{local['id']}", json={"notes_html": "<p>fine</p>"}).status_code == 200
    client.patch(f"/api/tasks/{local['id']}", json={"status": "done"})
    assert pushed == []
