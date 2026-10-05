from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

MAX_LEVEL = 130
MAX_LEVEL_PER_PRESTIGE = 50
PRESTIGE_LEVEL_STEP = 20
PRESTIGE_XP_MULTIPLIER = 0.25

CURVE_BASE_XP = 100
CURVE_EXPONENT = 1.6


def build_curve(max_level: int = MAX_LEVEL) -> dict[str, int]:
    if max_level < 1:
        raise ValueError("max_level must be greater than 0")

    return {
        str(level): round(CURVE_BASE_XP * (level**CURVE_EXPONENT))
        for level in range(max_level + 1)
    }


def load_curve(path: Path, max_level: int = MAX_LEVEL) -> dict[str, int]:
    with path.open("r", encoding="utf-8") as curve_file:
        raw_curve = json.load(curve_file)

    if not isinstance(raw_curve, dict):
        raise ValueError("XP curve must be a JSON object")

    curve = {"0": 0}
    previous_xp = 0

    for level in range(1, max_level + 1):
        raw_xp = raw_curve.get(str(level))

        if not isinstance(raw_xp, int) or raw_xp <= previous_xp:
            raise ValueError(f"Invalid XP threshold for level {level}")

        curve[str(level)] = raw_xp
        previous_xp = raw_xp

    return curve


def max_level_for_prestige(prestige: int) -> int:
    if prestige < 0:
        raise ValueError("prestige cannot be negative")

    return min(
        MAX_LEVEL,
        MAX_LEVEL_PER_PRESTIGE + PRESTIGE_LEVEL_STEP * prestige,
    )


def required_xp(
    curve: Mapping[str, int],
    level: int,
    prestige: int = 0,
) -> int:
    if prestige < 0:
        raise ValueError("prestige cannot be negative")

    if level <= 0:
        return 0

    base_xp = curve.get(str(level))
    if base_xp is None:
        return 0

    multiplier = 1 + PRESTIGE_XP_MULTIPLIER * prestige
    return round(base_xp * multiplier)


def scale_curve(
    curve: Mapping[str, int],
    multiplier: float,
) -> dict[str, int]:
    if multiplier <= 0:
        raise ValueError("multiplier must be greater than zero")

    return {
        level: round(xp * multiplier)
        for level, xp in curve.items()
    }
