"""Read-only scaffold diagnostics. This command never launches an agent."""

import argparse
import json
import shutil
import sys

from supervisor import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ab-supervisor",
        description="Development scaffold for the AB Agent Supervisor (execution not implemented).",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("doctor", help="Report scaffold prerequisites without launching agents")
    args = parser.parse_args(argv)

    if args.command == "doctor":
        python_ok = sys.version_info >= (3, 12)
        git_available = shutil.which("git") is not None
        ready = python_ok and git_available
        print(
            json.dumps(
                {
                    "stage": "scaffold",
                    "version": __version__,
                    "python": sys.version.split()[0],
                    "python_supported": python_ok,
                    "git_available": git_available,
                    "optional_agent_commands": {
                        command: shutil.which(command) is not None
                        for command in ("codex", "claude", "hermes")
                    },
                    "development_prerequisites_ready": ready,
                    "workflow_implemented": False,
                    "agent_execution_verified": False,
                    "sandbox_verified": False,
                },
                indent=2,
            )
        )
        return 0 if ready else 1
    return 2
