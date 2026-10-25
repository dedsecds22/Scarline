"""Belépési pont a SCARLINE Pygame prototípusához."""

import pygame

from config import FPS, HEIGHT, WIDTH, WINDOW_TITLE
from game import Game


def main() -> None:
    pygame.init()
    pygame.display.set_caption(WINDOW_TITLE)
    screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.DOUBLEBUF)
    clock = pygame.time.Clock()
    game = Game(screen)
    running = True

    while running:
        # A nagy frame-idő ugrások ne okozzanak fizikán átugrást.
        dt = min(clock.tick(FPS) / 1000.0, 0.04)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                game.save(force=True)
                running = False
            elif event.type == pygame.KEYDOWN:
                if game.handle_keydown(event.key):
                    running = False

        if not running:
            break

        game.update(dt, pygame.key.get_pressed())
        game.draw()
        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()
