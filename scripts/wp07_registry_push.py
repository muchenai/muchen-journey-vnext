#!/usr/bin/env python3
"""Push one immutable candidate image with bounded, observable retries."""

from __future__ import annotations

import argparse
import subprocess
import time


def push_image(
    component: str,
    reference: str,
    *,
    attempts: int = 3,
    delay_seconds: int = 3,
    runner=subprocess.run,
    sleeper=time.sleep,
) -> int:
    if component not in {"api", "web", "worker"}:
        raise ValueError("component must be api, web, or worker")
    if attempts < 1 or attempts > 3:
        raise ValueError("attempts must be between 1 and 3")
    if delay_seconds < 0 or delay_seconds > 10:
        raise ValueError("delay_seconds must be between 0 and 10")

    for attempt in range(1, attempts + 1):
        print(
            f"WP07_REGISTRY_PUSH component={component} attempt={attempt}/{attempts} "
            "result=START"
        )
        completed = runner(("docker", "push", reference), check=False)
        if completed.returncode == 0:
            print(
                f"WP07_REGISTRY_PUSH component={component} attempt={attempt}/{attempts} "
                "result=PASS"
            )
            return attempt
        if attempt == attempts:
            print(
                f"WP07_REGISTRY_PUSH component={component} attempt={attempt}/{attempts} "
                "result=FAIL retries_exhausted=true"
            )
            raise RuntimeError(f"registry push failed for {component}")
        print(
            f"WP07_REGISTRY_PUSH component={component} attempt={attempt}/{attempts} "
            f"result=RETRY next_in_seconds={delay_seconds}"
        )
        sleeper(delay_seconds)
    raise AssertionError("bounded push loop did not terminate")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--component", required=True, choices=("api", "web", "worker"))
    parser.add_argument("--reference", required=True)
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--delay-seconds", type=int, default=3)
    args = parser.parse_args()
    push_image(
        args.component,
        args.reference,
        attempts=args.attempts,
        delay_seconds=args.delay_seconds,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
