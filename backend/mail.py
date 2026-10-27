"""Outlook mail over Microsoft Graph, using the same Microsoft sign-in as Planner (scopes Mail.Read + Mail.Send).

Read the inbox for the right-hand Inbox panel, fetch one message for AI task creation, and send notification email.
"""
from __future__ import annotations

import requests

from . import planner_sync

GRAPH = "https://graph.microsoft.com/v1.0"


class MailNotConnected(RuntimeError):
    pass


def _token() -> str:
    token = planner_sync._token()
    if not token:
        raise MailNotConnected("Sign in to Microsoft in Settings (Microsoft Planner & Outlook) to use your inbox.")
    return token


def _request(method: str, path: str, **kw) -> requests.Response:
    r = requests.request(method, GRAPH + path, headers={"Authorization": f"Bearer {_token()}", **kw.pop("headers", {})}, timeout=30, **kw)
    if r.status_code == 403:
        raise MailNotConnected("Your Microsoft sign-in doesn't include mail access yet. Add the Mail.Read and Mail.Send "
                               "permissions to the Azure app (see README), then sign out and in again in Settings.")
    r.raise_for_status()
    return r


def account() -> str | None:
    st = planner_sync.status()
    return st.get("account") if st.get("signed_in") else None


def inbox(top: int = 25) -> list[dict]:
    data = _request("GET", "/me/mailFolders/inbox/messages", params={
        "$top": str(top), "$orderby": "receivedDateTime desc",
        "$select": "id,subject,from,receivedDateTime,bodyPreview,webLink,isRead,importance,hasAttachments",
    }).json()
    return [{
        "id": m["id"], "subject": m.get("subject") or "(no subject)",
        "from": ((m.get("from") or {}).get("emailAddress") or {}).get("name") or ((m.get("from") or {}).get("emailAddress") or {}).get("address") or "",
        "from_address": ((m.get("from") or {}).get("emailAddress") or {}).get("address") or "",
        "received": m.get("receivedDateTime"), "preview": m.get("bodyPreview") or "", "link": m.get("webLink"),
        "unread": not m.get("isRead", True), "important": m.get("importance") == "high", "attachments": m.get("hasAttachments", False),
    } for m in data.get("value", [])]


def message(message_id: str) -> dict:
    m = _request("GET", f"/me/messages/{message_id}", params={"$select": "id,subject,from,toRecipients,receivedDateTime,body,webLink,importance"},
                 headers={"Prefer": 'outlook.body-content-type="text"'}).json()
    sender = (m.get("from") or {}).get("emailAddress") or {}
    return {"id": m["id"], "subject": m.get("subject") or "(no subject)", "from": sender.get("name") or sender.get("address") or "",
            "from_address": sender.get("address") or "", "received": m.get("receivedDateTime"),
            "body": ((m.get("body") or {}).get("content") or "")[:12000], "link": m.get("webLink"),
            "important": m.get("importance") == "high"}


def send(subject: str, body_html: str, to: str | None = None) -> None:
    to = to or account()
    if not to:
        raise MailNotConnected("No email address: sign in to Microsoft or set one in Settings → Notifications.")
    _request("POST", "/me/sendMail", json={"message": {
        "subject": subject, "body": {"contentType": "HTML", "content": body_html},
        "toRecipients": [{"emailAddress": {"address": to}}]}, "saveToSentItems": False})
