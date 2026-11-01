#!/usr/bin/env python3
"""Download and verify the exact public host artifacts used by container tests."""
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def main():
    pins = json.loads((ROOT / 'tests/hosts.lock.json').read_text())
    destination = ROOT / 'work/platforms/downloads'
    destination.mkdir(parents=True, exist_ok=True)
    for name, host in pins.items():
        for artifact in host.get('assets', []):
            path = destination / artifact['name']
            expected = artifact['digest'].removeprefix('sha256:')
            if len(expected) != 64:
                raise ValueError('An immutable SHA-256 pin is required.')
            if not path.exists():
                temporary = path.with_suffix(path.suffix + '.part')
                with urllib.request.urlopen(artifact['browser_download_url'], timeout=60) as source, temporary.open('wb') as output:
                    while chunk := source.read(1024 * 1024):
                        output.write(chunk)
                if hashlib.sha256(temporary.read_bytes()).hexdigest() != expected:
                    raise ValueError('Downloaded artifact failed integrity verification.')
                temporary.rename(path)
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise ValueError('Cached artifact failed integrity verification.')
            print(name, host['version'], 'verified', flush=True)


if __name__ == '__main__':
    main()
