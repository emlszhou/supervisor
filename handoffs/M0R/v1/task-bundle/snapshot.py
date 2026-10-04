"""Hash a precise tracked Git tree; does not include dirty or untracked files."""

import argparse
import hashlib
import json
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--commit", required=True)
args = parser.parse_args()
commit = (
    subprocess.check_output(
        ["git", "rev-parse", "--verify", "--end-of-options", args.commit + "^{commit}"]
    )
    .decode()
    .strip()
)
manifest = []
for entry in subprocess.check_output(["git", "ls-tree", "-r", "-z", commit]).split(b"\0"):
    if not entry:
        continue
    header, path = entry.split(b"\t", 1)
    mode, kind, oid = header.decode().split()
    if kind != "blob" or mode not in {"100644", "100755"}:
        raise ValueError("Only ordinary tracked files are permitted")
    data = subprocess.check_output(["git", "cat-file", "blob", oid])
    manifest.append(
        dict(path=path.decode("utf-8"), mode=mode, sha256=hashlib.sha256(data).hexdigest())
    )
manifest.sort(key=lambda item: item["path"])
canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
print(
    json.dumps(
        dict(
            commit=commit,
            snapshot_sha256=hashlib.sha256(canonical).hexdigest(),
            tracked_files=len(manifest),
        )
    )
)
