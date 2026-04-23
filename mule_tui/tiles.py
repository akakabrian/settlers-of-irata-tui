"""Tile glyph + style tables for the Irata map."""

from __future__ import annotations

from rich.style import Style

from .engine import TileKind


# 2-glyph patterns keyed by (x + y) & 1 — reads painted, not stamped.
_PATTERN: dict[TileKind, tuple[str, str]] = {
    TileKind.PLAIN:    (".", ","),
    TileKind.RIVER:    ("~", "≈"),
    TileKind.MOUNTAIN: ("▲", "△"),
    TileKind.TOWN:     ("▣", "◉"),
}

# Resource glyphs (for mule overlay).
RESOURCE_GLYPH: dict[str, str] = {
    "food":     "F",
    "energy":   "E",
    "smithore": "S",
    "crystite": "C",
}


_FG: dict[TileKind, str] = {
    TileKind.PLAIN:    "rgb(170,180,120)",
    TileKind.RIVER:    "rgb(110,160,220)",
    TileKind.MOUNTAIN: "rgb(200,170,130)",
    TileKind.TOWN:     "rgb(230,210,130)",
}

_BG: dict[TileKind, str] = {
    TileKind.PLAIN:    "rgb(40,50,25)",
    TileKind.RIVER:    "rgb(15,30,55)",
    TileKind.MOUNTAIN: "rgb(50,40,30)",
    TileKind.TOWN:     "rgb(45,35,15)",
}


# Per-player ownership border / tint.
PLAYER_COLORS: list[str] = [
    "rgb(230,80,80)",      # red — P0 (human)
    "rgb(110,140,230)",    # blue — P1
    "rgb(100,200,120)",    # green — P2
    "rgb(230,210,110)",    # yellow — P3
]


def tile_glyph(kind: TileKind, x: int, y: int) -> str:
    a, b = _PATTERN[kind]
    return a if ((x + y) & 1) == 0 else b


def tile_style(kind: TileKind, owner: int | None) -> Style:
    """Compose fg/bg. Owner tint darkens the bg slightly toward player color."""
    fg = _FG[kind]
    bg = _BG[kind]
    if owner is not None:
        pc = PLAYER_COLORS[owner]
        # Blend: bg stays dominant, we just shift the fg if not town.
        return Style.parse(f"bold {pc} on {bg}")
    return Style.parse(f"{fg} on {bg}")


def mule_style(owner: int) -> Style:
    return Style.parse(f"bold white on {PLAYER_COLORS[owner]}")
