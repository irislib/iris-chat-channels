#!/usr/bin/env python3
"""Package the checked release component; unsigned, with digest and source provenance."""
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)

git('diff', '--exit-code', 'HEAD', '--', 'zeroclaw/plugin', 'wit', 'scripts/build-wasm.py')
commit = git('rev-parse', 'HEAD').decode().strip()
epoch = int(git('show', '-s', '--format=%ct', commit))
version = json.loads(git('show', commit + ':package.json'))['version']
wasm = (ROOT / 'work/wasm-target/wasm32-wasip2/release/iris_chat.wasm').read_bytes()
if wasm[:4] != b'\0asm':
    raise SystemExit('Build the WASM component first.')
for private_path in (str(ROOT), str(Path.home())):
    if private_path.encode() in wasm:
        raise SystemExit('Binary contains a local path; build with scripts/build-wasm.py.')
digest = hashlib.sha256(wasm).hexdigest()
manifest = f'wasm_sha256 = "{digest}"\n' + git('show', commit + ':zeroclaw/plugin/manifest.toml').decode()
files = {'manifest.toml': manifest.encode(), 'iris_chat.wasm': wasm,
    'LICENSE': git('show', commit + ':LICENSE'), 'README.md': git('show', commit + ':zeroclaw/plugin/README.md'),
    'SOURCE.json': (json.dumps({'repository': 'https://github.com/irislib/iris-chat-channels', 'commit': commit,
        'version': version, 'rustc': '1.99.0 b940084d7', 'target': 'wasm32-wasip2',
        'recipe': 'scripts/build-wasm.py', 'wasm_sha256': digest}, sort_keys=True) + '\n').encode()}
name = f'iris-zeroclaw-{version}.zip'
target = ROOT / 'dist' / name
timestamp = datetime.datetime.fromtimestamp(epoch, datetime.timezone.utc).timetuple()[:6]
with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
    for path, data in sorted(files.items()):
        entry = zipfile.ZipInfo(path, timestamp); entry.external_attr = 0o644 << 16
        archive.writestr(entry, data)
sums = ROOT / 'dist/SHA256SUMS'
lines = [line for line in sums.read_text().splitlines() if not line.endswith('  ' + name)]
lines.append(hashlib.sha256(target.read_bytes()).hexdigest() + '  ' + name)
sums.write_text('\n'.join(lines) + '\n')
print(name)
print('Component SHA-256: ' + digest)
print('Unsigned package: strict hosts require operator-approved signing.')
