"""Az Assets mappa PNG-inek betöltése és előkészítése (display init után hívandó)."""

from __future__ import annotations

import random
import sys
from pathlib import Path

import pygame

_BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
ASSET_DIR = _BASE_DIR / "Assets"
TILE = 128
ROCKET_LENGTH = 52


def _load(*parts: str) -> pygame.Surface:
    return pygame.image.load(str(ASSET_DIR.joinpath(*parts))).convert_alpha()


def _fit(image: pygame.Surface, width: int) -> pygame.Surface:
    rect = image.get_bounding_rect()
    image = image.subsurface(rect).copy()
    height = max(1, round(image.get_height() * width / image.get_width()))
    return pygame.transform.smoothscale(image, (width, height))


def _tile_canvas(kind: str, size: tuple[int, int], seed: int) -> pygame.Surface:
    """Egyetlen, ismétlődő csempe (ground5: teljesen átlátszatlan, a legkisebb varratú)."""
    tile = _load("Ground_Stone", kind, "ground5.png")
    canvas = pygame.Surface(size, pygame.SRCALPHA)
    for y in range(0, size[1], TILE):
        for x in range(0, size[0], TILE):
            canvas.blit(tile, (x, y))
    return canvas


class Assets:
    def font(self, size: int) -> pygame.font.Font:
        return pygame.font.Font(str(ASSET_DIR / "Fonts" / "ComicRelief-Regular.ttf"), size)

    def __init__(self, screen_size: tuple[int, int]) -> None:
        width, height = screen_size

        self.space = _load("Background", "Space.png").convert()
        self.space_overlay = _load("Background", "Space_1.png").convert()
        self.planets = [_load("Background", f"Planet{i}.png") for i in range(10)]
        self.sun_frames = [_load("Background", f"Sun_{i:05d}.png") for i in range(15)]

        canvas_size = (width + TILE * 2, max(width, height) + TILE * 2)
        self.ground_tiles = {
            "Ground": _tile_canvas("Ground", canvas_size, 11),
            "Stone": _tile_canvas("Stone", canvas_size, 23),
        }

        self.rocket = _fit(_load("Other", "rocket.png"), ROCKET_LENGTH)
        ghost = self.rocket.copy()
        ghost.fill((90, 170, 255, 255), special_flags=pygame.BLEND_RGBA_MULT)
        ghost.set_alpha(120)
        self.ghost_rocket = ghost

        self.explosions = [
            _fit(_load("Other", name), 256) for name in ("explosion.png", "explosion2.png", "explosion3.png")
        ]
        self.dust = _fit(_load("Other", "dust.png"), 96)
