"""A játékos rakétájának egyszerű, asset nélküli megjelenítése és fizikája."""

from __future__ import annotations

import math

import pygame

from config import (
    GRAVITY,
    HEIGHT,
    MAX_VERTICAL_SPEED,
    ROCKET_RADIUS,
    THRUST_ACCELERATION,
)


class Rocket:
    def __init__(self, image: pygame.Surface | None = None) -> None:
        self.image = image
        self.x = 0.0
        self.y = 0.0
        self.vy = 0.0
        self.angle = 0.0
        self.radius = ROCKET_RADIUS

    def reset(self, x: float, y: float) -> None:
        self.x = float(x)
        self.y = float(y)
        self.vy = 0.0
        self.angle = 0.0

    def update(self, dt: float, thrust: bool, forward_speed: float) -> None:
        self.x += forward_speed * dt
        self.vy += GRAVITY * dt
        if thrust:
            self.vy += THRUST_ACCELERATION * dt
        self.vy = max(-MAX_VERTICAL_SPEED, min(MAX_VERTICAL_SPEED, self.vy))
        self.y += self.vy * dt

        # A vizuális billenés követi a függőleges mozgást, de korlátozott marad.
        target_angle = math.atan2(self.vy, max(1.0, forward_speed))
        target_angle = max(math.radians(-38), min(math.radians(38), target_angle))
        blend = min(1.0, dt * 7.0)
        self.angle += (target_angle - self.angle) * blend

    def draw(self, surface: pygame.Surface, screen_x: float, screen_y: float, thrust: bool, time_value: float) -> None:
        center = (int(screen_x), int(screen_y))

        if self.image is not None:
            if thrust:
                flame_length = 30 + 8 * (0.5 + 0.5 * math.sin(time_value * 36.0))
                flame = [(-24, -5), (-flame_length - 6, 0), (-24, 5)]
                pygame.draw.polygon(surface, (255, 106, 49), self._transform(flame, center, self.angle))
                inner = [(-24, -2.5), (-flame_length * 0.8, 0), (-24, 2.5)]
                pygame.draw.polygon(surface, (255, 220, 127), self._transform(inner, center, self.angle))
            rotated = pygame.transform.rotozoom(self.image, math.degrees(self.angle), 1.0)
            surface.blit(rotated, rotated.get_rect(center=center))
            return

        # Hajtómű-láng: néhány változó méretű, rétegzett sokszög.
        if thrust:
            flame_length = 18 + 5 * (0.5 + 0.5 * math.sin(time_value * 36.0))
            flame = [(-10, -4), (-flame_length, 0), (-10, 4)]
            pygame.draw.polygon(surface, (255, 106, 49), self._transform(flame, center, self.angle))
            inner = [(-10, -2), (-flame_length * 0.62, 0), (-10, 2)]
            pygame.draw.polygon(surface, (255, 220, 127), self._transform(inner, center, self.angle))

        # Főtest, orr, alsó/felső stabilizátor és ablak.
        body = [(19, 0), (7, -6), (-11, -5), (-15, 0), (-11, 5), (7, 6)]
        fins = [(-7, -5), (-13, -11), (-2, -7), (-1, -4)]
        fins_bottom = [(-7, 5), (-13, 11), (-2, 7), (-1, 4)]
        pygame.draw.polygon(surface, (203, 220, 235), self._transform(fins, center, self.angle))
        pygame.draw.polygon(surface, (203, 220, 235), self._transform(fins_bottom, center, self.angle))
        pygame.draw.polygon(surface, (236, 242, 248), self._transform(body, center, self.angle))
        pygame.draw.lines(surface, (101, 130, 154), True, self._transform(body, center, self.angle), 1)

        window = self._transform([(8, -2.7), (13, 0), (8, 2.7)], center, self.angle)
        pygame.draw.polygon(surface, (71, 190, 236), window)
        pygame.draw.circle(surface, (255, 255, 255), (int(screen_x + math.cos(self.angle) * 9), int(screen_y - math.sin(self.angle) * 9)), 1)

    @staticmethod
    def _transform(points: list[tuple[float, float]], center: tuple[int, int], angle: float) -> list[tuple[int, int]]:
        # A képernyő Y tengelye lefelé mutat, ezért a vizuális forgatás előjele fordított.
        cosine = math.cos(angle)
        sine = math.sin(angle)
        result: list[tuple[int, int]] = []
        for px, py in points:
            x = px * cosine + py * sine
            y = -px * sine + py * cosine
            result.append((int(center[0] + x), int(center[1] + y)))
        return result
