from fastapi.testclient import TestClient

from backend.app import app


def make(client, title, **kw):
    r = client.post("/api/tasks", json={"title": title, **kw})
    assert r.status_code == 200, r.text
    return r.json()


def test_task_lifecycle_and_slots():
    with TestClient(app) as client:
        client.put("/api/settings", json={"ram_slots": 3, "auto_fill": False})
        ids = [make(client, f"Task {i}", priority="high" if i < 2 else "low")["id"] for i in range(5)]
        state = client.get("/api/state").json()
        assert len(state["slots"]) == 3
        assert all(t["status"] == "basket" for t in state["tasks"])
        assert all(t["assigned_week"] for t in state["tasks"])

        # sort basket: 3 go to the brain, 2 overflow to backlog
        client.post("/api/rethink", json={"include_basket": True})
        tasks = {t["id"]: t for t in client.get("/api/state").json()["tasks"]}
        assert sum(t["status"] == "active" for t in tasks.values()) == 3
        assert sum(t["status"] == "backlog" for t in tasks.values()) == 2
        assert tasks[ids[0]]["status"] == "active"

        # drop a backlog task onto an occupied synapse: occupant is bumped to backlog
        backlog_id = next(i for i, t in tasks.items() if t["status"] == "backlog")
        occupant = next(t for t in tasks.values() if t["slot_index"] == 0)
        r = client.post(f"/api/tasks/{backlog_id}/place", json={"slot_index": 0})
        assert r.json()["slot_index"] == 0 and r.json()["pinned"]
        assert client.get(f"/api/tasks/{occupant['id']}").json()["status"] == "backlog"

        # complete with auto-fill pulls the top of the queue into the freed synapse
        client.put("/api/settings", json={"auto_fill": True})
        client.patch(f"/api/tasks/{backlog_id}", json={"status": "done"})
        tasks = client.get("/api/state").json()["tasks"]
        assert sum(t["status"] == "active" for t in tasks) == 3


def test_detail_checklist_attachment_links():
    with TestClient(app) as client:
        t = make(client, "Budget report Q4", checklist=["Gather numbers"])
        other = make(client, "Q4 budget review")
        d = client.post(f"/api/tasks/{t['id']}/checklist", json={"text": "Draft"}).json()
        assert [c["text"] for c in d["checklist"]] == ["Gather numbers", "Draft"]
        d = client.patch(f"/api/checklist/{d['checklist'][0]['id']}", json={"done": True}).json()
        assert d["checklist_done"] == 1

        r = client.post(f"/api/tasks/{t['id']}/attachments", files={"files": ("shot.png", b"\x89PNG fake", "image/png")},
                        data={"is_screenshot": "true"})
        att = r.json()["attachments"][0]
        assert att["is_screenshot"]
        assert client.get(f"/api/attachments/{att['id']}").content == b"\x89PNG fake"

        # shared words create an auto link
        links = client.get(f"/api/tasks/{t['id']}").json()["links"]
        assert any(l["id"] == other["id"] for l in links)

        d = client.patch(f"/api/tasks/{t['id']}", json={"notes_html": "<p>hello</p>", "due_at": "2026-11-02"}).json()
        assert d["notes_html"] == "<p>hello</p>" and d["due_at"] == "2026-11-02"


def test_dashboard_and_repeat():
    with TestClient(app) as client:
        t = make(client, "Weekly sync notes", due_at="2026-10-27")
        client.patch(f"/api/tasks/{t['id']}", json={"repeat": "weekly"})
        client.patch(f"/api/tasks/{t['id']}", json={"status": "done"})
        tasks = client.get("/api/state").json()["tasks"]
        nxt = [x for x in tasks if x["title"] == "Weekly sync notes" and x["status"] != "done"]
        assert nxt and nxt[0]["due_at"] == "2026-11-03"
        dash = client.get("/api/dashboard").json()
        assert {"kpis", "weeks", "calendar", "regions", "trend", "insights"} <= dash.keys()
        assert len(dash["weeks"]) == 8 and len(dash["calendar"]) == 42


def test_claude_without_key_is_friendly():
    with TestClient(app) as client:
        r = client.post("/api/claude/chat", json={"messages": [{"role": "user", "content": "hi"}]})
        assert r.status_code == 400 and "API key" in r.json()["detail"]
        assert client.get("/api/settings").json()["has_anthropic_api_key"] is False


def test_parking_a_synapse_does_not_bounce_back():
    with TestClient(app) as client:
        client.put("/api/settings", json={"ram_slots": 2, "auto_fill": True})
        for t in client.get("/api/state").json()["tasks"]:
            client.delete(f"/api/tasks/{t['id']}")
        a = make(client, "Alpha", priority="urgent")
        make(client, "Beta", priority="low")
        make(client, "Gamma", priority="low")
        client.post("/api/rethink", json={"include_basket": True})
        client.post(f"/api/tasks/{a['id']}/unplace", json={"to": "backlog"})
        tasks = {t["title"]: t for t in client.get("/api/state").json()["tasks"]}
        assert tasks["Alpha"]["status"] == "backlog"
        assert sum(t["status"] == "active" for t in tasks.values()) == 1


def test_open_in_browser(monkeypatch):
    opened = []
    monkeypatch.setattr("backend.app.webbrowser.open", opened.append)
    with TestClient(app) as client:
        t = make(client, "Open me")
        assert client.post("/api/open", json={"task_id": t["id"]}).json()["url"].endswith(f"/#task={t['id']}")
        assert client.post("/api/open", json={}).status_code == 200
        assert client.post("/api/open", json={"task_id": 999999}).status_code == 404
    assert len(opened) == 2 and opened[0].startswith("http://localhost:")


def test_theme_setting():
    with TestClient(app) as client:
        assert client.get("/api/state").json()["settings"]["theme"] == "blue"
        assert client.put("/api/settings", json={"theme": "green"}).status_code == 200
        assert client.get("/api/state").json()["settings"]["theme"] == "green"
        assert client.put("/api/settings", json={"theme": "plaid"}).status_code == 422
        client.put("/api/settings", json={"theme": "blue"})


def test_open_popup_window(monkeypatch):
    windows = []
    monkeypatch.setattr("backend.app.desktop.open_window", lambda url, kind="popup": windows.append((url, kind)) or "window")
    with TestClient(app) as client:
        t = make(client, "Pop me")
        r = client.post("/api/open", json={"task_id": t["id"], "window": "popup"}).json()
        assert r["opened"] == "window" and "?popup=" in r["url"] and r["url"].endswith(f"#task={t['id']}")
        assert client.post("/api/open", json={"new": True, "window": "popup"}).json()["url"].endswith("#new")
        assert "/?win=" in client.post("/api/open", json={"window": "app"}).json()["url"]
        assert client.post("/api/open", json={"window": "fullscreen"}).status_code == 422
    assert [k for _, k in windows] == ["popup", "popup", "app"]


def test_window_tracking(monkeypatch):
    monkeypatch.setattr("backend.app.desktop.open_window", lambda url, kind="popup": "window")
    with TestClient(app) as client:
        before = client.get("/api/state").json()["windows_open"]
        url = client.post("/api/open", json={"window": "popup"}).json()["url"]
        pid = url.split("popup=")[1].split("#")[0]
        assert client.get("/api/state").json()["windows_open"] == before + 1
        assert client.post(f"/api/windows/{pid}/alive").status_code == 200
        assert client.post(f"/api/windows/{pid}/closed").status_code == 200
        assert client.get("/api/state").json()["windows_open"] == before
        assert client.post("/api/windows/not-a-pid!/closed").status_code in (404, 422)


def test_hemisphere_placement_rules():
    with TestClient(app) as client:
        client.put("/api/settings", json={"ram_slots": 3, "auto_fill": False})
        for t in client.get("/api/state").json()["tasks"]:
            if t["status"] == "active":
                client.post(f"/api/tasks/{t['id']}/unplace", json={"to": "backlog"})
        t = make(client, "Paint a mural", creative_score=90)
        # dropping a creative task on the left (logical) synapse re-classifies it
        client.post(f"/api/tasks/{t['id']}/place", json={"slot_index": 1})
        moved = client.get(f"/api/tasks/{t['id']}").json()
        assert moved["slot_index"] == 1 and moved["region"] == "logical" and moved["creative_locked"]
        # making it creative again moves it to a synapse on the creative side (or the centre)
        client.patch(f"/api/tasks/{t['id']}", json={"creative_score": 90})
        back = client.get(f"/api/tasks/{t['id']}").json()
        assert back["region"] == "creative" and back["status"] == "active" and back["slot_index"] in (0, 2)
        client.put("/api/settings", json={"ram_slots": 7, "auto_fill": True})


def test_dependencies_api():
    with TestClient(app) as client:
        a, b, c = (make(client, f"Dep {x}") for x in "abc")
        assert client.post(f"/api/tasks/{b['id']}/dependencies", json={"depends_on_id": a["id"]}).status_code == 200
        d = client.post(f"/api/tasks/{c['id']}/dependencies", json={"depends_on_id": b["id"]}).json()
        assert [n["id"] for n in d["needs"]] == [b["id"]]
        assert client.post(f"/api/tasks/{a['id']}/dependencies", json={"depends_on_id": c["id"]}).status_code == 409
        assert client.post(f"/api/tasks/{a['id']}/dependencies", json={"depends_on_id": a["id"]}).status_code == 400
        state = {t["id"]: t for t in client.get("/api/state").json()["tasks"]}
        assert [state[x["id"]]["seq"]["step"] for x in (a, b, c)] == [1, 2, 3]
        assert state[a["id"]]["score"] >= state[c["id"]]["score"]   # urgency flows back to the first step
        assert [u["id"] for u in client.get(f"/api/tasks/{a['id']}").json()["unlocks"]] == [b["id"]]
        client.delete(f"/api/tasks/{c['id']}/dependencies/{b['id']}")
        assert client.get("/api/state").json()["tasks"] and client.get(f"/api/tasks/{c['id']}").json()["needs"] == []
        for x in (a, b, c):
            client.delete(f"/api/tasks/{x['id']}")


def test_system_info_and_quick_links(monkeypatch):
    opened = []
    monkeypatch.setattr("backend.app.webbrowser.open", opened.append)
    with TestClient(app) as client:
        info = client.get("/api/system").json()
        assert info["specs"]["host"] and "usage" in info
        links = client.get("/api/settings").json()["quick_links"]
        assert links and all(l["label"] and l["target"] for l in links)
        assert client.post("/api/quicklinks/0/open").json()["ok"] and opened == [links[0]["target"]]
        assert client.post("/api/quicklinks/99/open").status_code == 404
        bad = client.put("/api/settings", json={"quick_links": [{"label": "x", "target": "relative/path"}]})
        assert bad.status_code == 422
        ok = client.put("/api/settings", json={"quick_links": [{"label": "Site", "target": "https://example.com"}, {"label": "Temp", "target": "C:\\Windows"}]})
        assert ok.status_code == 200 and len(ok.json()["quick_links"]) == 2
        client.put("/api/settings", json={"quick_links": links})


def test_templates_builtin_use_and_save():
    with TestClient(app) as client:
        names = [t["name"] for t in client.get("/api/templates").json()]
        assert {"Meeting prep", "Bug fix", "Weekly report"} <= set(names)
        bug = next(t for t in client.get("/api/templates").json() if t["name"] == "Bug fix")
        t = client.post(f"/api/templates/{bug['id']}/use", json={"title": "Fix: login timeout"}).json()
        assert t["title"] == "Fix: login timeout" and t["priority"] == "high" and t["checklist_total"] == 5 and t["region"] == "logical"
        tpl = client.post(f"/api/tasks/{t['id']}/template", json={"name": "My bug flow"}).json()
        assert tpl["checklist"][0] == "Reproduce the issue" and tpl["priority"] == "high"
        assert client.delete(f"/api/templates/{tpl['id']}").json()["ok"]
        client.delete(f"/api/tasks/{t['id']}")


def test_notify_channel_routes_reminders(monkeypatch):
    from backend import notify, reminders
    sent = []
    monkeypatch.setattr(notify, "desktop", lambda *a, **k: sent.append(("desktop", a[1])) or True)
    monkeypatch.setattr(notify, "email", lambda subject, body: sent.append(("email", subject)) or None)
    monkeypatch.setattr(notify.threading, "Thread", lambda target, daemon: type("T", (), {"start": staticmethod(target)})())
    with TestClient(app) as client:
        past = "2020-01-01T09:00"
        ids = {ch: make(client, f"Remind {ch}", reminder_at=past, notify=ch)["id"] for ch in ("desktop", "email", "both", "off")}
        fired = reminders.check_reminders()
        assert {f["task_id"] for f in fired} >= set(ids.values())
        assert ("desktop", "Remind desktop") in sent and ("desktop", "Remind both") in sent
        assert any(k == "email" and "Remind email" in s for k, s in sent) and any(k == "email" and "Remind both" in s for k, s in sent)
        assert not any("Remind off" in s for _, s in sent)
        for i in ids.values():
            client.delete(f"/api/tasks/{i}")


def test_mail_inbox_and_ai_task(monkeypatch):
    from backend import claude_service, mail
    msg = {"id": "AAMkTest1", "subject": "Can you send the Q3 deck by Friday?", "from": "Dana", "from_address": "dana@example.com",
           "received": "2026-10-26T09:00:00Z", "body": "Hi, please send the Q3 deck by Friday 31 Oct. Thanks!", "link": "https://outlook/x", "important": False}
    monkeypatch.setattr(mail, "inbox", lambda top=25: [{**msg, "preview": msg["body"], "unread": True, "attachments": False}])
    monkeypatch.setattr(mail, "message", lambda mid: msg)
    monkeypatch.setattr(mail, "account", lambda: "me@example.com")
    monkeypatch.setattr(claude_service, "email_to_task", lambda m: {
        "actionable": True, "title": "Send Q3 deck to Dana", "summary": "Dana needs the Q3 deck.", "due_date": "2026-10-31",
        "priority": "high", "effort": "S", "steps": ["Update numbers", "Send deck"], "creative_score": 40, "tags": ["deck"]})
    with TestClient(app) as client:
        inbox = client.get("/api/mail/inbox").json()
        assert inbox["messages"][0]["task_id"] is None
        t = client.post("/api/mail/AAMkTest1/task").json()
        assert t["ai"] and t["title"] == "Send Q3 deck to Dana" and t["due_at"].startswith("2026-10-31") and t["checklist_total"] == 2
        assert "Open in Outlook" in t["notes_html"] and t["status"] == "basket"
        assert client.get("/api/mail/inbox").json()["messages"][0]["task_id"] == t["id"]
        again = client.post("/api/mail/AAMkTest1/task").json()
        assert again["existing"] and again["id"] == t["id"]
        client.delete(f"/api/tasks/{t['id']}")


def test_mail_not_connected_is_friendly():
    with TestClient(app) as client:
        r = client.get("/api/mail/inbox")
        assert r.status_code == 400 and "Sign in to Microsoft" in r.json()["detail"]


def test_slot_positions_setting():
    with TestClient(app) as client:
        ok = client.put("/api/settings", json={"slot_positions": {"2": [0.4, 0.5, 0.2, 0.6, 0.7, 0.3]}})
        assert ok.status_code == 200 and ok.json()["slot_positions"]["2"][0] == 0.4
        assert client.put("/api/settings", json={"slot_positions": {"x": [0, 0, 0, 0, 0, 1]}}).status_code == 422
        assert client.put("/api/settings", json={"slot_positions": {"1": [0, 0, 0]}}).status_code == 422
        client.put("/api/settings", json={"slot_positions": {}})


def test_version_and_update_check(monkeypatch):
    from backend import app as app_module
    from backend.version import __version__

    class Resp:
        ok = True
        def json(self):
            return {"tag_name": "v99.0.0", "html_url": "https://github.com/x/y/releases/v99.0.0",
                    "assets": [{"name": "Memory-Setup-99.0.0.exe", "browser_download_url": "https://dl/Memory-Setup-99.0.0.exe"}]}
    monkeypatch.setattr("requests.get", lambda *a, **k: Resp())
    app_module._latest_release.update(at=0.0, data=None)
    with TestClient(app) as client:
        assert client.get("/api/state").json()["version"] == __version__
        v = client.get("/api/version").json()
        assert v["update_available"] and v["latest"]["download"].endswith(".exe") and v["version"] == __version__
    app_module._latest_release.update(at=0.0, data=None)


def test_paths_default_to_appdata_when_packaged(monkeypatch, tmp_path):
    import importlib
    import sys
    from backend import paths
    monkeypatch.delenv("MEMORY_DATA_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    try:
        frozen = importlib.reload(paths)
        assert frozen.DATA_DIR == tmp_path / "Memory" and frozen.ENV_FILE == tmp_path / "Memory" / ".env"
    finally:
        monkeypatch.undo()
        importlib.reload(paths)


def test_old_manual_links_become_a_sequence(tmp_path, monkeypatch):
    import sqlite3
    from backend import db
    con = sqlite3.connect(db.DB_PATH)
    con.row_factory = sqlite3.Row
    ids = [con.execute("INSERT INTO tasks(title, created_at, updated_at) VALUES(?, '2026-01-01', '2026-01-01')", (f"L{i}",)).lastrowid for i in range(3)]
    con.execute("INSERT INTO links(a_id, b_id, kind, strength) VALUES(?, ?, 'manual', 1)", (ids[1], ids[2]))
    con.execute("INSERT INTO links(a_id, b_id, kind, strength) VALUES(?, ?, 'manual', 1)", (ids[0], ids[1]))
    con.execute("DELETE FROM sync_state WHERE key = 'manual_links_to_dependencies'")
    con.commit()
    con.close()
    db.init()
    with TestClient(app) as client:
        seq = {t["id"]: t["seq"] for t in client.get("/api/state").json()["tasks"] if t["id"] in ids}
        assert [seq[i]["step"] for i in ids] == [1, 2, 3]
        assert not [l for l in client.get("/api/state").json()["links"] if l["kind"] == "manual"]
        for i in ids:
            client.delete(f"/api/tasks/{i}")


def test_desktop_wallpaper_setting_starts_and_stops_host(monkeypatch):
    from backend import wallpaper
    calls = []
    monkeypatch.setattr(wallpaper, "start", lambda port, screens="all": calls.append(("start", screens)))
    monkeypatch.setattr(wallpaper, "stop", lambda: calls.append(("stop",)))
    with TestClient(app) as client:
        assert client.get("/api/wallpaper").json()["enabled"] is False
        client.put("/api/settings", json={"desktop_wallpaper": True, "wallpaper_screens": "primary"})
        assert client.get("/api/wallpaper").json()["enabled"] is True
        client.put("/api/settings", json={"wallpaper_screens": "all"})
        client.put("/api/settings", json={"desktop_wallpaper": False})
        assert client.post("/api/wallpaper/restart").status_code == 400
        client.put("/api/settings", json={"ram_slots": 7})   # unrelated settings don't touch the wallpaper
    assert [c[0] for c in calls if c[0] == "start"] == ["start", "start"] and calls[0] == ("start", "primary") and calls[1] == ("start", "all")
    assert ("stop",) in calls


def test_browser_sign_in_and_error_help(monkeypatch):
    from backend import planner_sync

    class FakeApp:
        def acquire_token_interactive(self, scopes, **kw):
            assert "Mail.Read" in scopes and kw["prompt"] == "select_account"
            return {"error": "invalid_request", "error_description": "AADSTS50011: The redirect URI 'http://localhost:51234' does not match."}
        def get_accounts(self):
            return []
    ran = []
    monkeypatch.setattr(planner_sync, "_app", lambda cache: FakeApp())
    monkeypatch.setattr(planner_sync.threading, "Thread", lambda target, daemon: type("T", (), {"start": staticmethod(lambda: ran.append(target()))})())
    with TestClient(app) as client:
        r = client.post("/api/planner/login", json={"method": "browser"}).json()
        assert r["method"] == "browser" and ran
        st = client.get("/api/planner/status").json()
        assert "http://localhost" in st["error"] and "AADSTS50011" in st["error"] and st["pending"] is None
    planner_sync._flow_error = None
