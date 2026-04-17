from __future__ import annotations

from command_router import CommandRouter


def main() -> None:
    router = CommandRouter()
    while True:
        try:
            command = input('KIO> ').strip()
        except (EOFError, KeyboardInterrupt):
            print('\nGoodbye.')
            break
        if not command:
            continue
        print(router.handle(command))


if __name__ == '__main__':
    main()
