"""The list of all recipes and how to build them."""

from __future__ import annotations

from packages.config.settings import AppConfig
from packages.strategies.families import FAMILY_RECIPES
from packages.strategies.recipes import BASE_RECIPES

ALL_RECIPES = BASE_RECIPES + FAMILY_RECIPES


def build_recipes(cfg: AppConfig, names: list[str] | None = None) -> dict:
    """Recipes share the same signals config. The baseline uses target_mode first_meeting_rr like the others."""
    sig = cfg.signals.model_copy(update={"target_mode": "first_meeting_rr"})
    out = {r.name: r(sig, cfg.strategy.minimum_reward_to_risk) for r in ALL_RECIPES}
    if names:
        unknown = [n for n in names if n not in out]
        if unknown:
            raise ValueError(f"unknown recipes {unknown}; available {sorted(out)}")
        out = {n: out[n] for n in names}
    return out
