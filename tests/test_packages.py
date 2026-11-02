"""Exercise released setup entrypoints with a saved contact and a CLI off PATH.

Run after scripts/package.py with IRIS_TEST_PACKAGES=1. No real identities or
network connections are used. Hermes's wizard has separate real-host tests.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = json.loads((ROOT / 'package.json').read_text())['version']
PACKAGES = Path(os.environ.get('IRIS_PACKAGE_DIR', str(ROOT / 'dist')))


@unittest.skipUnless(os.environ.get('IRIS_TEST_PACKAGES') == '1', 'Run after packaging with IRIS_TEST_PACKAGES=1')
class PackagedSetup(unittest.TestCase):
    def test_setup_and_restart_for_every_packaged_entrypoint(self):
        for kind in ('openclaw', 'opencode', 'pi', 'nanobot', 'zeroclaw-bridge'):
            with self.subTest(platform=kind), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                state = root / 'state'
                state.mkdir()
                policy = json.dumps({'owner_hex': 'a'*64, 'chat_id': 'a'*64})
                (state / 'pairing.json').write_text(policy)
                profile = state / 'profile'
                profile.mkdir()
                (profile / 'identity').write_text('private test identity')
                tools = root / 'tools'
                tools.mkdir()
                shutil.copyfile(ROOT / 'tests/fake_iris.py', tools / 'iris')
                (tools / 'iris').chmod(0o755)
                (tools / 'python3').symlink_to(sys.executable)
                env = {**os.environ, 'PATH': str(tools), 'HOME': str(root),
                       'IRIS_OPENCODE_STATE_DIR': str(state), 'IRIS_PI_STATE_DIR': str(state)}
                if kind == 'nanobot':
                    with zipfile.ZipFile(PACKAGES / f'iris_nanobot-{VERSION}-py3-none-any.whl') as bundle:
                        bundle.extractall(root)
                    command = [sys.executable, str(root / 'nanobot/channels/iris/setup.py'), '--state', str(state)]
                else:
                    with tarfile.open(PACKAGES / f'iris-{kind}-{VERSION}.tgz') as bundle:
                        bundle.extractall(root)
                    if kind == 'zeroclaw-bridge':
                        command = [sys.executable, str(root / 'zeroclaw/setup.py'), '--state', str(state)]
                    elif kind == 'openclaw':
                        runner = root / 'run-setup.mjs'
                        runner.write_text('''import { setup } from './package/openclaw/setup.mjs';
const state = process.argv[2];
const current = {};
await setup({runtime: {
  state: { resolveStateDir: () => state + '/..' },
  config: { current: () => ({channels: {iris: {stateDir: state}}}),
    mutateConfigFile: async ({mutate}) => mutate(current) }
}});
if (!current.channels.iris.enabled) throw new Error('Channel not enabled');
''')
                        command = [shutil.which('node'), str(runner), str(state)]
                    else:
                        command = [shutil.which('node'), str(root / f'package/{kind}/setup.mjs'), str(root)]
                for attempt in range(2):
                    result = subprocess.run(command, env=env, input='', text=True, capture_output=True, timeout=20)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(json.loads((state / 'cli.json').read_text())['path'], str(tools / 'iris'))
                    self.assertEqual((state / 'pairing.json').read_text(), policy)
                    self.assertEqual((profile / 'identity').read_text(), 'private test identity')
                    # Subsequent processes cannot discover iris through PATH.
                    env['PATH'] = str(root / 'python-only')
                    Path(env['PATH']).mkdir(exist_ok=True)
                    if attempt == 0:
                        (Path(env['PATH']) / 'python3').symlink_to(sys.executable)


if __name__ == '__main__':
    unittest.main()
