#!/usr/bin/env python3
"""Build the offline universal Mac app. Build prerequisites: macOS, Xcode CLI, uv.

Only the build machine downloads dependencies. The resulting app never invokes
pip, uv, git, Homebrew or an external Python on the player's Mac.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from urllib.parse import unquote, urlparse
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / 'desktop/runtime-lock.json'
REQUIREMENTS = ROOT / 'desktop/requirements-macos.lock'


def run(args, **kwargs):
    return subprocess.run([str(arg) for arg in args], check=True, **kwargs)


def verify_sha256(path: Path, expected: str):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    if digest.hexdigest() != expected:
        raise ValueError(f'Runtime checksum mismatch: {path}')


def extract_archive(archive: Path, destination: Path):
    """Preserve Python's symlinks, rejecting archive traversal and special files."""
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with tarfile.open(archive) as tar:
        members = tar.getmembers()
        links = {str(PurePosixPath(item.name)) for item in members if item.issym() or item.islnk()}
        for item in members:
            name = PurePosixPath(item.name)
            target = root / item.name
            unsafe = name.is_absolute() or '..' in name.parts
            unsafe |= any(str(parent) in links for parent in name.parents)
            unsafe |= not (item.isfile() or item.isdir() or item.issym() or item.islnk())
            if item.issym() or item.islnk():
                link = (target.parent if item.issym() else root) / item.linkname
                unsafe |= os.path.commonpath([str(root), str(link.resolve())]) != str(root)
            if unsafe:
                raise ValueError(f'Unsafe archive member: {item.name}')
        # Input archives are checksum verified and every member validated above.
        tar.extractall(destination)


def archive_engine(repository: Path, commit: str, destination: Path):
    """Archive the immutable Git object, never copy a dirty working directory."""
    with tempfile.TemporaryDirectory() as temp:
        archive = Path(temp) / 'engine.tar'
        with archive.open('wb') as output:
            run(['git', '-C', repository, 'archive', '--format=tar', commit], stdout=output)
        extract_archive(archive, destination)


def fetch_runtime(entry: dict, cache: Path, offline: bool):
    archive = cache / unquote(Path(urlparse(entry['url']).path).name)
    if not archive.exists():
        if offline:
            raise FileNotFoundError(f'Offline build needs cached runtime: {archive}')
        partial = archive.with_suffix('.download')
        try:
            with urlopen(entry['url'], timeout=90) as response, partial.open('wb') as target:
                shutil.copyfileobj(response, target)
            verify_sha256(partial, entry['sha256'])
            partial.replace(archive)
        finally:
            partial.unlink(missing_ok=True)
    verify_sha256(archive, entry['sha256'])
    return archive


def compile_launcher(destination: Path, build: Path):
    slices = []
    for arch in ('arm64', 'x86_64'):
        binary = build / f'FrightFeud-{arch}'
        run(['xcrun', 'swiftc', '-swift-version', '5', '-O', '-target', f'{arch}-apple-macos12.0', ROOT / 'desktop/FrightFeud.swift', '-o', binary])
        slices.append(binary)
    run(['xcrun', 'lipo', '-create', *slices, '-output', destination])
    destination.chmod(0o755)


def audit_macos_binaries(root: Path):
    """Fail a release when any bundled Mach-O requires a newer OS than 12.6."""
    magic = {b'\xfe\xed\xfa\xce', b'\xce\xfa\xed\xfe', b'\xfe\xed\xfa\xcf', b'\xcf\xfa\xed\xfe', b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca', b'\xca\xfe\xba\xbf'}
    count = 0
    for path in root.rglob('*'):
        if not path.is_file() or path.is_symlink():
            continue
        with path.open('rb') as source:
            if source.read(4) not in magic:
                continue
        result = run(['xcrun', 'otool', '-l', path], capture_output=True, text=True)
        # `version` also appears in dylib load commands; only inspect minOS blocks.
        versions = re.findall(r'cmd LC_(?:BUILD_VERSION|VERSION_MIN_MACOSX)\b(?:(?!\nLoad command).)*?(?:minos|\bversion)\s+(\d+(?:\.\d+)+)', result.stdout, re.S)
        if not versions:
            raise ValueError(f'No macOS deployment target found: {path}')
        for version in versions:
            if tuple(int(p) for p in version.split('.')[:2]) > (12, 6):
                raise ValueError(f'{path} requires macOS {version}, newer than target 12.6')
        count += 1
    return count


def copy_payload(resources: Path, source: Path = ROOT):
    """Stage launcher, app-scoped relay, and game with content-addressed metadata."""
    helpers = ['launcher.py', 'relay.py']
    helpers.extend(name for name in ('phone_server.py', 'phone_launch.py') if (source / 'desktop' / name).is_file())
    for name in helpers:
        shutil.copy2(source / 'desktop' / name, resources / name)
    game = resources / 'game'
    game.mkdir()
    for name in ('app.json', 'index.html', 'THIRD-PARTY-NOTICES.md'):
        shutil.copy2(source / name, game / name)
    shutil.copytree(source / 'fonts', game / 'fonts')
    if (source / 'assets').is_dir():
        shutil.copytree(source / 'assets', game / 'assets')
    payload = [resources / name for name in helpers]
    payload.extend(path for path in game.rglob('*') if path.is_file())
    return {str(path.relative_to(resources)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(payload)}


def build_bundle(engine_repo: Path, cache: Path, output: Path, offline: bool):
    lock = json.loads(LOCK.read_text())
    work = ROOT / '.build/macos'
    app = work / 'Fright Feud.app'
    if app.exists():
        shutil.rmtree(app)
    contents = app / 'Contents'
    resources = contents / 'Resources'
    executable = contents / 'MacOS/FrightFeud'
    executable.parent.mkdir(parents=True)
    resources.mkdir()
    cache.mkdir(parents=True, exist_ok=True)
    archive_engine(engine_repo, lock['engine_commit'], resources / 'engine')
    for required in ('app_engine/__main__.py', 'app.schema.json', 'model-registry.json', 'launcher.html', 'LICENSE'):
        if not (resources / 'engine' / required).is_file():
            raise ValueError(f'Pinned engine is missing required resource: {required}')
    payload_hashes = copy_payload(resources)
    runtime_hashes = {}
    for arch, entry in lock['runtimes'].items():
        print(f'Bundling {arch} Python and locked binary dependencies…', flush=True)
        runtime = resources / 'runtimes' / arch
        extract_archive(fetch_runtime(entry, cache, offline), runtime)
        site = runtime / 'python/lib/python3.12/site-packages'
        command = ['uv', 'pip', 'install', '--target', site, '--python-version', '3.12', '--python-platform', entry['platform'], '--only-binary', ':all:', '--require-hashes', '--no-deps', '--no-compile-bytecode', '-r', REQUIREMENTS]
        if offline:
            command.append('--offline')
        run(command)
        shutil.copy2(REQUIREMENTS, runtime / 'requirements-macos.lock')
        runtime_hashes[arch] = entry['sha256']
    manifest = dict(lock)
    manifest['requirements_sha256'] = hashlib.sha256(REQUIREMENTS.read_bytes()).hexdigest()
    manifest['runtime_sha256'] = runtime_hashes
    manifest['payload_sha256'] = payload_hashes
    (resources / 'bundle.json').write_text(json.dumps(manifest, indent=2) + '\n')
    shutil.copy2(LOCK, resources / 'runtime-lock.json')
    info = {'CFBundleName': 'Fright Feud', 'CFBundleDisplayName': 'Fright Feud', 'CFBundleIdentifier': lock['bundle_id'], 'CFBundleExecutable': 'FrightFeud', 'CFBundlePackageType': 'APPL', 'CFBundleShortVersionString': lock['version'], 'CFBundleVersion': lock['version'], 'LSMinimumSystemVersion': lock['minimum_macos'], 'NSHighResolutionCapable': True, 'NSPrincipalClass': 'NSApplication'}
    with (contents / 'Info.plist').open('wb') as target:
        plistlib.dump(info, target)
    compile_launcher(executable, work)
    audited = audit_macos_binaries(app)
    # Ad-hoc signing preserves integrity but does not provide notarization.
    run(['codesign', '--force', '--deep', '--sign', '-', app])
    run(['codesign', '--verify', '--deep', '--strict', app])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)
    run(['ditto', '-c', '-k', '--keepParent', '--norsrc', app, output])
    print(f'Built {output} ({output.stat().st_size:,} bytes; {audited} Mach-O files audited)')
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine-repo', type=Path, default=ROOT.parent / 'app-engine')
    parser.add_argument('--cache', type=Path, default=ROOT / '.build-cache')
    parser.add_argument('--output', type=Path, default=ROOT / 'dist/Fright-Feud-macOS.zip')
    parser.add_argument('--offline', action='store_true', help='Use previously cached runtimes and uv wheels only')
    args = parser.parse_args()
    if sys.platform != 'darwin':
        parser.error('Build on macOS with Xcode command-line tools and uv installed.')
    build_bundle(args.engine_repo, args.cache, args.output, args.offline)


if __name__ == '__main__':
    main()
