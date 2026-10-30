import json
from .core import run_case


def main():
    for enabled in (False, True):
        print(json.dumps(run_case(enforce_idempotency=enabled), indent=2))


if __name__ == "__main__":
    main()
