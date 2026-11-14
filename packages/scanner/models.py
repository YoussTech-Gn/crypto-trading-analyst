"""Scanner data models. The scanner discovers assets to investigate; it never emits signals."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

SCANNER_VERSION = "scanner-1.0"

STATUS_SHORTLISTED = "SHORTLISTED"
STATUS_RANKED = "RANKED_NOT_SHORTLISTED"
STATUS_EXCLUDED = "EXCLUDED"


@dataclass(frozen=True)
class ScanEntry:
    symbol: str
    status: str
    rank: int | None
    quote_volume: float | None
    price_change_percent: float | None
    spread_bps: float | None
    exclusion_reasons: tuple[str, ...] = ()
    category: str = "CRYPTO"


@dataclass(frozen=True)
class ScanSnapshot:
    """One saved scan: stored inputs + parameters are enough to recompute the entries."""

    snapshot_id: str
    created_at_utc: datetime
    scanner_version: str
    params: dict[str, Any]
    inputs: dict[str, Any]
    entries: tuple[ScanEntry, ...]
    non_target_quote_skipped: int = 0

    @property
    def shortlisted(self) -> tuple[ScanEntry, ...]:
        return tuple(e for e in self.entries if e.status == STATUS_SHORTLISTED)
