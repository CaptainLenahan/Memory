"""Microsoft Planner sync over Microsoft Graph, using msal's device-code flow.

Requires an Azure app registration (public client flows enabled) with delegated Tasks.ReadWrite + User.Read.
Pull: Planner tasks assigned to you land in the Basket. Push: completion, due date and checklist ticks go back.
"""
from __future__ import annotations

import html
import logging
import threading
from datetime import datetime, timezone

import msal
import requests

from . import db
from .classifier import creative_score

log = logging.getLogger("memory.planner")
GRAPH = "https://graph.microsoft.com/v1.0"
SCOPES = ["Tasks.ReadWrite", "User.Read", "Mail.Read", "Mail.Send"]  # mail: Inbox panel + email notifications
CACHE_PATH = db.DATA_DIR / "msal_cache.bin"

_lock = threading.Lock()
_pending_flow: dict | None = None
_browser_pending = False
_flow_error: str | None = None

# Plain-English fixes for the sign-in errors people actually hit.
_AADSTS_HELP = {
    "AADSTS50011": "Add http://localhost as a redirect URI: in the app registration, Authentication → Add a platform → "
                   "Mobile and desktop applications → custom redirect URI http://localhost.",
    "AADSTS500113": "Add http://localhost as a redirect URI: in the app registration, Authentication → Add a platform → "
                    "Mobile and desktop applications → custom redirect URI http://localhost.",
    "AADSTS7000218": "Turn on Allow public client flows in the app registration (Authentication), then try again.",
    "AADSTS65001": "Your organisation needs to approve this app: ask IT to grant admin consent for its permissions.",
    "AADSTS90094": "Your organisation needs to approve this app: ask IT to grant admin consent for its permissions.",
    "AADSTS53003": "Blocked by your organisation's Conditional Access policy. Ask IT to allow this app.",
    "AADSTS700016": "That client ID wasn't found in this tenant. Check the client ID and tenant ID in Settings.",
}


def _explain(result: dict) -> str:
    desc = result.get("error_description") or result.get("error") or "Sign-in didn't complete."
    code = next((c for c in _AADSTS_HELP if c in desc), None)
    return f"{_AADSTS_HELP[code]} ({code})" if code else desc.split(" Trace ID")[0]


# ---------- auth ----------

def _config() -> tuple[str, str]:
    with db.connect() as con:
        s = db.get_settings(con)
    return s.get("azure_client_id") or "", s.get("azure_tenant_id") or "organizations"


def _cache() -> msal.SerializableTokenCache:
    cache = msal.SerializableTokenCache()
    if CACHE_PATH.exists():
        cache.deserialize(CACHE_PATH.read_text())
    return cache


def _save(cache: msal.SerializableTokenCache) -> None:
    if cache.has_state_changed:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(cache.serialize())


def _app(cache) -> msal.PublicClientApplication | None:
    client_id, tenant = _config()
    if not client_id:
        return None
    return msal.PublicClientApplication(client_id, authority=f"https://login.microsoftonline.com/{tenant}", token_cache=cache)


def _token() -> str | None:
    cache = _cache()
    app = _app(cache)
    if not app:
        return None
    accounts = app.get_accounts()
    if not accounts:
        return None
    result = app.acquire_token_silent(SCOPES, account=accounts[0])
    _save(cache)
    return result.get("access_token") if result else None


def status() -> dict:
    client_id, tenant = _config()
    out = {"configured": bool(client_id), "tenant": tenant, "signed_in": False, "account": None,
           "pending": None, "error": _flow_error}
    if client_id:
        app = _app(_cache())
        accounts = app.get_accounts() if app else []
        if accounts:
            out["signed_in"] = True
            out["account"] = accounts[0].get("username")
    if _pending_flow:
        out["pending"] = {k: _pending_flow.get(k) for k in ("user_code", "verification_uri", "message")}
    elif _browser_pending:
        out["pending"] = {"method": "browser", "message": "Finish signing in on the Microsoft page that opened in your browser."}
    with db.connect() as con:
        out["last_sync"] = db.get_sync(con, "planner_last_sync")
        out["last_result"] = db.get_sync(con, "planner_last_result")
    return out


def start_browser_login() -> dict:
    """Sign in through the normal browser (authorization code + PKCE, redirect to http://localhost). Works where an
    organisation blocks device-code sign-in. The app registration needs the redirect URI http://localhost under
    "Mobile and desktop applications". A thread waits up to 5 minutes for the browser to come back."""
    global _browser_pending, _flow_error
    cache = _cache()
    app = _app(cache)
    if not app:
        raise RuntimeError("Set the Azure client ID in Settings first.")
    if not _browser_pending:
        _browser_pending, _flow_error = True, None

        def run():
            global _browser_pending, _flow_error
            from .reminders import bus
            try:
                result = app.acquire_token_interactive(SCOPES, prompt="select_account", timeout=300)
            except Exception as e:  # timeout, port in use, browser couldn't open
                result = {"error_description": str(e) or "Sign-in timed out."}
            _save(cache)
            _browser_pending = False
            if "access_token" not in result:
                _flow_error = _explain(result)
            bus.publish("planner", {"event": "login", "ok": "access_token" in result, "error": _flow_error})

        threading.Thread(target=run, daemon=True).start()
    return {"method": "browser", "message": "A Microsoft sign-in page opened in your browser. Finish signing in there."}


def start_login() -> dict:
    """Begin device-code sign-in (the fallback). The user opens verification_uri and enters user_code; a thread waits."""
    global _pending_flow, _flow_error
    cache = _cache()
    app = _app(cache)
    if not app:
        raise RuntimeError("Set the Azure client ID in Settings first.")
    flow = app.initiate_device_flow(scopes=SCOPES)
    if "user_code" not in flow:
        raise RuntimeError(flow.get("error_description") or "Could not start device sign-in.")
    _pending_flow, _flow_error = flow, None

    def wait():
        global _pending_flow, _flow_error
        from .reminders import bus
        result = app.acquire_token_by_device_flow(flow)
        _save(cache)
        _pending_flow = None
        if "access_token" not in result:
            _flow_error = _explain(result)
        bus.publish("planner", {"event": "login", "ok": "access_token" in result, "error": _flow_error})

    threading.Thread(target=wait, daemon=True).start()
    return {"method": "code", **{k: flow.get(k) for k in ("user_code", "verification_uri", "message", "expires_in")}}


def logout() -> None:
    cache = _cache()
    app = _app(cache)
    if app:
        for acc in app.get_accounts():
            app.remove_account(acc)
        _save(cache)
    if CACHE_PATH.exists():
        CACHE_PATH.unlink()


def auto_sync_due() -> bool:
    with db.connect() as con:
        if not db.get_settings(con).get("planner_auto_sync"):
            return False
    return _token() is not None


# ---------- graph helpers ----------

def _get(token: str, url: str) -> dict:
    r = requests.get(url if url.startswith("http") else GRAPH + url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
    r.raise_for_status()
    return r.json()


def _patch(token: str, url: str, etag: str, body: dict) -> dict | None:
    r = requests.patch(GRAPH + url, json=body, timeout=30, headers={
        "Authorization": f"Bearer {token}", "If-Match": etag, "Prefer": "return=representation"})
    r.raise_for_status()
    return r.json() if r.content else None


def _priority(p: int | None) -> str:
    if p is None:
        return "medium"
    if p <= 1:
        return "urgent"
    if p <= 4:
        return "high"
    if p <= 7:
        return "medium"
    return "low"


def _planner_priority(p: str) -> int:
    return {"urgent": 1, "high": 3, "medium": 5, "low": 9}.get(p, 5)


def _due_local(value: str | None) -> str | None:
    if not value:
        return None
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt.astimezone().date().isoformat()


def _notes_from_description(desc: str) -> str:
    if not desc:
        return ""
    return "".join(f"<p>{html.escape(line)}</p>" for line in desc.splitlines() if line.strip())


# ---------- sync ----------

def sync() -> dict:
    with _lock:
        token = _token()
        if not token:
            return {"ok": False, "error": "Not signed in to Microsoft."}
        try:
            result = _pull(token)
            result["ok"] = True
        except requests.HTTPError as e:
            result = {"ok": False, "error": f"Graph error {e.response.status_code}: {e.response.text[:300]}"}
        except requests.RequestException as e:
            result = {"ok": False, "error": f"Network error: {e}"}
        with db.connect() as con:
            db.set_sync(con, "planner_last_sync", db.now_iso())
            db.set_sync(con, "planner_last_result", result)
            if result.get("ok"):
                from . import engine
                engine.recompute(con)
        return result


def _pull(token: str) -> dict:
    tasks, url = [], "/me/planner/tasks"
    while url:
        page = _get(token, url)
        tasks.extend(page.get("value", []))
        url = page.get("@odata.nextLink")
    plans: dict[str, str] = {}
    buckets: dict[str, str] = {}
    created = updated = completed = 0
    with db.connect() as con:
        for pt in tasks:
            ext = pt["id"]
            row = con.execute("SELECT * FROM tasks WHERE external_id = ?", (ext,)).fetchone()
            done = pt.get("percentComplete") == 100
            if row is None and done:
                continue
            etag = pt.get("@odata.etag")
            if row is not None and row["etag"] == etag:
                continue  # unchanged since last sync
            plan_id, bucket_id = pt.get("planId"), pt.get("bucketId")
            if plan_id and plan_id not in plans:
                try:
                    plans[plan_id] = _get(token, f"/planner/plans/{plan_id}").get("title", "Planner")
                except requests.HTTPError:
                    plans[plan_id] = "Planner"
            if bucket_id and bucket_id not in buckets:
                try:
                    buckets[bucket_id] = _get(token, f"/planner/buckets/{bucket_id}").get("name", "")
                except requests.HTTPError:
                    buckets[bucket_id] = ""
            fields = {
                "title": pt.get("title") or "(untitled)",
                "due_at": _due_local(pt.get("dueDateTime")),
                "priority": _priority(pt.get("priority")),
                "plan_name": plans.get(plan_id, "Planner"),
                "bucket_name": buckets.get(bucket_id, ""),
                "etag": etag,
            }
            details = _get(token, f"/planner/tasks/{ext}/details")
            checklist = sorted(details.get("checklist", {}).items(), key=lambda kv: kv[1].get("orderHint", ""))
            if row is None:
                fields.update(source="planner", external_id=ext, status="basket",
                              notes_html=_notes_from_description(details.get("description", "")),
                              details_etag=details.get("@odata.etag"))
                fields["creative_score"] = creative_score(fields["title"], details.get("description", ""))
                task_id = db.insert_task(con, fields)
                for pos, (cid, item) in enumerate(checklist):
                    con.execute("INSERT INTO checklist_items(task_id, text, done, position, external_id) VALUES(?, ?, ?, ?, ?)",
                                (task_id, item.get("title", ""), int(bool(item.get("isChecked"))), pos, cid))
                db.log_activity(con, task_id, f"Synced from Planner ({fields['plan_name']})")
                created += 1
            else:
                task_id = row["id"]
                fields["details_etag"] = details.get("@odata.etag")
                if done and row["status"] != "done":
                    fields.update(status="done", completed_at=db.now_iso(), slot_index=None, pinned=False)
                    completed += 1
                db.update_task(con, task_id, fields)
                for cid, item in checklist:
                    existing = con.execute("SELECT id FROM checklist_items WHERE task_id = ? AND external_id = ?", (task_id, cid)).fetchone()
                    if existing:
                        con.execute("UPDATE checklist_items SET text = ?, done = ? WHERE id = ?",
                                    (item.get("title", ""), int(bool(item.get("isChecked"))), existing["id"]))
                    else:
                        con.execute("INSERT INTO checklist_items(task_id, text, done, position, external_id) VALUES(?, ?, ?, 999, ?)",
                                    (task_id, item.get("title", ""), int(bool(item.get("isChecked"))), cid))
                db.log_activity(con, task_id, "Updated from Planner")
                updated += 1
    return {"fetched": len(tasks), "created": created, "updated": updated, "completed": completed}


def push_task(task_id: int) -> dict:
    """Send completion, due date, priority and checklist state of a Planner-sourced task back to Graph."""
    token = _token()
    if not token:
        return {"ok": False, "error": "Not signed in"}
    with db.connect() as con:
        t = db.task_detail(con, task_id)
    if not t or t["source"] != "planner" or not t["external_id"]:
        return {"ok": False, "error": "Not a Planner task"}
    try:
        current = _get(token, f"/planner/tasks/{t['external_id']}")
        body = {
            "percentComplete": 100 if t["status"] == "done" else (current.get("percentComplete") if current.get("percentComplete") != 100 else 50),
            "priority": _planner_priority(t["priority"]),
            "title": t["title"],
            "dueDateTime": f"{t['due_at'][:10]}T17:00:00Z" if t.get("due_at") else None,
        }
        updated = _patch(token, f"/planner/tasks/{t['external_id']}", current["@odata.etag"], body)
        details = _get(token, f"/planner/tasks/{t['external_id']}/details")
        checklist = {c["external_id"]: {"@odata.type": "microsoft.graph.plannerChecklistItem", "isChecked": c["done"]}
                     for c in t["checklist"] if c.get("external_id")}
        if checklist:
            _patch(token, f"/planner/tasks/{t['external_id']}/details", details["@odata.etag"], {"checklist": checklist})
        with db.connect() as con:
            fresh = _get(token, f"/planner/tasks/{t['external_id']}")
            db.update_task(con, task_id, {"etag": fresh.get("@odata.etag") or (updated or {}).get("@odata.etag")}, touch=False)
        return {"ok": True}
    except requests.RequestException as e:
        log.warning("Planner push failed for task %s: %s", task_id, e)
        return {"ok": False, "error": str(e)}
