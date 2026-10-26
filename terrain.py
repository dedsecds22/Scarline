"""Determinista, rombolható plafon-padló pálya."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Iterable

import pygame

from config import (
    HEIGHT,
    ROCKET_RADIUS,
    TERRAIN_EDGE,
    TERRAIN_FILL,
    TERRAIN_GLOW,
    TERRAIN_STEP,
    WORLD_LENGTH,
)

TILE_SIZE = 128
MAX_COMBINED_LEVEL = 10
OBSTACLE_MIN_LEVEL = 11
DARK_MIN_LEVEL = 13
FULL_COMBO_LEVEL = 15
OBSTACLE_BLAST_RADIUS = 170.0
ROCKET_CLEARANCE = ROCKET_RADIUS + 6.0


def zone_kinds(level_index: int) -> list[str]:
    """A szint gravitációs zónái sorrendben: 'flip' (fejjel lefelé) és 'side' (90 fokos forgatás)."""
    if level_index < 2 or OBSTACLE_MIN_LEVEL <= level_index < FULL_COMBO_LEVEL:
        return []
    if level_index < 4:
        return ["flip"]
    if level_index < 6:
        return ["flip", "flip"]
    if level_index < 8:
        return ["flip", "side", "flip"]
    return ["flip", "side", "flip", "side"]


def dark_count(level_index: int) -> int:
    """A sötét (csak villámfénnyel látható) zónák száma."""
    if level_index < DARK_MIN_LEVEL:
        return 0
    if level_index == DARK_MIN_LEVEL:
        return 2
    if level_index == DARK_MIN_LEVEL + 1:
        return 3
    return 2 if level_index == FULL_COMBO_LEVEL else 3


@dataclass
class Obstacle:
    """Mozgó akadály (akna); a pozíciója a próbálkozás idejének determinisztikus függvénye."""

    x: float
    y: float
    amp_x: float
    amp_y: float
    radius: float
    omega: float
    phase: float
    alive: bool = True

    def position(self, t: float) -> tuple[float, float]:
        angle = self.omega * t + self.phase
        return self.x + self.amp_x * math.cos(angle), self.y + self.amp_y * math.sin(angle)


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
        self._layers: dict[tuple[int, int], tuple[pygame.Surface, pygame.Surface]] = {}
        self.gate_xs: list[float] = []

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
        self.zones = self._plan_zones()
        self.zones = sorted(self.zones + self._plan_darks(), key=lambda zone: zone[1])
        self.obstacles = self._plan_obstacles()

    def _blocked_for_obstacle(self, x: float) -> bool:
        if any(g - 280.0 < x < g + 330.0 for g in self.gate_xs):
            return True
        return any(
            kind != "dark" and (start - 160.0 < x < start + 160.0 or end - 160.0 < x < end + 160.0)
            for kind, start, end in self.zones
        )

    def _plan_obstacles(self) -> list[Obstacle]:
        if self.level_index < OBSTACLE_MIN_LEVEL:
            return []
        rng = random.Random(self.seed * 43 + 11)
        spacing = max(380.0, 620.0 - (self.level_index - OBSTACLE_MIN_LEVEL) * 40.0)
        obstacles: list[Obstacle] = []
        x = 1900.0
        while x < self.length - 600:
            if self._blocked_for_obstacle(x):
                x += 60.0
                continue
            radius = rng.uniform(22.0, 30.0)
            amp_x = rng.choice((0.0, 0.0, 45.0))
            half_gap = (self.ceiling_y_at(x) - self.floor_y_at(x)) * 0.5
            amp_y = max(8.0, half_gap - radius - ROCKET_CLEARANCE - 0.65 * amp_x) * rng.uniform(0.6, 1.0)
            omega = rng.uniform(2.0, 3.4) * (1.0 + 0.04 * (self.level_index - OBSTACLE_MIN_LEVEL))
            obstacles.append(
                Obstacle(x, self.center_y_at(x), amp_x, amp_y, radius, omega, rng.uniform(0.0, math.tau))
            )
            x += spacing * rng.uniform(0.75, 1.25)
        return obstacles

    def _plan_darks(self) -> list[tuple[str, float, float]]:
        count = dark_count(self.level_index)
        if count == 0:
            return []
        rng = random.Random(self.seed * 53 + 5)
        spans: list[tuple[float, float]] = []
        if self.level_index >= FULL_COMBO_LEVEL:
            # Összes elem együtt: a sötétség rátelepszik a gravitációs zónákra is.
            by_start = [zone for zone in self.zones]
            spans.append((by_start[1][1] - 150.0, by_start[2][2] + 300.0))
            spans.append((by_start[3][1] - 200.0, by_start[3][2] + 150.0))
            if count > 2:
                spans.append((by_start[0][1] + 100.0, by_start[0][2] + 100.0))
        else:
            low, high = 2300.0, self.length - 600.0
            slot = (high - low) / count
            for i in range(count):
                length = min(rng.uniform(1500.0, 2100.0), slot - 500.0)
                start = low + i * slot + rng.uniform(100.0, max(100.0, slot - length - 300.0))
                spans.append((start, start + length))
        return [("dark", start, end) for start, end in sorted(spans)]

    def is_dark(self, x: float) -> bool:
        return any(kind == "dark" and start <= x < end for kind, start, end in self.zones)

    def destroy_obstacles_near(self, x: float, radius: float = OBSTACLE_BLAST_RADIUS) -> list[Obstacle]:
        hit = [o for o in self.obstacles if o.alive and abs(o.x - x) <= radius]
        for obstacle in hit:
            obstacle.alive = False
        return hit
    def _generate(self) -> tuple[list[float], list[float]]:
        rng = random.Random(self.seed)
        control_count = math.ceil(self.length / self.CONTROL_SPACING) + 2

        # Magasabb szinteken szűkebb a járat; a közepe viszont nagyobb
        # amplitúdóban mozog, így hosszú, meredek emelkedők/lejtők lesznek.
        if self.level_index <= 4:
            base_half_gap = 104.0 - (self.level_index - 1) * 5.0
        elif self.level_index < OBSTACLE_MIN_LEVEL:
            # Az 5. szinttől lassabban szűkül a járat (korábban 84 -> 59, most 90 -> 75).
            base_half_gap = 90.0 - (self.level_index - 5) * 3.0
        else:
            # A 10. szektor felett a járat tágabb, a nehézséget a mozgó akadályok adják.
            base_half_gap = 128.0 - (self.level_index - OBSTACLE_MIN_LEVEL) * 3.0
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
        self.gate_xs: list[float] = []
        x = 1500.0
        while x < self.length - 600:
            self.gate_xs.append(x)
            first = int(x / self.step)
            for i in range(first, min(self.sample_count, first + gate_width // self.step + 1)):
                floors[i] = centers[i] - 2.0
                ceilings[i] = centers[i] + 2.0
            x += spacing * rng.uniform(0.8, 1.2)

    def _plan_zones(self) -> list[tuple[str, float, float]]:
        """Gravitációs zónák (fajta, kezdet, vég) a szint sorszáma szerint."""
        kinds = zone_kinds(self.level_index)
        if not kinds:
            return []
        rng = random.Random(self.seed * 17 + 3)
        low, high = 2000.0, 10300.0
        slot = (high - low) / len(kinds)

        def clear_of_gates(x: float) -> float:
            # A váltópont ne essen egy kapu közelébe.
            for _ in range(80):
                if all(not (g - 260.0 < x < g + 310.0) for g in self.gate_xs):
                    break
                x += 20.0
            return x

        zones: list[list] = []
        for i, kind in enumerate(kinds):
            length = min(rng.uniform(1400.0, 2000.0), slot - 900.0)
            start = low + i * slot + rng.uniform(100.0, max(100.0, slot - length - 700.0))
            zones.append([kind, start, start + length])

        if self.level_index >= MAX_COMBINED_LEVEL:
            # Kombinált szakasz: a fordított gravitáció egy forgatott zóna közepén kezdődik.
            side = zones[1]
            zones[2] = ["flip", side[1] + 0.5 * (side[2] - side[1]), side[2] + 450.0]

        return [(kind, clear_of_gates(start), clear_of_gates(end)) for kind, start, end in zones]

    def is_flipped(self, x: float) -> bool:
        return any(kind == "flip" and start <= x < end for kind, start, end in self.zones)

    def is_rotated(self, x: float) -> bool:
        return any(kind == "side" and start <= x < end for kind, start, end in self.zones)

    def restore(self) -> None:
        """Visszaállítja az eredeti, kráter nélküli pályát."""
        self.floor, self.ceiling = self._generate()
        for obstacle in self.obstacles:
            obstacle.alive = True

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
        if size not in self._layers:
            self._layers[size] = (pygame.Surface(size, pygame.SRCALPHA), pygame.Surface(size, pygame.SRCALPHA))
        layer, mask = self._layers[size]
        mask.fill((0, 0, 0, 0))
        pygame.draw.polygon(mask, (255, 255, 255, 255), floor_polygon)
        pygame.draw.polygon(mask, (255, 255, 255, 255), ceiling_polygon)
        layer.blit(self.texture, (-(int(camera_x) % TILE_SIZE), 0))
        layer.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        surface.blit(layer, (0, 0))

    def to_save_data(self) -> dict:
        return {
            "seed": self.seed,
            "level_index": self.level_index,
            "length": self.length,
            "step": self.step,
            "floor": self.floor,
            "ceiling": self.ceiling,
        }
