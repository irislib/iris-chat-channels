import { spawn } from 'node:child_process';
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { normalizeOwner } from './identity.mjs';

export async function setup(api) {
  const current = api.runtime.config.current();
  const previous = current.channels?.iris ?? {};
  if (previous.bridgeUrl) throw new Error('This Iris channel uses a managed transport. Preserve its existing pairing through the container operator.');
  const stateDir = previous.stateDir ?? join(api.runtime.state.resolveStateDir(), 'iris-channel');
  const child = spawn(previous.pythonPath ?? 'python3', [fileURLToPath(new URL('../hermes/transport.py', import.meta.url)),
    'interactive', '--state', stateDir, '--binary', previous.irisPath ?? 'iris'], { stdio: 'inherit' });
  await new Promise((resolve, reject) => {
    child.on('error', () => reject(new Error('Install Python 3 and the Iris CLI, then rerun setup.')));
    child.on('exit', code => code === 0 ? resolve() : reject(new Error('Iris setup did not finish; existing identity is preserved.')));
  });
  const policy = JSON.parse(await readFile(join(stateDir, 'pairing.json'), 'utf8'));
  const owner = normalizeOwner(policy.owner_hex);
  if (policy.chat_id !== owner || (previous.owner && previous.owner !== owner)) throw new Error('Iris contact policy differs; refusing to overwrite configuration.');
  await api.runtime.config.mutateConfigFile({ afterWrite: { mode: 'auto' }, mutate(draft) {
    draft.channels = { ...draft.channels, iris: { ...draft.channels?.iris, enabled: true, owner, stateDir } };
  } });
  console.log('Iris is paired. Start or restart the OpenClaw gateway, then send it a message in Iris.');
}
