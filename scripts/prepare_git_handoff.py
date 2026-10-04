"""Export a coordinator-owned frozen contract from a fetched Git ref, without switching branches."""

import argparse
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from verify_handoff import check_name, verify_task_bundle


def git(repo: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(repo), *args], stderr=subprocess.PIPE)


def prepare(repo: Path, ref: str, output: Path, contract_prefix: str = "handoffs/M0/v2") -> dict:
    repo = repo.resolve()
    if output.is_symlink():
        raise ValueError("Output must not be a symlink")
    output = output.absolute()
    if output.exists():
        raise ValueError("Contract output already exists; it will not be overwritten")
    checkout = Path(git(repo, "rev-parse", "--show-toplevel").decode().strip()).resolve()
    if output.resolve().is_relative_to(checkout):
        raise ValueError("Contract must be outside the implementation checkout")
    spec_commit = git(repo, "rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}")
    spec_commit = spec_commit.decode().strip()
    if not re.fullmatch(r"[a-f0-9]{40}|[a-f0-9]{64}", spec_commit):
        raise ValueError("Invalid coordinator commit")
    check_name(contract_prefix)
    if not contract_prefix.startswith("handoffs/"):
        raise ValueError("Contract prefix must be under handoffs")
    prefix = contract_prefix + "/"
    metadata = json.loads(git(repo, "show", f"{spec_commit}:{prefix}handoff.json"))
    baseline = metadata["baseline_commit"]
    if not re.fullmatch(r"[a-f0-9]{40}|[a-f0-9]{64}", baseline):
        raise ValueError("Invalid baseline commit")
    head = git(repo, "rev-parse", "HEAD").decode().strip()
    if head != baseline:
        raise ValueError("Initial kickoff requires HEAD exactly at the frozen baseline")
    if git(repo, "status", "--porcelain=v1", "--untracked-files=all").strip():
        raise ValueError("Initial kickoff requires a clean implementation checkout")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".M0-contract-", dir=output.parent))
    try:
        entries = git(repo, "ls-tree", "-r", "-z", spec_commit, "--", prefix).split(b"\0")
        for entry in filter(None, entries):
            header, raw_name = entry.split(b"\t", 1)
            mode, kind, object_id = header.decode().split()
            if kind != "blob" or mode not in {"100644", "100755"}:
                raise ValueError("Contract must contain only ordinary Git files")
            name = raw_name.decode("utf-8")
            if not name.startswith(prefix):
                raise ValueError("Unexpected contract path")
            relative = name.removeprefix(prefix)
            check_name(relative)
            target = stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(git(repo, "cat-file", "blob", object_id))
        manifest = verify_task_bundle(stage / "task-bundle", metadata["bundle_sha256"])
        if manifest["baseline_commit"] != baseline or manifest["task_id"] != metadata["task_id"]:
            raise ValueError("Coordinator metadata and contract do not match")
        output.mkdir(exist_ok=False)
        shutil.copytree(stage, output, dirs_exist_ok=True)
        for path in output.rglob("*"):
            if path.is_file():
                path.chmod(0o444)
    finally:
        shutil.rmtree(stage)
    return {
        "baseline_commit": baseline,
        "coordinator_commit": spec_commit,
        "bundle_sha256": metadata["bundle_sha256"],
        "implementation_branch": metadata["implementation_branch"],
        "contract_directory": str(output / "task-bundle"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", default="origin/main")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--contract-prefix", default="handoffs/M0/v2")
    args = parser.parse_args()
    result = prepare(Path.cwd(), args.ref, args.output, args.contract_prefix)
    print(json.dumps(result, indent=2))
    print("Contract exported and hashes verified. Read-only mode is not an OS sandbox.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
