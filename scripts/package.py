#!/usr/bin/env python3
"""Build an App Engine ZIP using only the Python standard library."""
import argparse
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=root / "dist" / "fright-feud-app-engine.zip")
    parser.add_argument("--prefix", default="", help="Put every file under this top-level folder, e.g. fright-fued")
    args = parser.parse_args()
    if args.prefix and (not args.prefix.replace("-", "").replace("_", "").isalnum()):
        parser.error("--prefix must be a plain folder name")
    prefix = args.prefix + "/" if args.prefix else ""
    manifest = json.loads((root / "app.json").read_text(encoding="utf-8"))
    if manifest.get("id") != "fright-feud" or not (root / "index.html").is_file():
        parser.error("Expected the Fright Feud manifest and index.html")
    files = [root / name for name in ("app.json", "index.html", "README.md", "CLAUDE.md", "THIRD-PARTY-NOTICES.md",
                                        "Launch Fright Feud.command", "Get Latest Updates.command")]
    for folder in ("fonts", "assets", "icon", "scripts", "tests", "desktop", "docs", ".claude/skills"):
        files.extend(p for p in sorted((root / folder).rglob("*"))
                     if p.is_file() and "__pycache__" not in p.parts
                     and p.suffix != ".pyc" and p.name != ".DS_Store"
                     and not p.is_relative_to(root / "docs" / "verification"))
    for path in files:
        if path.is_symlink() or not path.resolve().is_relative_to(root) or not path.is_file():
            parser.error("Missing or unsafe package file: " + str(path))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(args.output, "w", compression=ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, prefix + path.relative_to(root).as_posix())
    print(f"Built {args.output.resolve()} ({args.output.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
