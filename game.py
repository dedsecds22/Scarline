"""A SCARLINE első játszható prototípusának játéklogikája."""

from __future__ import annotations

import json
import math
import random
import sys
from dataclasses import dataclass
from pathlib import Path

import pygame

from config import (
    ACCENT,
    ACCENT_BRIGHT,
    BACKGROUND,
    BASE_FORWARD_SPEED,
    BASE_SEED,
    CRATER_DEPTH,
    CRATER_RADIUS,
    FORWARD_ACCELERATION,
    HEIGHT,
    MAX_FORWARD_SPEED,
    MAX_LEVEL,
    PLAYER_SCREEN_X,
    ROTATED_ANCHOR,
    GHOST_LEAD_BASE,
    GHOST_LEAD_MAX,
    GHOST_LEAD_STEP,
    PHYSICS_STEP,
    ROCKET_RADIUS,
    TEXT_MAIN,
    TEXT_MUTED,
    WIDTH,
)
from effects import Effects
from assets import Assets
from rocket import Rocket
from terrain import TerrainProfile, zone_kinds


_APP_DIR = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
SAVE_PATH = _APP_DIR / "save.json"


@dataclass
class Ghost:
    """Egy korábbi próbálkozás felvett útvonala; a végpontján kráter robban."""

    xs: list[float]
    ys: list[float]
    side: str
    index: int = 0
    done: bool = False


class Game:
    def __init__(self, screen: pygame.Surface) -> None:
        self.screen = screen
        self.real_screen = screen
        saved = self._read_save()
        self.assets = Assets((WIDTH, HEIGHT))
        self.font_title = self.assets.font(84)
        self.font_large = self.assets.font(42)
        self.font_medium = self.assets.font(26)
        self.font_small = self.assets.font(17)
        self.font_tiny = self.assets.font(14)
        self.menu_open = True
        self.started = False
        self.menu_index = 0
        self.view_flip = 1.0
        self.view_rot = 0.0
        self.world_surf = pygame.Surface((WIDTH, HEIGHT))
        self.side_surf = pygame.Surface((HEIGHT, WIDTH))
        self.level_index = min(MAX_LEVEL, max(1, int(saved.get("level_index", 1)))) if saved else 1
        self.menu_sector = self.level_index
        self.seed = self._seed_for_level(self.level_index)
        self.terrain = self._new_terrain()
        self.best_x = max(0.0, float(saved.get("best_x", 0.0))) if saved else 0.0
        self.bests: dict[int, float] = {}
        if saved:
            for key, value in (saved.get("bests") or {}).items():
                try:
                    self.bests[int(key)] = max(0.0, float(value))
                except (TypeError, ValueError):
                    pass
        self.bests[self.level_index] = self.best_x
        self.last_saved_best = self.best_x

        self.rocket = Rocket(self.assets.rocket)
        self.effects = Effects(self.assets)
        self.ghosts: list[Ghost] = []
        self.trail_x: list[float] = []
        self.trail_y: list[float] = []
        self.accumulator = 0.0
        self.attempt = 1
        self.state = "playing"  # playing, crash, complete
        self.crash_timer = 0.0
        self.elapsed = 0.0
        self.shake_timer = 0.0
        self.shake_magnitude = 0.0
        self.clock = 0.0
        self._build_scenery()
        self._respawn(initial=True)

    def _new_terrain(self) -> TerrainProfile:
        terrain = TerrainProfile(self.seed, self.level_index)
        terrain.texture = self.assets.ground_tiles["Ground" if self.level_index % 2 else "Stone"]
        return terrain

    def _build_scenery(self) -> None:
        """Parallax bolygók: a szint seedje határozza meg az elrendezésüket."""
        rng = random.Random(self.seed + 5)
        self.planets = []
        for layer, speed in enumerate((0.07, 0.12, 0.2)):
            for k in range(3):
                image = self.assets.planets[rng.randrange(len(self.assets.planets))]
                scale = (0.55, 0.8, 1.1)[layer]
                if scale != 1.0:
                    image = pygame.transform.smoothscale(image, (int(150 * scale), int(150 * scale)))
                self.planets.append((image, speed, rng.uniform(0, 1600), rng.uniform(95, HEIGHT - 190)))

    @staticmethod
    def _seed_for_level(level_index: int) -> int:
        return BASE_SEED + (level_index - 1) * 7919

    def _read_save(self) -> dict | None:
        try:
            if SAVE_PATH.exists():
                data = json.loads(SAVE_PATH.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data.get("version") in (1, 2, 3):
                    return data
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass
        return None

    def save(self, force: bool = False) -> None:
        if not force and self.best_x - self.last_saved_best < 250.0:
            return
        self.bests[self.level_index] = self.best_x
        payload = {
            "version": 3,
            "level_index": self.level_index,
            "best_x": self.best_x,
            "bests": {str(level): value for level, value in self.bests.items()},
        }
        try:
            temp_path = SAVE_PATH.with_suffix(".tmp")
            temp_path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
            temp_path.replace(SAVE_PATH)
            self.last_saved_best = self.best_x
        except OSError:
            # A mentés hibája ne állítsa meg a játékot; a futó menet ettől még működik.
            pass

    def _respawn(self, initial: bool = False) -> None:
        # Minden próba az elejéről indul, a kráterek eltűnnek; a korábbi
        # próbák szellemként újra végigmennek és a hibapontjukon kráterezik a pályát.
        self.terrain.restore()
        # Minden újabb szellem korábbról/előrébb indul, így a robbanások
        # időben megelőzik a játékost és nem egyszerre érkeznek.
        for order, ghost in enumerate(self.ghosts):
            lead = min(GHOST_LEAD_MAX, GHOST_LEAD_BASE + order * GHOST_LEAD_STEP)
            ghost.index = min(int(lead / PHYSICS_STEP), len(ghost.xs) - 1)
            ghost.done = False
        self.rocket.reset(0.0, self.terrain.center_y_at(0.0))
        self.trail_x = []
        self.trail_y = []
        self.accumulator = 0.0
        self.elapsed = 0.0
        self.view_flip = 1.0
        self.view_rot = 0.0
        self.state = "playing"
        self.crash_timer = 0.0
        self.effects.engine_accumulator = 0.0
        if not initial:
            self.shake_timer = max(self.shake_timer, 0.12)
            self.shake_magnitude = max(self.shake_magnitude, 3.0)

    def _current_speed(self) -> float:
        level_bonus = (self.level_index - 1) * 15.0
        base = BASE_FORWARD_SPEED + level_bonus
        return min(MAX_FORWARD_SPEED + level_bonus * 0.5, base + self.rocket.x * FORWARD_ACCELERATION)

    def _crash(self, side: str) -> None:
        self.best_x = max(self.best_x, self.rocket.x)
        impact_x = max(0.0, min(float(self.terrain.length), self.rocket.x))
        impact_y = self.terrain.floor_y_at(impact_x) if side == "floor" else self.terrain.ceiling_y_at(impact_x)

        # A próbálkozás útvonala szellemként megmarad a következő körökre.
        self.ghosts.append(Ghost(self.trail_x[:], self.trail_y[:], side))
        self.attempt += 1
        self.effects.explosion(impact_x, impact_y, scale=1.0)
        self.state = "crash"
        self.crash_timer = 0.95
        self.shake_timer = 0.34
        self.shake_magnitude = 12.0
        self.save(force=True)

    def _crater_params(self) -> tuple[float, float]:
        depth = CRATER_DEPTH + min(30.0, (self.level_index - 1) * 3.0)
        radius = CRATER_RADIUS + min(15.0, (self.level_index - 1) * 1.5)
        return radius, depth

    def _step_ghosts(self) -> None:
        for ghost in self.ghosts:
            if ghost.done:
                continue
            ghost.index += 1
            if ghost.index >= len(ghost.xs):
                ghost.done = True
                x = ghost.xs[-1]
                y = ghost.ys[-1]
                radius, depth = self._crater_params()
                self.terrain.carve_crater(x, ghost.side, radius, depth)
                self.effects.explosion(x, y, scale=1.0)
                self.shake_timer = max(self.shake_timer, 0.2)
                self.shake_magnitude = max(self.shake_magnitude, 6.0)

    def reset_level(self) -> None:
        """Teljes újrakezdés: az aktuális szint szellemei és rekordja törlődnek."""
        self.level_index = min(MAX_LEVEL, max(1, self.level_index))
        self.menu_sector = self.level_index
        self.seed = self._seed_for_level(self.level_index)
        self.terrain = self._new_terrain()
        self.best_x = 0.0
        self.bests[self.level_index] = 0.0
        self.last_saved_best = 0.0
        self.effects = Effects(self.assets)
        self.ghosts = []
        self.attempt = 1
        self._respawn(initial=True)
        self.save(force=True)

    def next_level(self) -> None:
        if self.level_index >= MAX_LEVEL:
            self.menu_open = True
            self.menu_index = 0
            return
        self.bests[self.level_index] = max(self.bests.get(self.level_index, 0.0), self.best_x)
        self.level_index += 1
        self.reset_level()

    def _launch_sector(self, sector: int) -> None:
        """Ha másik szektort választottak, azt tölti be (a rekordját megtartva)."""
        if sector == self.level_index:
            return
        stored = self.bests.get(sector, 0.0)
        self.bests[self.level_index] = max(self.bests.get(self.level_index, 0.0), self.best_x)
        self.level_index = sector
        self.reset_level()
        self.best_x = stored
        self.bests[sector] = stored
        self.last_saved_best = stored
        self.save(force=True)
        self.started = False

    def handle_keydown(self, key: int) -> bool:
        """Visszatér True-val, ha az ablak bezárását kérték."""
        if self.menu_open:
            return self._handle_menu_key(key)
        if key == pygame.K_ESCAPE:
            self.menu_open = True
            self.menu_index = 0
            return False
        if key == pygame.K_r:
            self.reset_level()
        elif self.state == "complete" and key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_n):
            self.next_level()
        return False

    def _menu_items(self) -> list[str]:
        first = "RESUME" if self.started and self.menu_sector == self.level_index else "START"
        return [first, "SECTOR", "RESTART SECTOR", "NEW GAME", "QUIT"]

    def _handle_menu_key(self, key: int) -> bool:
        items = self._menu_items()
        if key in (pygame.K_LEFT, pygame.K_a) and items[self.menu_index] == "SECTOR":
            self.menu_sector = max(1, self.menu_sector - 1)
        elif key in (pygame.K_RIGHT, pygame.K_d) and items[self.menu_index] == "SECTOR":
            self.menu_sector = min(MAX_LEVEL, self.menu_sector + 1)
        elif key in (pygame.K_UP, pygame.K_w):
            self.menu_index = (self.menu_index - 1) % len(items)
        elif key in (pygame.K_DOWN, pygame.K_s):
            self.menu_index = (self.menu_index + 1) % len(items)
        elif key == pygame.K_ESCAPE:
            if self.started:
                self.menu_open = False
            else:
                self.save(force=True)
                return True
        elif key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_KP_ENTER):
            choice = items[self.menu_index]
            if choice in ("START", "RESUME", "SECTOR"):
                self._launch_sector(self.menu_sector)
                self.started = True
                self.menu_open = False
            elif choice == "RESTART SECTOR":
                self.level_index = self.menu_sector
                self.reset_level()
                self.started = True
                self.menu_open = False
            elif choice == "NEW GAME":
                self.level_index = 1
                self.bests = {}
                self.reset_level()
                self.started = True
                self.menu_open = False
            else:
                self.save(force=True)
                return True
        return False

    def update(self, dt: float, keys: pygame.key.ScancodeWrapper) -> None:
        self.clock += dt
        if self.menu_open:
            return
        self.effects.update(dt)
        target = -1.0 if self.terrain.is_flipped(self.rocket.x) else 1.0
        self.view_flip += max(-4.0 * dt, min(4.0 * dt, target - self.view_flip))
        rot_target = 1.0 if self.terrain.is_rotated(self.rocket.x) else 0.0
        self.view_rot += max(-2.2 * dt, min(2.2 * dt, rot_target - self.view_rot))
        if self.shake_timer > 0:
            self.shake_timer = max(0.0, self.shake_timer - dt)
            self.shake_magnitude *= max(0.0, 1.0 - dt * 5.0)

        if self.state == "crash":
            self.crash_timer -= dt
            if self.crash_timer <= 0:
                self._respawn()
            return

        if self.state != "playing":
            return

        self.elapsed += dt
        thrust = bool(keys[pygame.K_SPACE] or keys[pygame.K_w] or keys[pygame.K_UP])
        # Fix lépésköz: a szellemek felvétele és lejátszása így mindig szinkronban marad.
        self.accumulator += dt
        while self.accumulator >= PHYSICS_STEP and self.state == "playing":
            self.accumulator -= PHYSICS_STEP
            self._physics_step(thrust)

    def _physics_step(self, thrust: bool) -> None:
        self._step_ghosts()

        speed = self._current_speed()
        flipped = self.terrain.is_flipped(self.rocket.x)
        self.rocket.update(PHYSICS_STEP, thrust, speed, -1.0 if flipped else 1.0)
        self.trail_x.append(self.rocket.x)
        self.trail_y.append(self.rocket.y)
        if thrust:
            self.effects.emit_engine(self.rocket.x - 13.0, self.rocket.y, PHYSICS_STEP)

        if self.rocket.x > self.best_x:
            self.best_x = self.rocket.x
            self.save()

        if self.rocket.x >= self.terrain.length:
            self.rocket.x = float(self.terrain.length)
            self.state = "complete"
            self.save(force=True)
            return

        floor_y = self.terrain.floor_y_at(self.rocket.x)
        ceiling_y = self.terrain.ceiling_y_at(self.rocket.x)
        if self.rocket.y - ROCKET_RADIUS <= floor_y:
            self._crash("floor")
        elif self.rocket.y + ROCKET_RADIUS >= ceiling_y:
            self._crash("ceiling")

    def _draw_ghosts(self, camera_x: float, shake_x: int, shake_y: int) -> None:
        width, height = self.screen.get_size()
        for ghost in self.ghosts:
            if ghost.done or not ghost.xs:
                continue
            i = min(max(0, ghost.index - 1), len(ghost.xs) - 1)
            j = min(i + 6, len(ghost.xs) - 1)
            k = max(0, i - 6)
            slope = math.atan2(ghost.ys[j] - ghost.ys[k], max(1.0, ghost.xs[j] - ghost.xs[k]))
            sx = ghost.xs[i] - camera_x + shake_x
            sy = height / 2 - ghost.ys[i] + shake_y
            if -40 <= sx <= width + 40:
                image = pygame.transform.rotozoom(self.assets.ghost_rocket, math.degrees(slope), 1.0)
                self.screen.blit(image, image.get_rect(center=(int(sx), int(sy))))

    def _camera_x(self, anchor: float) -> float:
        return max(-anchor, self.rocket.x - anchor)

    def _render_world(self, surface: pygame.Surface, anchor: float, shake: tuple[int, int]) -> None:
        self.screen = surface
        surface.fill(BACKGROUND)
        camera_x = self._camera_x(anchor)
        shake_x, shake_y = shake
        self._draw_background(camera_x, shake_x, shake_y)
        self._draw_flip_bands(camera_x, shake_x, shake_y)
        self.terrain.draw(surface, camera_x, shake_x, shake_y)
        self._draw_ghosts(camera_x, shake_x, shake_y)
        self.effects.draw(surface, camera_x, shake_x, shake_y)

        if self.state == "playing":
            rocket_screen_x = self.rocket.x - camera_x + shake_x
            rocket_screen_y = surface.get_height() / 2 - self.rocket.y + shake_y
            pressed = pygame.key.get_pressed()
            thrust = pressed[pygame.K_SPACE] or pressed[pygame.K_w] or pressed[pygame.K_UP]
            self.rocket.draw(surface, rocket_screen_x, rocket_screen_y, bool(thrust), self.elapsed)

    def draw(self) -> None:
        if self.menu_open:
            self._draw_menu()
            return
        shake = (0, 0)
        if self.shake_timer > 0 and self.shake_magnitude > 0.3:
            m = int(self.shake_magnitude)
            shake = (random.randint(-m, m), random.randint(-m, m))

        rot = self.view_rot
        if rot < 0.999:
            self._render_world(self.world_surf, PLAYER_SCREEN_X, shake)
        if rot > 0.001:
            self._render_world(self.side_surf, ROTATED_ANCHOR, shake)
        self.screen = self.real_screen
        self._compose_world()
        self._draw_flip_labels()
        self._draw_hud()
        if self.state == "crash":
            self._draw_message("IMPACT", "Restarting - past runs will blast the way.", "Re-launching...", self.crash_timer)
        elif self.state == "complete":
            if self.level_index >= MAX_LEVEL:
                self._draw_message("ALL SECTORS CLEARED", "You mastered every gravity trick.", "ENTER / SPACE  -  MAIN MENU", None)
            else:
                self._draw_message("SECTOR CLEARED", "The next sector is narrower and faster.", "ENTER / SPACE  -  NEXT LEVEL", None)

    def _flipped_view(self, surface: pygame.Surface) -> pygame.Surface:
        """A felület a függőleges nézet-átfordítás állapota szerint (ugyanakkora méretben)."""
        f = self.view_flip
        if f >= 0.999:
            return surface
        image = surface if f > 0 else pygame.transform.flip(surface, False, True)
        if f <= -0.999:
            return image
        # Átmenet: a világ "átbillen" a vízszintes tengelye körül.
        width, height = surface.get_size()
        squashed = max(2, int(abs(f) * height))
        out = pygame.Surface((width, height))
        out.fill(BACKGROUND)
        out.blit(pygame.transform.scale(image, (width, squashed)), (0, (height - squashed) // 2))
        return out

    def _compose_world(self) -> None:
        """A világ-felületeket a nézet állapota (átfordítás, 90 fokos forgatás) szerint a képernyőre teszi."""
        r = self.view_rot
        if r <= 0.001:
            self.screen.blit(self._flipped_view(self.world_surf), (0, 0))
            return
        # Az oldalnézet felülete: előre = felfelé, a gravitáció jobbra, a hajtómű balra hat.
        side = pygame.transform.rotate(self._flipped_view(self.side_surf), 90)
        if r >= 0.999:
            self.screen.blit(side, (0, 0))
            return
        eased = r * r * (3.0 - 2.0 * r)
        theta = math.radians(90.0 * eased)
        pivot = (PLAYER_SCREEN_X + 290.0, HEIGHT / 2 - 80.0)
        rotated = pygame.transform.rotate(self._flipped_view(self.world_surf), math.degrees(theta))
        a, b = WIDTH / 2 - pivot[0], HEIGHT / 2 - pivot[1]
        center = (
            pivot[0] + a * math.cos(theta) + b * math.sin(theta),
            pivot[1] - a * math.sin(theta) + b * math.cos(theta),
        )
        self.screen.fill(BACKGROUND)
        self.screen.blit(rotated, rotated.get_rect(center=(int(center[0]), int(center[1]))))
        side.set_alpha(int(255 * r * r))
        self.screen.blit(side, (0, 0))

    ZONE_COLORS = {
        "flip": ((230, 80, 255), (80, 220, 255)),
        "side": ((255, 160, 50), (90, 255, 140)),
    }

    def _flip_markers(self) -> list[tuple[float, bool, str]]:
        """(x, belépés-e a zónába, zónafajta) hármasok."""
        markers: list[tuple[float, bool, str]] = []
        for kind, start, end in self.terrain.zones:
            markers.append((start, True, kind))
            markers.append((end, False, kind))
        return markers

    def _draw_flip_bands(self, camera_x: float, shake_x: int, shake_y: int) -> None:
        width, height = self.screen.get_size()
        pulse = 0.55 + 0.45 * math.sin(self.clock * 6.0)
        for x, entering, kind in self._flip_markers():
            sx = int(x - camera_x + shake_x)
            if sx < -60 or sx > width + 60:
                continue
            top = int(height / 2 - self.terrain.ceiling_y_at(x) + shake_y) - 40
            bottom = int(height / 2 - self.terrain.floor_y_at(x) + shake_y) + 40
            color = self.ZONE_COLORS[kind][0 if entering else 1]
            band = pygame.Surface((60, max(1, bottom - top)), pygame.SRCALPHA)
            for k in range(6):
                alpha = int((95 - k * 14) * pulse)
                pygame.draw.line(band, (*color, max(0, alpha)), (k * 5 + 2, 0), (k * 5 + 2, band.get_height()), 3)
            pygame.draw.line(band, (*color, 230), (0, 0), (0, band.get_height()), 3)
            self.screen.blit(band, (sx, top))

    def _draw_flip_labels(self) -> None:
        # A feliratok a képernyőn (nem a tükrözött/forgatott világban) készülnek, hogy olvashatóak maradjanak.
        sideways = self.view_rot >= 0.5
        camera_x = self._camera_x(ROTATED_ANCHOR if sideways else PLAYER_SCREEN_X)
        for x, entering, kind in self._flip_markers():
            offset = x - camera_x
            color = self.ZONE_COLORS[kind][0 if entering else 1]
            if kind == "flip":
                label = "GRAVITY FLIP" if entering else "GRAVITY NORMAL"
            else:
                label = "GRAVITY TURN" if entering else "GRAVITY NORMAL"
            rendered = self.font_tiny.render(label, True, color)
            if sideways:
                sy = int(HEIGHT - offset)
                if sy < 90 or sy > HEIGHT + 40:
                    continue
                self.screen.blit(rendered, (WIDTH // 2 - rendered.get_width() // 2, sy - 28))
                self._gravity_arrow(WIDTH // 2, sy - 40, (1, 0), color, 1.2)
                continue
            sx = int(offset)
            if sx < -120 or sx > WIDTH + 120:
                continue
            self.screen.blit(rendered, (sx - rendered.get_width() // 2 + 10, 116))
            if not entering:
                direction = (0, 1)
            else:
                direction = (0, -1) if kind == "flip" else (1, 0)
            self._gravity_arrow(sx + 10, 148, direction, color, 1.2)

    def _gravity_arrow(self, cx: int, cy: int, direction: tuple[int, int], color: tuple[int, int, int], scale: float = 1.0) -> None:
        s = 9 * scale
        dx, dy = direction
        px, py = -dy, dx
        points = [
            (cx + dx * s, cy + dy * s),
            (cx - dx * s * 0.6 + px * s * 0.8, cy - dy * s * 0.6 + py * s * 0.8),
            (cx - dx * s * 0.6 - px * s * 0.8, cy - dy * s * 0.6 - py * s * 0.8),
        ]
        pygame.draw.polygon(self.screen, color, points)

    def _draw_menu(self) -> None:
        # Háttér: a pálya lassan elúszik a rakéta mögött; a játékállás nem módosul.
        camera_x = 1600.0 + self.clock * 90.0
        self.screen.fill(BACKGROUND)
        self._draw_background(camera_x, 0, 0)
        self.terrain.draw(self.screen, camera_x)
        bob = math.sin(self.clock * 2.0) * 10.0
        self.rocket.draw(self.screen, 250, HEIGHT / 2 + bob - 40, True, self.clock)

        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((3, 5, 12, 150))
        self.screen.blit(overlay, (0, 0))

        self._center_text("SCARLINE", 110, self.font_title, ACCENT_BRIGHT)
        self._center_text("Every crash clears the way for the next run.", 215, self.font_small, TEXT_MUTED)

        for i, label in enumerate(self._menu_items()):
            y = 268 + i * 56
            selected = i == self.menu_index
            if selected:
                bar = pygame.Rect(WIDTH // 2 - 190, y - 6, 380, 50)
                pygame.draw.rect(self.screen, (24, 36, 56), bar, border_radius=10)
                pygame.draw.rect(self.screen, ACCENT, bar, width=2, border_radius=10)
            if label == "SECTOR":
                label = f"<   SECTOR {self.menu_sector:02d}   >"
            elif label in ("START", "RESUME") and self.menu_sector != self.level_index:
                label = f"LAUNCH SECTOR {self.menu_sector:02d}"
            self._center_text(label, y, self.font_medium, ACCENT_BRIGHT if selected else TEXT_MAIN)

        sector = self.menu_sector
        best = self.best_x if sector == self.level_index else self.bests.get(sector, 0.0)
        kinds = zone_kinds(sector)
        flips, turns = kinds.count("flip"), kinds.count("side")
        zones = "  ".join(part for part in (f"{flips} GRAVITY FLIP" if flips else "", f"{turns} GRAVITY TURN" if turns else "") if part)
        if sector >= 10:
            zones += "  (COMBINED)"
        self._center_text(f"SECTOR {sector:02d}   -   BEST {best / 1000:05.2f} km", 556, self.font_small, TEXT_MAIN)
        self._center_text(zones or "NO GRAVITY ZONES", 590, self.font_tiny, TEXT_MUTED)
        self._center_text("UP / DOWN  -  SELECT      LEFT / RIGHT  -  SECTOR      ENTER  -  CONFIRM      ESC  -  BACK", 640, self.font_tiny, TEXT_MUTED)
        self._center_text("In game: SPACE / W / UP  -  THRUST      R  -  RESTART SECTOR", 664, self.font_tiny, TEXT_MUTED)

    def _draw_background(self, camera_x: float, shake_x: int, shake_y: int) -> None:
        a = self.assets
        size = a.space.get_width()
        width, height = self.screen.get_size()
        tile_y = -300 if height <= HEIGHT else -max(0, (a.space.get_height() - height) // 2)

        def tiled(image: pygame.Surface, speed: float, flags: int = 0) -> None:
            ox = -(int(camera_x * speed) % size) + shake_x // 2
            for x in (ox, ox + size):
                if x < width:
                    self.screen.blit(image, (x, tile_y + shake_y // 2), special_flags=flags)

        tiled(a.space, 0.04)
        tiled(a.space_overlay, 0.09, pygame.BLEND_RGB_ADD)

        sun = a.sun_frames[int(self.clock * 10) % len(a.sun_frames)]
        sun_x = int(width - 260 - (camera_x * 0.02) % (width + 700)) % (width + 700) - 350
        self.screen.blit(sun, (sun_x, 110 * height // HEIGHT))

        wrap = width + 400
        for image, speed, px, py in self.planets:
            x = int((px - camera_x * speed) % wrap) - 200
            self.screen.blit(image, (x + shake_x, int(py * height / HEIGHT) + shake_y))

    def _draw_hud(self) -> None:
        # Felső, áttetsző helyett sötét, egyszerű HUD-sáv.
        pygame.draw.rect(self.screen, (10, 15, 27), (0, 0, WIDTH, 76))
        pygame.draw.line(self.screen, (35, 51, 71), (0, 75), (WIDTH, 75), 1)
        self._text("SCARLINE", 24, 13, self.font_medium, TEXT_MAIN)
        self._text(f"SECTOR {self.level_index:02d}", 24, 44, self.font_tiny, ACCENT)

        distance = max(0.0, self.rocket.x)
        self._text(f"DIST  {distance / 1000:05.2f} km", 270, 15, self.font_small, TEXT_MAIN)
        self._text(f"BEST  {self.best_x / 1000:05.2f} km   TRY {self.attempt}", 270, 42, self.font_tiny, TEXT_MUTED)
        self._text(f"SPEED  {self._current_speed():03.0f}", 485, 15, self.font_small, ACCENT_BRIGHT)
        self._text("SPACE / W / UP  -  THRUST", 755, 15, self.font_tiny, TEXT_MAIN)
        self._text("R  -  RESTART SECTOR     ESC  -  MENU", 755, 42, self.font_tiny, TEXT_MUTED)

        # Haladási csík.
        bar_x, bar_y, bar_w, bar_h = 24, HEIGHT - 21, WIDTH - 48, 4
        pygame.draw.rect(self.screen, (31, 43, 60), (bar_x, bar_y, bar_w, bar_h), border_radius=2)
        fraction = min(1.0, max(0.0, self.rocket.x / self.terrain.length))
        pygame.draw.rect(self.screen, ACCENT, (bar_x, bar_y, int(bar_w * fraction), bar_h), border_radius=2)
        record_x = bar_x + int(bar_w * min(1.0, self.best_x / self.terrain.length))
        pygame.draw.line(self.screen, ACCENT_BRIGHT, (record_x, bar_y - 3), (record_x, bar_y + bar_h + 3), 2)
        for kind, start, end in self.terrain.zones:
            colors = self.ZONE_COLORS[kind]
            for mark_x, color in ((start, colors[0]), (end, colors[1])):
                px = bar_x + int(bar_w * mark_x / self.terrain.length)
                pygame.draw.line(self.screen, color, (px, bar_y - 5), (px, bar_y + bar_h + 5), 2)

        # Aktuális gravitáció iránya.
        rotated = self.terrain.is_rotated(self.rocket.x)
        flipped = self.terrain.is_flipped(self.rocket.x)
        color = self.ZONE_COLORS["side"][0] if rotated else self.ZONE_COLORS["flip"][0] if flipped else TEXT_MAIN
        direction = (1, 0) if rotated else (0, -1) if flipped else (0, 1)
        self._text("GRAVITY", 1110, 15, self.font_small, color)
        self._gravity_arrow(1235, 26, direction, color, 1.3)
        ahead = [(x, kind) for x, entering, kind in self._flip_markers() if x > self.rocket.x]
        if ahead:
            next_x, next_kind = min(ahead)
            if next_x - self.rocket.x < 500 and int(self.clock * 4) % 2 == 0:
                if next_kind == "side":
                    self._center_text("! ROTATION AHEAD !", 84, self.font_small, self.ZONE_COLORS["side"][0])
                else:
                    self._center_text("! GRAVITY SHIFT AHEAD !", 84, self.font_small, (255, 120, 255))

    def _draw_message(self, title: str, subtitle: str, footer: str, timer: float | None) -> None:
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((3, 5, 12, 125))
        self.screen.blit(overlay, (0, 0))
        panel = pygame.Rect(WIDTH // 2 - 285, HEIGHT // 2 - 116, 570, 232)
        pygame.draw.rect(self.screen, (13, 21, 35), panel, border_radius=12)
        pygame.draw.rect(self.screen, (72, 94, 119), panel, width=1, border_radius=12)
        title_color = ACCENT if self.state == "crash" else ACCENT_BRIGHT
        self._center_text(title, HEIGHT // 2 - 78, self.font_large, title_color)
        self._center_text(subtitle, HEIGHT // 2 - 22, self.font_small, TEXT_MAIN)
        if timer is not None:
            count = max(0, math.ceil(timer * 10) / 10)
            footer = f"RE-LAUNCH IN {count:0.1f}s"
        self._center_text(footer, HEIGHT // 2 + 42, self.font_tiny, TEXT_MUTED)

    def _text(self, value: str, x: int, y: int, font: pygame.font.Font, color: tuple[int, int, int]) -> None:
        self.screen.blit(font.render(value, True, color), (x, y))

    def _center_text(self, value: str, y: int, font: pygame.font.Font, color: tuple[int, int, int]) -> None:
        rendered = font.render(value, True, color)
        self.screen.blit(rendered, (WIDTH // 2 - rendered.get_width() // 2, y))
