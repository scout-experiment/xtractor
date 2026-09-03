#!/usr/bin/env bash
# Build the single-file zipapp distribution: dist/xtractor.pyz
# Bundles xtractor_cli plus every runtime dependency (twitter-cli fork,
# click, rich, yaml, curl_cffi, browser_cookie3, ...). Rerunnable: removes
# its own artifacts first.
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-.venv/bin/python}"

rm -rf build/pyz-src build/stage
rm -f dist/xtractor.pyz
mkdir -p build/pyz-src build/stage dist

# Install the project and all dependencies into a throwaway target dir.
"$PY" -m pip install --quiet --target build/pyz-src .

# Stage everything (packages + dist-info); pip --target never collides with
# the venv's own site-packages.
cp -a build/pyz-src/. build/stage/
cat > build/stage/__main__.py <<'EOF'
"""Zipapp bootstrap: unpack native extensions to a private cache, then run.
zipimport cannot load compiled extensions from inside an archive, so the
bundle is extracted once to a hash-keyed directory under the xtractor cache
which is put first on sys.path before importing the CLI.
"""

import hashlib
import os
import shutil
import sys
import zipfile
from pathlib import Path


def _extract_native(archive: Path, target: Path) -> None:
    target.mkdir(parents=True)
    os.chmod(target, 0o700)
    with zipfile.ZipFile(archive) as bundle:
        for info in bundle.infolist():
            name = info.filename
            if name.endswith(("/", ".pyc")) or name == "__main__.py":
                continue
            member = os.path.normpath(name)
            if member.startswith(("..", "/")):
                continue
            destination = target / member
            destination.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(info) as source, open(destination, "wb") as output:
                shutil.copyfileobj(source, output)
            mode = (info.external_attr >> 16) & 0o777
            if mode:
                os.chmod(destination, mode)
    (target / ".complete").write_text("ok", encoding="utf-8")


def _run() -> int:
    archive = Path(os.path.dirname(os.path.abspath(__file__)))
    digest = hashlib.sha256()
    with open(archive, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    cache_base = Path(os.environ.get("XTRACTOR_CACHE_DIR", Path.home() / ".cache" / "xtractor"))
    target = cache_base / f"pyz-{digest.hexdigest()[:16]}"

    if not (target / ".complete").is_file():
        staging = target.with_name(f".{target.name}.tmp{os.getpid()}")
        shutil.rmtree(staging, ignore_errors=True)
        _extract_native(archive, staging)
        shutil.rmtree(target, ignore_errors=True)
        staging.rename(target)
    # Native modules from the cache, pure Python from the archive.
    sys.path.insert(0, str(target))

    from xtractor_cli.cli import main

    return main()


sys.exit(_run())
EOF

python3 -m zipapp -p "/usr/bin/env python3" -o dist/xtractor.pyz build/stage
ls -lh dist/xtractor.pyz
