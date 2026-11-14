"""Strategy lab: recipes (parts), scorecard (gap to goal), trial ledger (multiple-testing penalty)."""

from packages.strategies.base import Recipe
from packages.strategies.registry import ALL_RECIPES, build_recipes
from packages.strategies.scorecard import Goal, score_recipe, z_for_trials

__all__ = ["Recipe", "ALL_RECIPES", "build_recipes", "Goal", "score_recipe", "z_for_trials"]
