"""Minimal interactive client for the unified Runtime."""

import asyncio

from maestro.bootstrap import build_platform


async def repl() -> None:
    platform = build_platform()
    while True:
        message = (await asyncio.to_thread(input, "\n你> ")).strip()
        if message in {"exit", "quit", "q"}:
            return
        if not message:
            continue
        run = await platform.runtime.start(message)
        print(run.final_text or f"Run {run.run_id}: {run.status.value}")


def main() -> None:
    asyncio.run(repl())


if __name__ == "__main__":
    main()
