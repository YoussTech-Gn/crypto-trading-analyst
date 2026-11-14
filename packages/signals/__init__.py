"""Paper-only LONG signal decisions (SIGNAL / NO_TRADE) built on the analysis engine."""

from packages.signals.generator import SIGNAL_VERSION, SignalDecision, SignalGenerator
from packages.signals.repository import SignalRepository

__all__ = ["SIGNAL_VERSION", "SignalDecision", "SignalGenerator", "SignalRepository"]
