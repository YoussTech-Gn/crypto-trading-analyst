from packages.notify.heartbeat import heartbeat_target, send_heartbeat

URL = "https://hc-ping.com/abc-123"


class _R:
    def __init__(self, code):
        self.status_code = code


def test_target_success_and_fail_and_refusals():
    assert heartbeat_target(URL, True) == URL
    assert heartbeat_target(URL + "/", False) == URL + "/fail"
    assert heartbeat_target(None, True) is None
    assert heartbeat_target("http://hc-ping.com/abc", True) is None


def test_send_never_reveals_the_url_and_never_raises():
    calls = []
    sent, info = send_heartbeat(URL, False, get=lambda u, timeout: calls.append(u) or _R(200))
    assert sent and calls == [URL + "/fail"] and "abc-123" not in info

    def boom(u, timeout):
        raise OSError(f"cannot reach {u}")
    sent, info = send_heartbeat(URL, True, get=boom)
    assert not sent and "abc-123" not in info and "hc-ping" not in info


def test_off_when_not_configured():
    assert send_heartbeat(None, True) == (False, "off (NOTIFY_HEARTBEAT_URL not set)")
    assert send_heartbeat("", True)[0] is False
