"""Interactive commands for the unified Runtime."""

import asyncio
import shlex

from maestro.bootstrap import Platform, build_platform
from maestro.runtime.capabilities import CapabilityKind


_HELP = """Commands:
  run <objective>
  resume <run_id>
  approve <run_id> <approval_id> <revision> [yes|no]
  cancel <run_id>
  skills
  mcp
  help
  exit
"""


def _print_run(run) -> None:
    print(run.final_text or f"Run {run.run_id}: {run.status.value}")


async def _handle(platform: Platform, line: str) -> bool:
    command, _, remainder = line.partition(" ")
    if command in {"exit", "quit", "q"}:
        return False
    if command == "help":
        print(_HELP, end="")
    elif command == "run" and remainder.strip():
        _print_run(await platform.runtime.start(remainder.strip()))
    elif command == "resume" and remainder.strip():
        _print_run(await platform.runtime.execute(remainder.strip()))
    elif command == "cancel" and remainder.strip():
        _print_run(await platform.runtime.cancel(remainder.strip()))
    elif command == "approve":
        parts = shlex.split(remainder)
        if len(parts) not in {3, 4}:
            print("Usage: approve <run_id> <approval_id> <revision> [yes|no]")
        else:
            approved = len(parts) == 3 or parts[3].lower() not in {"no", "n", "false"}
            _print_run(await platform.runtime.approve(parts[0], parts[1], approved, "local-user", int(parts[2])))
    elif command == "skills":
        for skill in platform.skill_catalog.discover().values():
            print(f"{skill.name}\t{skill.description}")
    elif command == "mcp":
        for spec in platform.capabilities.snapshot().values():
            if spec.kind is CapabilityKind.MCP:
                print(spec.name)
    else:
        print(_HELP, end="")
    return True


async def repl() -> None:
    platform = build_platform()
    print(_HELP, end="")
    while True:
        line = (await asyncio.to_thread(input, "\nagent> ")).strip()
        if line and not await _handle(platform, line):
            return


def main() -> None:
    asyncio.run(repl())


if __name__ == "__main__":
    main()
