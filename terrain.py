"""Determinista, rombolható plafon-padló pálya."""

from __future__ import annotations

import math
import random
from typing import Iterable

import pygame

from config import (
    HEIGHT,
    TERRAIN_EDGE,
    TERRAIN_FILL,
    TERRAIN_GLOW,
    TERRAIN_STEP,
    WORLD_LENGTH,
)

TILE_SIZE = 128


class TerrainProfile:
    """A pályát két mintavételezett görbe írja le: floor és ceiling."""

    CONTROL_SPACING = 235.0

    def __init__(
        self,
        seed: int,
        level_index: int = 1,
        *,
        floor: Iterable[float] | None = None,
        ceiling: Iterable[float] | None = None,
        length: int = WORLD_LENGTH,
        step: int = TERRAIN_STEP,
    ) -> None:
        self.seed = int(seed)
        self.level_index = max(1, int(level_index))
        self.length = int(length)
        self.step = int(step)
        self.sample_count = self.length // self.step + 1
        self.texture: pygame.Surface | None = None
        self._layer: pygame.Surface | None = None
        self._mask: pygame.Surface | None = None

        if floor is not None and ceiling is not None:
            loaded_floor = [float(v) for v in floor]
            loaded_ceiling = [float(v) for v in ceiling]
            if len(loaded_floor) == self.sample_count and len(loaded_ceiling) == self.sample_count:
                self.floor = loaded_floor
                self.ceiling = loaded_ceiling
            else:
                self.floor, self.ceiling = self._generate()
        else:
            self.floor, self.ceiling = self._generate()

    def _generate(self) -> tuple[list[float], list[float]]:
        rng = random.Random(self.seed)
        control_count = math.ceil(self.length / self.CONTROL_SPACING) + 2

        # Magasabb szinteken szűkebb a járat; a közepe viszont nagyobb
        # amplitúdóban mozog, így hosszú, meredek emelkedők/lejtők lesznek.
        base_half_gap = max(62.0, 104.0 - (self.level_index - 1) * 5.0)
        gap_var = 22.0
        amplitude = 262.0 - (base_half_gap + gap_var)
        max_slope = min(0.62, 0.46 + (self.level_index - 1) * 0.02)

        # Szakaszos, hosszú rámpák: a pálya közepe lineárisan megy célpontról célpontra.
        waypoints = [(0.0, 0.0), (500.0, 0.0)]
        wx, wy = waypoints[-1]
        while wx < self.length + 1200:
            progress = min(1.0, wx / self.length)
            seg_len = rng.uniform(450.0, 1100.0) * (1.0 - 0.35 * progress)
            direction = -1.0 if wy > 0 else 1.0
            if abs(wy) < amplitude * 0.3 and rng.random() < 0.5:
                direction = -direction
            target = wy + direction * rng.uniform(amplitude * 0.9, amplitude * 2.0)
            target = max(-amplitude, min(amplitude, target))
            seg_len = max(seg_len, abs(target - wy) / max_slope)
            wx += seg_len
            wy = target
            waypoints.append((wx, wy))

        raw: list[float] = []
        seg = 0
        for i in range(self.sample_count):
            x = i * self.step
            while waypoints[seg + 1][0] < x:
                seg += 1
            x0, y0 = waypoints[seg]
            x1, y1 = waypoints[seg + 1]
            raw.append(y0 + (y1 - y0) * (x - x0) / (x1 - x0))

        # Kétszeres mozgóátlag: lekerekíti a töréspontokat, a lejtők megmaradnak.
        centers_smooth = raw
        for _ in range(2):
            window = 22
            padded = [centers_smooth[0]] * window + centers_smooth + [centers_smooth[-1]] * window
            centers_smooth = [
                sum(padded[i : i + 2 * window + 1]) / (2 * window + 1)
                for i in range(self.sample_count)
            ]

        half_gaps = [base_half_gap + 10.0]
        for _ in range(1, control_count):
            half_gaps.append(rng.uniform(base_half_gap - gap_var, base_half_gap + gap_var))

        floors: list[float] = []
        ceilings: list[float] = []
        for i in range(self.sample_count):
            x = i * self.step
            control_pos = x / self.CONTROL_SPACING
            left = min(int(control_pos), control_count - 2)
            t = control_pos - left
            smooth_t = 0.5 - 0.5 * math.cos(math.pi * t)
            half_gap = half_gaps[left] + (half_gaps[left + 1] - half_gaps[left]) * smooth_t
            center = centers_smooth[i]
            floors.append(center - half_gap)
            ceilings.append(center + half_gap)

        self._add_gates(floors, ceilings, centers_smooth)
        return floors, ceilings

    def _add_gates(self, floors: list[float], ceilings: list[float], centers: list[float]) -> None:
        """Hirtelen, szinte zárt kapuk: kráter nélkül nem lehet átjutni rajtuk."""
        rng = random.Random(self.seed * 31 + 7)
        spacing = max(1100.0, 1900.0 - (self.level_index - 1) * 120.0)
        gate_width = 50
        x = 1500.0
        while x < self.length - 600:
            first = int(x / self.step)
            for i in range(first, min(self.sample_count, first + gate_width // self.step + 1)):
                floors[i] = centers[i] - 2.0
                ceilings[i] = centers[i] + 2.0
            x += spacing * rng.uniform(0.8, 1.2)

    def restore(self) -> None:
        """Visszaállítja az eredeti, kráter nélküli pályát."""
        self.floor, self.ceiling = self._generate()

    def _value_at(self, values: list[float], x: float) -> float:
        if x <= 0:
            return values[0]
        if x >= self.length:
            return values[-1]
        position = x / self.step
        index = int(position)
        fraction = position - index
        return values[index] * (1.0 - fraction) + values[index + 1] * fraction

    def floor_y_at(self, x: float) -> float:
        return self._value_at(self.floor, x)

    def ceiling_y_at(self, x: float) -> float:
        return self._value_at(self.ceiling, x)

    def center_y_at(self, x: float) -> float:
        return (self.floor_y_at(x) + self.ceiling_y_at(x)) * 0.5

    def carve_crater(self, x: float, side: str, radius: float, depth: float) -> None:
        """Krátert vág a padlóba vagy a plafonba; a módosítás a profilban marad."""
        if side not in ("floor", "ceiling"):
            raise ValueError("A side értéke 'floor' vagy 'ceiling' lehet.")
        if radius <= 0 or depth <= 0:
            return

        first = max(0, int((x - radius) / self.step))
        last = min(self.sample_count - 1, int((x + radius) / self.step) + 1)
        target = self.floor if side == "floor" else self.ceiling

        for i in range(first, last + 1):
            sample_x = i * self.step
            normalized = (sample_x - x) / radius
            if abs(normalized) > 1.0:
                continue
            # Sima, lekerekített kráterprofil; a szélen nullára fut.
            falloff = (1.0 - normalized * normalized) ** 2
            amount = depth * falloff
            if side == "floor":
                target[i] -= amount
            else:
                target[i] += amount

    def draw(self, surface: pygame.Surface, camera_x: float, shake_x: int = 0, shake_y: int = 0) -> None:
        """Kirajzolja a terepet a látható viewporton, plusz néhány peremmintával."""
        start_x = math.floor(camera_x / self.step) * self.step - self.step
        end_x = camera_x + surface.get_width() + self.step
        world_xs = list(range(int(start_x), int(end_x) + self.step, self.step))
        if len(world_xs) < 2:
            return

        floor_points: list[tuple[int, int]] = []
        ceiling_points: list[tuple[int, int]] = []
        center_screen_y = surface.get_height() // 2
        for world_x in world_xs:
            screen_x = int(round(world_x - camera_x + shake_x))
            floor_screen_y = int(round(center_screen_y - self.floor_y_at(world_x) + shake_y))
            ceiling_screen_y = int(round(center_screen_y - self.ceiling_y_at(world_x) + shake_y))
            floor_points.append((screen_x, floor_screen_y))
            ceiling_points.append((screen_x, ceiling_screen_y))

        width = surface.get_width()
        height = surface.get_height()
        floor_polygon = floor_points + [(width + 2, height + 2), (-2, height + 2)]
        ceiling_polygon = [(-2, -2), (width + 2, -2)] + list(reversed(ceiling_points))

        if self.texture is not None:
            self._draw_textured(surface, camera_x, floor_polygon, ceiling_polygon)
            pygame.draw.lines(surface, (18, 11, 8), False, floor_points, 4)
            pygame.draw.lines(surface, (18, 11, 8), False, ceiling_points, 4)
            return

        pygame.draw.polygon(surface, TERRAIN_FILL, floor_polygon)
        pygame.draw.polygon(surface, TERRAIN_FILL, ceiling_polygon)
        pygame.draw.lines(surface, TERRAIN_GLOW, False, floor_points, 7)
        pygame.draw.lines(surface, TERRAIN_GLOW, False, ceiling_points, 7)
        pygame.draw.lines(surface, TERRAIN_EDGE, False, floor_points, 2)
        pygame.draw.lines(surface, TERRAIN_EDGE, False, ceiling_points, 2)

    def _draw_textured(self, surface: pygame.Surface, camera_x: float, floor_polygon: list, ceiling_polygon: list) -> None:
        size = surface.get_size()
        if self._layer is None or self._layer.get_size() != size:
            self._layer = pygame.Surface(size, pygame.SRCALPHA)
            self._mask = pygame.Surface(size, pygame.SRCALPHA)
        self._mask.fill((0, 0, 0, 0))
        pygame.draw.polygon(self._mask, (255, 255, 255, 255), floor_polygon)
        pygame.draw.polygon(self._mask, (255, 255, 255, 255), ceiling_polygon)
        self._layer.blit(self.texture, (-(int(camera_x) % TILE_SIZE), 0))
        self._layer.blit(self._mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        surface.blit(self._layer, (0, 0))

    def to_save_data(self) -> dict:
        return {
            "seed": self.seed,
            "level_index": self.level_index,
            "length": self.length,
            "step": self.step,
            "floor": self.floor,
            "ceiling": self.ceiling,
        }
