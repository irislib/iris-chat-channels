# Tests

Fast transport and JavaScript checks:

```sh
python3 -m unittest discover -s tests -p 'test_transport.py' -v
python3 -m unittest discover -s tests -p 'test_stdio.py' -v
node --test tests/*.test.mjs
cargo test --locked --manifest-path zeroclaw/plugin/Cargo.toml
```

`hosts.lock.json` pins the exact OpenCode 1.19.5, Pi 1.4.0, nanobot 0.4.0, and ZeroClaw 0.8.7 release commits and Linux amd64 artifact hashes. `scripts/fetch-test-hosts.py` verifies every downloaded or reused artifact before execution. nanobot's Python 3.13 environment is locked with wheel hashes in `nanobot-requirements.lock`; OpenCode's offline startup dependencies are locked in `opencode-package-lock.json`.

## Live host checks

`platform_e2e.py HOST` runs the real host, plugin, Iris CLI, and file-reading tool. Two throwaway identities exchange encrypted messages through `local_relay.py`; `model_fixture.py` provides deterministic model responses with no paid API calls. The relay deliberately omits signature validation and is only a test fixture. Iris still encrypts and decrypts the actual conversation. No personal profiles, contacts, or model configuration are read.

Run these tests only inside a disposable Linux amd64 container with `--network none --cap-drop ALL --security-opt no-new-privileges`, no mounts or published ports, and bounded memory/CPU. Copy files with `docker cp`. Place the repository at `/tmp/channels`, extracted host binaries at `/tmp/bin/{opencode,pi/pi,zeroclaw}`, and a file containing `IRIS_TOOL_OK` at `/tmp/test-workspace/marker.txt`.

Use Iris CLI 2026.10.30, Linux x86_64 asset SHA-256 `e4da5384fb713546db2af1f3b087fdc134ee1d4e73e40d6d32cb1643280037eb`, available from [the Iris CLI release](https://github.com/irislib/iris-chat-rs/releases/tag/v2026.10.30). The executed test base was Debian trixie with Python 3.13.5 and this Iris CLI; the agent hosts came from the separate verified release artifacts.

Install the nanobot lock with `uv pip install --require-hashes --only-binary :all: --python-version 3.13 --python-platform x86_64-unknown-linux-gnu --target /tmp/python -r tests/nanobot-requirements.lock`, then install the Iris wheel into that same target. Copy the OpenCode lock and package manifest as `package-lock.json` and `package.json` into a directory, run `npm ci --ignore-scripts` before disabling networking, and place that directory at `/tmp/opencode-deps`.

Build the ZeroClaw component with Rust 1.99.0 (`rustc b940084d7`, `wasm32-wasip2` target), `cargo build --locked --target wasm32-wasip2 --release`. Put `iris_chat.wasm` and its source `manifest.toml` in `/tmp/zeroclaw-package`. Its test uses a throwaway Ed25519 publisher and strict host verification; it never disables the installer compatibility check. Build dependencies are in `zeroclaw/plugin/Cargo.lock`, and the WIT provenance is in `wit/UPSTREAM_REF`.

Run each host separately, since they share fixture ports:

```sh
python3 /tmp/channels/tests/platform_e2e.py opencode
python3 /tmp/channels/tests/platform_e2e.py pi
python3 /tmp/channels/tests/platform_e2e.py nanobot
python3 /tmp/channels/tests/platform_e2e.py zeroclaw
PYTHONPATH=/tmp/python python3 -m unittest discover -s /tmp/channels/tests -p test_nanobot_runtime.py -v
```

Each run checks pairing, plugin startup, encrypted inbound delivery, model invocation, actual file-tool output, an encrypted reply, a second turn, a seen receipt, and successful typing refresh/stop commands. OpenCode also requests and receives one-time permission over Iris. Failed attempts retain container-only diagnostics; `--attempt NAME` creates a separate throwaway run. Logs may contain throwaway private chat state: publish only the sanitized test result, then remove the test container. Never attach live identities or expose test ports.

Packaging: `python3 scripts/package.py` builds deterministic tarballs and the nanobot wheel from committed `HEAD`, embedding its full source commit. It does not fetch or execute package scripts. Compare `dist/SHA256SUMS` across repeated packaging runs. WASM hashes may vary with compiler/system changes; a successful functional test is not a cross-toolchain reproducibility claim.
