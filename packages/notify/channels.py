"""Send a notification (ADR-045). Every channel is optional and failure-tolerant: a failed notification never stops
the journal. No secret is ever written to a file by this module; tokens are read from the environment or .env."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import httpx

_TOAST_PS = r"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
$t = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$x = $t.GetElementsByTagName('text')
$x.Item(0).AppendChild($t.CreateTextNode($env:CTA_TITLE)) > $null
$x.Item(1).AppendChild($t.CreateTextNode($env:CTA_BODY)) > $null
$n = [Windows.UI.Notifications.ToastNotification]::new($t)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe').Show($n)
"""


def load_env(root: Path) -> dict:
    """Environment variables, plus KEY=VALUE lines from <root>/.env (which is git-ignored). The environment wins."""
    env = {}
    p = root / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.split("  #")[0].strip().strip('"').strip("'")
    env.update({k: v for k, v in os.environ.items() if k.startswith(("NTFY_", "TELEGRAM_", "NOTIFY_"))})
    return env


def windows_toast(title: str, body: str) -> tuple[bool, str]:
    if os.name != "nt":
        return False, "not Windows"
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", _TOAST_PS], timeout=30,
                           env={**os.environ, "CTA_TITLE": title, "CTA_BODY": body}, capture_output=True, text=True)
        return r.returncode == 0, (r.stderr or "").strip()[:200]
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)[:200]


def ntfy(env: dict, title: str, body: str, priority: str = "default") -> tuple[bool, str]:
    topic = env.get("NTFY_TOPIC")
    if not topic:
        return False, "NTFY_TOPIC not set"
    server = env.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
    try:
        r = httpx.post(f"{server}/{topic}", content=body.encode("utf-8"), timeout=15,
                       headers={"Title": title.encode("ascii", "replace").decode(), "Priority": priority, "Tags": "chart_with_upwards_trend"})
        return r.status_code < 300, f"HTTP {r.status_code}"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)[:200]


def telegram(env: dict, title: str, body: str) -> tuple[bool, str]:
    token, chat = env.get("TELEGRAM_BOT_TOKEN"), env.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return False, "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set"
    try:
        r = httpx.post(f"https://api.telegram.org/bot{token}/sendMessage", timeout=15,
                       json={"chat_id": chat, "text": f"{title}\n{body}", "disable_web_page_preview": True})
        return r.status_code < 300, f"HTTP {r.status_code}"
    except Exception as exc:  # noqa: BLE001
        return False, "request failed"  # never echo the URL: it contains the token


def send(env: dict, title: str, body: str, urgent: bool = False) -> list[tuple[str, bool, str]]:
    out = [("windows", *windows_toast(title, body)), ("ntfy", *ntfy(env, title, body, "high" if urgent else "default")),
           ("telegram", *telegram(env, title, body))]
    return out
