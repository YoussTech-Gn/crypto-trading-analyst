"""Outside watcher ping (ADR-047): a dead man's switch.

The laptop cannot report that it is asleep or offline, so after every cycle it pings an outside check service
(for example healthchecks.io). The service, which never sleeps, alerts the owner when the pings stop.
A good scan pings the URL; a failed scan pings URL + "/fail" so a reachable-but-failing cycle alerts at once.

The URL is a secret (anyone with it can ping): it lives only in the git-ignored .env as NOTIFY_HEARTBEAT_URL
and is never printed. Only https URLs are used.
"""
from __future__ import annotations

from typing import Callable


def heartbeat_target(url: str | None, scan_ok: bool) -> str | None:
    """The URL to ping, or None when the heartbeat is off or the URL is not https."""
    if not url or not url.startswith("https://"):
        return None
    return url.rstrip("/") + ("" if scan_ok else "/fail")


def send_heartbeat(url: str | None, scan_ok: bool, get: Callable | None = None) -> tuple[bool, str]:
    """Ping the outside watcher. Returns (sent, info); info never contains the URL."""
    if not url:
        return False, "off (NOTIFY_HEARTBEAT_URL not set)"
    target = heartbeat_target(url, scan_ok)
    if target is None:
        return False, "refused: NOTIFY_HEARTBEAT_URL must start with https://"
    if get is None:
        import httpx
        get = httpx.get
    try:
        r = get(target, timeout=10)
        return 200 <= r.status_code < 300, f"HTTP {r.status_code} ({'success' if scan_ok else 'fail'} ping)"
    except Exception as exc:  # noqa: BLE001 - never let the ping break the cycle; never echo the URL
        return False, f"error {type(exc).__name__}"
