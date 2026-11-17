"""Stage and verify monthly CSV release assets without trusting upload success."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path

SYMBOL = re.compile(r"[A-Z][A-Z0-9]{0,19}\Z")
MONTH = re.compile(r"(20[2-9][0-9]|2100)-(0[1-9]|1[0-2])\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def expected(archive):
    manifest = json.loads((archive / "manifest.json").read_text())
    if (manifest.get("version") != 1 or not isinstance(manifest.get("generation"), int)
            or manifest["generation"] < 1 or not MONTH.fullmatch(manifest.get("month_nz", ""))
            or manifest.get("status") not in ("PARTIAL", "V2_COVERAGE_COMPLETE_PENDING_SOURCE_COMPARISON",
                                               "BASELINE_ONLY_UNAUDITED")
            or not isinstance(manifest.get("assets"), dict) or len(manifest["assets"]) != 102):
        raise ValueError("Invalid monthly archive manifest or roster size")
    year, month = manifest["month_nz"].split("-")
    result = {"manifest.json": digest(archive / "manifest.json")}
    for relative, proof in manifest["assets"].items():
        parts = Path(relative).parts
        if (len(parts) != 3 or not SYMBOL.fullmatch(parts[0])
                or parts[1:] != (year, month + ".csv")
                or not isinstance(proof, dict) or set(proof) != {"rows", "sha256"}
                or not isinstance(proof["rows"], int) or proof["rows"] < 0
                or not SHA256.fullmatch(proof["sha256"])):
            raise ValueError("Unsafe or malformed asset entry")
        result[f"{parts[0]}-{year}-{month}.csv"] = proof["sha256"]
    if len(result) != 103:
        raise ValueError("Duplicate monthly market asset")
    return manifest, result


def stage(archive, destination):
    archive, destination = Path(archive), Path(destination)
    if destination.exists():
        raise ValueError("Staging destination already exists")
    manifest, proofs = expected(archive)
    year, month = manifest["month_nz"].split("-")
    for asset, sha in proofs.items():
        source = (archive / "manifest.json" if asset == "manifest.json"
                  else archive / asset.split("-")[0] / year / (month + ".csv"))
        if source.is_symlink() or not source.is_file() or digest(source) != sha:
            raise ValueError(f"Source asset hash mismatch: {asset}")
    destination.mkdir(parents=True)
    for asset in proofs:
        source = (archive / "manifest.json" if asset == "manifest.json"
                  else archive / asset.split("-")[0] / year / (month + ".csv"))
        shutil.copyfile(source, destination / asset)
    verify(archive, destination)
    return manifest, proofs


def verify(archive, downloaded):
    _, proofs = expected(Path(archive))
    downloaded = Path(downloaded)
    actual = {path.name for path in downloaded.iterdir() if path.is_file() and not path.is_symlink()}
    if actual != set(proofs):
        raise ValueError("Release asset set differs from the archive manifest")
    for name, sha in proofs.items():
        if digest(downloaded / name) != sha:
            raise ValueError(f"Downloaded release asset hash mismatch: {name}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("stage", "verify", "metadata"))
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--directory", type=Path)
    args = parser.parse_args()
    if args.command == "metadata":
        manifest, proofs = expected(args.archive)
        print(json.dumps({"month": manifest["month_nz"], "generation": manifest["generation"],
                          "status": manifest["status"], "manifest_sha256": proofs["manifest.json"]}))
    elif args.directory is None:
        parser.error("stage and verify require --directory")
    elif args.command == "stage":
        stage(args.archive, args.directory)
    else:
        verify(args.archive, args.directory)


if __name__ == "__main__":
    main()
