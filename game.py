"""A SCARLINE első játszható prototípusának játéklogikája."""

from __future__ import annotations

import json
import math
import random
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
    PLAYER_SCREEN_X,
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
from terrain import TerrainProfile


SAVE_PATH = Path(__file__).resolve().with_name("save.json")


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
        self.level_index = max(1, int(saved.get("level_index", 1))) if saved else 1
        self.seed = self._seed_for_level(self.level_index)
        self.terrain = self._new_terrain()
        self.best_x = max(0.0, float(saved.get("best_x", 0.0))) if saved else 0.0
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
                if isinstance(data, dict) and data.get("version") in (1, 2):
                    return data
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass
        return None

    def save(self, force: bool = False) -> None:
        if not force and self.best_x - self.last_saved_best < 250.0:
            return
        payload = {
            "version": 2,
            "level_index": self.level_index,
            "best_x": self.best_x,
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
        self.seed = self._seed_for_level(self.level_index)
        self.terrain = self._new_terrain()
        self.best_x = 0.0
        self.last_saved_best = 0.0
        self.effects = Effects(self.assets)
        self.ghosts = []
        self.attempt = 1
        self._respawn(initial=True)
        self.save(force=True)

    def next_level(self) -> None:
        self.level_index += 1
        self.reset_level()

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
        return ["RESUME" if self.started else "START", "RESTART SECTOR", "NEW GAME", "QUIT"]

    def _handle_menu_key(self, key: int) -> bool:
        items = self._menu_items()
        if key in (pygame.K_UP, pygame.K_w):
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
            if choice in ("START", "RESUME"):
                self.started = True
                self.menu_open = False
            elif choice == "RESTART SECTOR":
                self.reset_level()
                self.started = True
                self.menu_open = False
            elif choice == "NEW GAME":
                self.level_index = 1
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
        self.rocket.update(PHYSICS_STEP, thrust, speed)
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
        for ghost in self.ghosts:
            if ghost.done or not ghost.xs:
                continue
            i = min(max(0, ghost.index - 1), len(ghost.xs) - 1)
            j = min(i + 6, len(ghost.xs) - 1)
            k = max(0, i - 6)
            slope = math.atan2(ghost.ys[j] - ghost.ys[k], max(1.0, ghost.xs[j] - ghost.xs[k]))
            sx = ghost.xs[i] - camera_x + shake_x
            sy = HEIGHT / 2 - ghost.ys[i] + shake_y
            if -40 <= sx <= WIDTH + 40:
                image = pygame.transform.rotozoom(self.assets.ghost_rocket, math.degrees(slope), 1.0)
                self.screen.blit(image, image.get_rect(center=(int(sx), int(sy))))

    def draw(self) -> None:
        if self.menu_open:
            self._draw_menu()
            return
        self.screen.fill(BACKGROUND)
        camera_x = max(-PLAYER_SCREEN_X, self.rocket.x - PLAYER_SCREEN_X)
        shake_x = 0
        shake_y = 0
        if self.shake_timer > 0 and self.shake_magnitude > 0.3:
            shake_x = random.randint(-int(self.shake_magnitude), int(self.shake_magnitude))
            shake_y = random.randint(-int(self.shake_magnitude), int(self.shake_magnitude))

        self._draw_background(camera_x, shake_x, shake_y)
        self.terrain.draw(self.screen, camera_x, shake_x, shake_y)
        self._draw_ghosts(camera_x, shake_x, shake_y)
        self.effects.draw(self.screen, camera_x, shake_x, shake_y)

        if self.state == "playing":
            rocket_screen_x = self.rocket.x - camera_x + shake_x
            rocket_screen_y = HEIGHT / 2 - self.rocket.y + shake_y
            thrust = pygame.key.get_pressed()[pygame.K_SPACE] or pygame.key.get_pressed()[pygame.K_w] or pygame.key.get_pressed()[pygame.K_UP]
            self.rocket.draw(self.screen, rocket_screen_x, rocket_screen_y, bool(thrust), self.elapsed)

        self._draw_hud()
        if self.state == "crash":
            self._draw_message("IMPACT", "Restarting - past runs will blast the way.", "Re-launching...", self.crash_timer)
        elif self.state == "complete":
            self._draw_message("SECTOR CLEARED", "The next sector is narrower and faster.", "ENTER / SPACE  -  NEXT LEVEL", None)

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
            y = 300 + i * 64
            selected = i == self.menu_index
            if selected:
                bar = pygame.Rect(WIDTH // 2 - 190, y - 6, 380, 54)
                pygame.draw.rect(self.screen, (24, 36, 56), bar, border_radius=10)
                pygame.draw.rect(self.screen, ACCENT, bar, width=2, border_radius=10)
            self._center_text(label, y, self.font_medium, ACCENT_BRIGHT if selected else TEXT_MAIN)

        self._center_text(f"SECTOR {self.level_index:02d}   -   BEST {self.best_x / 1000:05.2f} km", 570, self.font_small, TEXT_MAIN)
        self._center_text("UP / DOWN  -  SELECT      ENTER  -  CONFIRM      ESC  -  BACK", 640, self.font_tiny, TEXT_MUTED)
        self._center_text("In game: SPACE / W / UP  -  THRUST      R  -  RESTART SECTOR", 664, self.font_tiny, TEXT_MUTED)

    def _draw_background(self, camera_x: float, shake_x: int, shake_y: int) -> None:
        a = self.assets
        size = a.space.get_width()

        def tiled(image: pygame.Surface, speed: float, flags: int = 0) -> None:
            ox = -(int(camera_x * speed) % size) + shake_x // 2
            for x in (ox, ox + size):
                if x < WIDTH:
                    self.screen.blit(image, (x, -300 + shake_y // 2), special_flags=flags)

        tiled(a.space, 0.04)
        tiled(a.space_overlay, 0.09, pygame.BLEND_RGB_ADD)

        sun = a.sun_frames[int(self.clock * 10) % len(a.sun_frames)]
        sun_x = int(WIDTH - 260 - (camera_x * 0.02) % (WIDTH + 700)) % (WIDTH + 700) - 350
        self.screen.blit(sun, (sun_x, 110))

        wrap = WIDTH + 400
        for image, speed, px, py in self.planets:
            x = int((px - camera_x * speed) % wrap) - 200
            self.screen.blit(image, (x + shake_x, int(py) + shake_y))

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
