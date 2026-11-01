#!/usr/bin/env python3
"""Build the release component with a checked compiler and portable source paths."""
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = 'rustc 1.99.0 (b940084d7 2026-09-28)'
actual = subprocess.check_output(['rustc', '+stable', '--version'], text=True).strip()
if actual != EXPECTED:
    raise SystemExit(f'Requires {EXPECTED}; found {actual}. Select the pinned compiler before building.')
if os.environ.get('RUSTFLAGS') or os.environ.get('CARGO_ENCODED_RUSTFLAGS'):
    raise SystemExit('Unset custom Rust flags for this reproducible release recipe.')
env = dict(os.environ)
env['CARGO_TARGET_DIR'] = str(ROOT / 'work/wasm-target')
env['CARGO_INCREMENTAL'] = '0'
cargo_home = Path(os.environ.get('CARGO_HOME', str(Path.home() / '.cargo'))).resolve()
env['CARGO_ENCODED_RUSTFLAGS'] = '\x1f'.join([
    f'--remap-path-prefix={Path.home()}=/home/builder',
    f'--remap-path-prefix={cargo_home}=/cargo',
    f'--remap-path-prefix={ROOT}=/src/iris-chat-channels',
])
subprocess.run(['cargo', '+stable', 'build', '--locked', '--manifest-path', str(ROOT / 'zeroclaw/plugin/Cargo.toml'),
    '--target', 'wasm32-wasip2', '--release'], env=env, check=True)
