"""Könnyű, saját részecskerendszer Pygame-hez."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

import pygame



@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    life: float
    max_life: float
    size: float
    color: tuple[int, int, int]
    gravity: float = -90.0


@dataclass
class SpriteFx:
    image: pygame.Surface
    x: float
    y: float
    vx: float
    vy: float
    age: float
    duration: float
    scale0: float
    scale1: float
    alpha: int
    angle: float = 0.0
    spin: float = 0.0


class Effects:
    def __init__(self, assets=None) -> None:
        self.assets = assets
        self.particles: list[Particle] = []
        self.sprites: list[SpriteFx] = []
        self.engine_accumulator = 0.0
        self.rng = random.Random()

    def _add_sprite(self, image, x, y, duration, scale0, scale1, alpha, angle=0.0, spin=0.0, vx=0.0, vy=0.0) -> None:
        self.sprites.append(SpriteFx(image, x, y, vx, vy, 0.0, duration, scale0, scale1, alpha, angle, spin))

    def emit_engine(self, x: float, y: float, dt: float, strong: bool = True) -> None:
        self.engine_accumulator += dt
        interval = 0.018 if strong else 0.035
        while self.engine_accumulator >= interval:
            self.engine_accumulator -= interval
            if self.assets is not None and self.rng.random() < 0.16:
                self._add_sprite(
                    self.assets.dust, x - 6, y + self.rng.uniform(-3, 3), 0.55, 0.12, 0.3, 90,
                    angle=self.rng.uniform(0, 360), spin=self.rng.uniform(-60, 60),
                    vx=self.rng.uniform(-70, -30), vy=self.rng.uniform(-15, 15),
                )
            self.particles.append(
                Particle(
                    x=x + self.rng.uniform(-3, 2),
                    y=y + self.rng.uniform(-4, 4),
                    vx=self.rng.uniform(-145, -70),
                    vy=self.rng.uniform(-35, 35),
                    life=self.rng.uniform(0.12, 0.28),
                    max_life=0.28,
                    size=self.rng.uniform(1.5, 3.5),
                    color=self.rng.choice([(83, 190, 239), (255, 152, 70), (255, 216, 134)]),
                    gravity=0.0,
                )
            )

    def explosion(self, x: float, y: float, scale: float = 1.0) -> None:
        if self.assets is not None:
            for image, size, delay_scale in zip(self.assets.explosions, (1.0, 0.8, 0.6), (1.0, 0.8, 0.65)):
                self._add_sprite(
                    image, x, y, 0.5 * delay_scale + 0.1, 0.25 * size * scale, 0.95 * size * scale, 255,
                    angle=self.rng.uniform(0, 360), spin=self.rng.uniform(-80, 80),
                )
            for _ in range(5):
                self._add_sprite(
                    self.assets.dust, x + self.rng.uniform(-14, 14), y + self.rng.uniform(-14, 14),
                    self.rng.uniform(0.7, 1.2), 0.3 * scale, self.rng.uniform(0.9, 1.5) * scale, 150,
                    angle=self.rng.uniform(0, 360), spin=self.rng.uniform(-40, 40),
                    vx=self.rng.uniform(-70, 70), vy=self.rng.uniform(-70, 70),
                )
        colors = [
            (255, 236, 163),
            (255, 165, 73),
            (226, 79, 46),
            (119, 132, 147),
            (67, 76, 91),
        ]
        count = int(72 * scale)
        for _ in range(count):
            angle = self.rng.uniform(0, math.tau)
            speed = self.rng.uniform(65, 330) * scale
            life = self.rng.uniform(0.25, 0.95) * scale
            self.particles.append(
                Particle(
                    x=x + self.rng.uniform(-4, 4),
                    y=y + self.rng.uniform(-4, 4),
                    vx=math.cos(angle) * speed,
                    vy=math.sin(angle) * speed,
                    life=life,
                    max_life=life,
                    size=self.rng.uniform(2.0, 5.5) * scale,
                    color=self.rng.choice(colors),
                    gravity=-145.0,
                )
            )

        # Füstös, lassabb szemcsék.
        for _ in range(18):
            angle = self.rng.uniform(0, math.tau)
            speed = self.rng.uniform(25, 100) * scale
            life = self.rng.uniform(0.65, 1.2) * scale
            self.particles.append(
                Particle(
                    x=x,
                    y=y,
                    vx=math.cos(angle) * speed,
                    vy=math.sin(angle) * speed,
                    life=life,
                    max_life=life,
                    size=self.rng.uniform(4.0, 9.0) * scale,
                    color=(65, 76, 91),
                    gravity=-35.0,
                )
            )

    def update(self, dt: float) -> None:
        alive: list[Particle] = []
        for p in self.particles:
            p.life -= dt
            if p.life <= 0:
                continue
            p.vy += p.gravity * dt
            p.x += p.vx * dt
            p.y += p.vy * dt
            alive.append(p)
        self.particles = alive

        live: list[SpriteFx] = []
        for s in self.sprites:
            s.age += dt
            if s.age >= s.duration:
                continue
            s.x += s.vx * dt
            s.y += s.vy * dt
            s.angle += s.spin * dt
            live.append(s)
        self.sprites = live

    def draw(self, surface: pygame.Surface, camera_x: float, shake_x: int = 0, shake_y: int = 0) -> None:
        center_y = surface.get_height() // 2
        for s in self.sprites:
            t = s.age / s.duration
            scale = s.scale0 + (s.scale1 - s.scale0) * (1.0 - (1.0 - t) ** 2)
            image = pygame.transform.rotozoom(s.image, s.angle, scale)
            image.set_alpha(int(s.alpha * (1.0 - t) ** 1.3))
            rect = image.get_rect(center=(int(s.x - camera_x + shake_x), int(center_y - s.y + shake_y)))
            if rect.right < 0 or rect.left > surface.get_width():
                continue
            surface.blit(image, rect)
        for p in self.particles:
            screen_x = int(p.x - camera_x + shake_x)
            screen_y = int(center_y - p.y + shake_y)
            if screen_x < -20 or screen_x > surface.get_width() + 20 or screen_y < -20 or screen_y > surface.get_height() + 20:
                continue
            fade = max(0.0, min(1.0, p.life / max(0.001, p.max_life)))
            radius = max(1, int(p.size * (0.45 + 0.55 * fade)))
            color = tuple(int(channel * (0.35 + 0.65 * fade)) for channel in p.color)
            pygame.draw.circle(surface, color, (screen_x, screen_y), radius)
