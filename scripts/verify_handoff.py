"""Coordinator-side integrity check for offline M0 delivery; not a runtime sandbox."""

import argparse
import hashlib
import json
import re
from pathlib import Path, PurePosixPath


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def files(root: Path) -> dict[str, Path]:
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Expected a real package directory")
    found = {}
    folded = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError("Package must not contain symlinks")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError("Package must contain only regular files")
        name = path.relative_to(root).as_posix()
        if name.casefold() in folded:
            raise ValueError("Case-insensitive path collision")
        folded.add(name.casefold())
        found[name] = path
    return found


def check_name(name: str) -> None:
    path = PurePosixPath(name)
    if (
        not name
        or path.is_absolute()
        or path.as_posix() != name
        or ".." in path.parts
        or "\\" in name
        or ":" in name
    ):
        raise ValueError("Invalid package-relative path")


def verify_task_bundle(root: Path, expected_sha256: str) -> dict:
    if not re.fullmatch(r"[a-f0-9]{64}", expected_sha256):
        raise ValueError("Expected digest must be a SHA256 from the trusted handoff")
    inventory = files(root)
    if "manifest.json" not in inventory:
        raise ValueError("Missing task manifest")
    if digest(inventory["manifest.json"]) != expected_sha256:
        raise ValueError("Task manifest digest mismatch")
    manifest = json.loads(inventory["manifest.json"].read_text(encoding="utf-8"))
    if set(manifest) != {"schema_version", "task_id", "baseline_commit", "files"}:
        raise ValueError("Unknown or missing manifest fields")
    expected = manifest["files"]
    if not isinstance(expected, dict) or not expected:
        raise ValueError("Empty or invalid task inventory")
    if set(inventory) - {"manifest.json"} != set(expected):
        raise ValueError("Task file inventory mismatch")
    for name, checksum in expected.items():
        check_name(name)
        if not isinstance(checksum, str) or not re.fullmatch(r"[a-f0-9]{64}", checksum):
            raise ValueError("Invalid file digest")
        if digest(inventory[name]) != checksum:
            raise ValueError(f"Task content changed: {name}")
    task = json.loads(inventory["task.json"].read_text(encoding="utf-8"))
    if task["status"] != "frozen" or task["baseline_commit"] != manifest["baseline_commit"]:
        raise ValueError("Task must be frozen at the manifest baseline")
    if task["task_id"] != manifest["task_id"] or manifest["schema_version"] != 1:
        raise ValueError("Task and manifest identity mismatch")
    return manifest


def verify_handoff(root: Path, expected_bundle_sha256: str) -> dict:
    inventory = files(root)
    if "CHECKSUMS.sha256" not in inventory:
        raise ValueError("Missing handoff checksums")
    expected = {}
    for line in inventory["CHECKSUMS.sha256"].read_text(encoding="utf-8").splitlines():
        checksum, name = line.split("  ", 1)
        check_name(name)
        if name in expected or not re.fullmatch(r"[a-f0-9]{64}", checksum):
            raise ValueError("Duplicate or invalid handoff checksum")
        expected[name] = checksum
    if set(inventory) - {"CHECKSUMS.sha256"} != set(expected):
        raise ValueError("Handoff inventory mismatch")
    for name, checksum in expected.items():
        if digest(inventory[name]) != checksum:
            raise ValueError(f"Handoff content changed: {name}")
    manifest = verify_task_bundle(root / "task-bundle", expected_bundle_sha256)
    metadata = json.loads(inventory["handoff.json"].read_text(encoding="utf-8"))
    if metadata["baseline_commit"] != manifest["baseline_commit"]:
        raise ValueError("Handoff baseline mismatch")
    if metadata["bundle_sha256"] != expected_bundle_sha256:
        raise ValueError("Handoff task digest mismatch")
    return metadata


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--bundle-sha256", required=True)
    args = parser.parse_args()
    metadata = verify_handoff(args.directory, args.bundle_sha256)
    print(f"Verified offline delivery at baseline {metadata['baseline_commit']}")
    print("Checksums identify contents; they do not prove runtime isolation or M0 completion.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
