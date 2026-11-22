import httpx

from packages.config.settings import ExchangeConfig
from packages.market_data.client import BinanceAPIError, BinancePublicClient


def make(handler, fallbacks=("https://data-api.binance.vision",)):
    cfg = ExchangeConfig(max_retries=1, retry_backoff_seconds=0.0, fallback_base_urls=fallbacks)
    c = BinancePublicClient(cfg, sleep_fn=lambda s: None)
    c._client = httpx.Client(base_url=cfg.base_url, transport=httpx.MockTransport(handler))  # keep ownership semantics
    return c


def test_dns_failure_on_main_host_switches_to_the_market_data_host():
    seen = []

    def handler(req):
        seen.append(req.url.host)
        if req.url.host == "api.binance.com":
            raise httpx.ConnectError("getaddrinfo failed", request=req)
        return httpx.Response(200, json=[])

    c = make(handler)
    assert c._request_json("/api/v3/klines", {"symbol": "BTCUSDT"}) == []
    assert seen == ["api.binance.com", "api.binance.com", "data-api.binance.vision"]
    assert c.host_in_use == "https://data-api.binance.vision"
    c._request_json("/api/v3/klines")                      # sticky: the working host is kept
    assert seen[-1] == "data-api.binance.vision"


def test_http_errors_do_not_switch_hosts_and_all_hosts_down_still_fails_closed():
    def bad_request(req):
        return httpx.Response(400, text="bad")
    c = make(bad_request)
    try:
        c._request_json("/api/v3/klines")
        assert False
    except BinanceAPIError:
        assert c.host_in_use == "https://api.binance.com"

    def down(req):
        raise httpx.ConnectError("no network", request=req)
    c2 = make(down)
    try:
        c2._request_json("/api/v3/klines")
        assert False
    except BinanceAPIError as e:
        assert "2 host(s)" in str(e)
