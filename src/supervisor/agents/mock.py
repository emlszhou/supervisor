"""Mock agent adapter for testing without real model services."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from supervisor.workers.process import ProcessRequest, ProcessResult


class MockAdapter:
    """Mock agent that produces predetermined results without calling real services."""

    def __init__(self, scenario: str = "success"):
        self.scenario = scenario
        if scenario not in ["success", "nonzero", "timeout", "malformed", "wrong_identity"]:
            raise ValueError(f"unknown mock scenario: {scenario}")

    def build_request(self, context: dict[str, str], workspace: Path) -> ProcessRequest:
        """Build a ProcessRequest for the mock adapter.

        Args:
            context: dict with task_id, run_id, attempt_id, role, provider
            workspace: workspace root path

        Returns:
            ProcessRequest configured to run the mock script
        """
        for field in ["task_id", "run_id", "attempt_id", "role"]:
            if field not in context:
                raise ValueError(f"context must contain {field}")

        # Build the mock script as a Python one-liner
        identity = json.dumps(
            {
                "schema_version": 1,
                "task_id": context["task_id"],
                "run_id": context["run_id"],
                "attempt_id": context["attempt_id"],
                "role": context["role"],
                "provider": "mock",
            }
        )

        if self.scenario == "success":
            script = (
                f"import json; "
                f'data = json.loads("""{identity}"""); '
                f'data["status"] = "completed"; '
                f'data["exit_code"] = 0; '
                f'data["session_id"] = "mock-session-123"; '
                f'data["truncated"] = False; '
                f'data["usage"] = None; '
                f"print(json.dumps(data))"
            )
        elif self.scenario == "nonzero":
            script = 'import json, sys; print("not completed"); sys.exit(7)'
        elif self.scenario == "timeout":
            script = "import time; time.sleep(10)"
        elif self.scenario == "malformed":
            script = 'print("not valid json")'
        elif self.scenario == "wrong_identity":
            script = (
                f"import json; "
                f'data = json.loads("""{identity}"""); '
                f'data["attempt_id"] = "wrong-attempt"; '
                f'data["status"] = "completed"; '
                f'data["exit_code"] = 0; '
                f'data["session_id"] = "mock-session-456"; '
                f'data["truncated"] = False; '
                f'data["usage"] = None; '
                f"print(json.dumps(data))"
            )

        # Use Python to execute the script
        python_path = sys.executable
        argv = (python_path, "-c", script)

        # Build explicit minimal environment
        env = {
            "PATH": "/usr/bin:/bin",
            "HOME": str(workspace),
        }

        return ProcessRequest(
            argv=argv,
            cwd=workspace,
            workspace_root=workspace,
            env=env,
            timeout_seconds=5.0,
            cancel_grace_seconds=0.2,
            max_output_bytes=1048576,
            attempt_id=context["attempt_id"],
            require_tree_cleanup=False,
        )

    def parse_result(
        self,
        process: ProcessResult,
        *,
        expected: dict[str, str],
    ):
        """Parse mock process result using the standard parser."""
        from supervisor.agents.base import parse_agent_result

        return parse_agent_result(process, expected=expected)
