"""Task notifications, routed per task: desktop (a native Windows notification), email, both, or off.

Desktop notifications come from the server, so they arrive even when no Memory window is open (e.g. when you only
have the desktop wallpaper). Clicking one opens the task in your browser. Email goes through Outlook (Microsoft Graph)
to the address in Settings, or to the signed-in Microsoft account.
"""
from __future__ import annotations

import base64
import html
import logging
import subprocess
import sys
import threading

from . import db

log = logging.getLogger("memory.notify")
CHANNELS = ("desktop", "email", "both", "off")
APP_ID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"  # a registered app id that can raise toasts

_TOAST_PS = r"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml(@'
__XML__
'@)
$toast = New-Object Windows.UI.Notifications.ToastNotification $xml
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('__APPID__').Show($toast)
"""


def desktop(heading: str, title: str, detail: str = "", url: str | None = None) -> bool:
    """Show a Windows notification. Returns False where that isn't possible (other OSes, PowerShell blocked)."""
    if sys.platform != "win32":
        return False
    e = lambda s: html.escape(s or "", quote=True)  # noqa: E731
    launch = f' activationType="protocol" launch="{e(url)}"' if url else ""
    actions = (f'<actions><action content="Open" activationType="protocol" arguments="{e(url)}"/>'
               f'<action content="Dismiss" activationType="system" arguments="dismiss"/></actions>') if url else ""
    xml = (f'<toast{launch}><visual><binding template="ToastGeneric"><text>{e(heading)}</text><text>{e(title)}</text>'
           f'{"<text>" + e(detail) + "</text>" if detail else ""}</binding></visual>{actions}</toast>')
    script = _TOAST_PS.replace("__XML__", xml).replace("__APPID__", APP_ID)
    try:
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-EncodedCommand",
                        base64.b64encode(script.encode("utf-16-le")).decode()],
                       timeout=20, capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return True
    except (OSError, subprocess.SubprocessError) as ex:
        log.warning("desktop notification failed: %s", ex)
        return False


def email(subject: str, body_html: str) -> str | None:
    """Email the user through Outlook. Returns an error string, or None on success."""
    from . import mail
    try:
        with db.connect() as con:
            to = (db.get_settings(con).get("notify_email") or "").strip()
        mail.send(subject, body_html, to or None)
        return None
    except Exception as ex:  # surfaced in the activity log rather than crashing the reminder loop
        return str(ex)


def deliver(task: dict, heading: str, text: str, base_url: str = "http://localhost:8765/") -> None:
    """Send one task notification on the task's chosen channel(s). Runs in its own thread: email can be slow."""
    channel = task.get("notify") or "desktop"
    if channel == "off":
        return
    url = f"{base_url}#task={task['id']}"

    def run():
        detail = " · ".join(x for x in (f"due {task['due_at'][:10]}" if task.get("due_at") else "", task.get("priority", "").capitalize()) if x)
        if channel in ("desktop", "both"):
            desktop(f"Memory · {heading}", task["title"], detail, url)
        if channel in ("email", "both"):
            body = (f"<p><b>{html.escape(heading)}:</b> {html.escape(task['title'])}</p>"
                    f"<p>{html.escape(detail)}</p><p><a href=\"{html.escape(url)}\">Open in Memory</a></p>")
            err = email(f"[Memory] {text}", body)
            if err:
                with db.connect() as con:
                    db.log_activity(con, task["id"], f"Email notification failed: {err}")

    threading.Thread(target=run, daemon=True).start()
