"""Real harness + real Iris clients over a local relay and deterministic model.

Run only in the disposable --network=none container described in tests/README.md.
All identities, model inputs, and logs are temporary; no personal config is read.
"""
import argparse
import asyncio
import importlib.util
import json
import os
import re
from pathlib import Path
import subprocess
import shutil
import sys
import threading
import time

from local_relay import Relay
from model_fixture import ModelServer

ROOT = Path('/tmp/channels')
PLUGIN_ROOT = ROOT


def main():
    global PLUGIN_ROOT
    parser = argparse.ArgumentParser()
    parser.add_argument('host', choices=['opencode', 'pi', 'nanobot', 'zeroclaw'])
    parser.add_argument('--attempt', default='1')
    parser.add_argument('--plugin-root', default=str(ROOT))
    args = parser.parse_args()
    PLUGIN_ROOT = Path(args.plugin_root).resolve()
    if not str(PLUGIN_ROOT).startswith('/tmp/'):
        raise ValueError('Use only a temporary plugin directory inside the test container.')
    root = Path('/tmp/iris-e2e') / (args.host + '-' + args.attempt)
    if root.exists():
        raise RuntimeError('Use a fresh disposable test directory; preserve previous failure evidence.')
    root.mkdir(parents=True, mode=0o700)
    (root / 'hashtree').mkdir()
    (root / 'hashtree/config.toml').write_text('[blossom]\nservers=[]\nread_servers=["http://127.0.0.1:9"]\nwrite_servers=["http://127.0.0.1:9"]\n')
    env = {key: value for key, value in os.environ.items() if not key.startswith(('IRIS_', 'HTREE_', 'OPENAI_', 'ANTHROPIC_', 'OPENCODE_', 'PI_'))}
    env.update({'HOME': str(root / 'home'), 'XDG_CONFIG_HOME': str(root / 'home/.config'),
        'XDG_DATA_HOME': str(root / 'home/.local/share'), 'XDG_CACHE_HOME': str(root / 'home/.cache'),
        'IRIS_DEMO_RELAYS': '', 'IRIS_FIPS_WEBSOCKET_SEED_URLS': '', 'IRIS_CHAT_FIPS_WEBSOCKET_BIND_ADDR': '',
        'IRIS_CHAT_FIPS_UDP_BIND_ADDR': '', 'IRIS_CHAT_FIPS_ENABLE_WEBRTC': '0', 'IRIS_CHAT_FIPS_STATIC_PEERS': '',
        'IRIS_CHAT_FIPS_ROUTED_PEERS': '', 'IRIS_CHAT_FIPS_TRUSTED_RATERS': '', 'IRIS_CHAT_FIPS_LOCAL_RENDEZVOUS_ADDR': '',
        'IRIS_CHAT_SAME_HOST_HASHTREE': '0', 'IRIS_UPDATE_RELAYS': '', 'IRIS_UPDATE_BLOSSOM_SERVERS': 'http://127.0.0.1:9',
        'HTREE_CONFIG_DIR': str(root / 'hashtree'), 'PYTHONPATH': '/tmp/python', 'NO_COLOR': '1',
        'PATH': '/tmp/bin:/usr/local/bin:/usr/bin:/bin'})
    Path(env['HOME']).mkdir()
    (root / 'bin').mkdir()
    shutil.copyfile(ROOT / 'tests/audit_iris.py', root / 'bin/iris')
    (root / 'bin/iris').chmod(0o755)
    env['PATH'] = str(root / 'bin') + ':' + env['PATH']
    env['IRIS_TEST_AUDIT'] = str(root / 'typing.jsonl')
    processes = []
    logs = []
    relay = Relay(('127.0.0.1', 18777))
    model = ModelServer(('127.0.0.1', 18778))
    for server in (relay, model):
        threading.Thread(target=server.serve_forever, daemon=True).start()

    def run(profile, *arguments):
        result = subprocess.run(['iris', '--json', '--no-background-sync', '--data-dir', str(profile), *arguments],
            env={**env, 'HTREE_DATA_DIR': str(profile / 'htree')}, capture_output=True, timeout=30)
        if result.returncode:
            raise RuntimeError('Iris fixture operation failed: ' + arguments[0])
        value = json.loads(result.stdout)
        if value.get('status') != 'ok':
            raise RuntimeError('Iris fixture operation returned an error.')
        return value['data']

    def start(name, command, extra=None):
        log = (root / (name + '.log')).open('wb')
        logs.append(log)
        process = subprocess.Popen(command, env={**env, **(extra or {})}, cwd='/tmp/test-workspace',
            stdin=subprocess.PIPE, stdout=log, stderr=log)
        processes.append(process)
        return process

    def wait_until(check, seconds=90):
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            value = check()
            if value:
                return value
            if any(process.poll() is not None for process in processes):
                raise RuntimeError('An owned test process exited; inspect container-only logs.')
            time.sleep(0.4)
        raise TimeoutError('Timed out waiting for the integration boundary.')

    def service_ready(name):
        for line in (root / (name + '.log')).read_text().splitlines():
            try:
                if json.loads(line).get('data', {}).get('ready'):
                    return True
            except (ValueError, AttributeError):
                continue
        return False

    state = root / 'agent'
    peer = root / 'peer'
    try:
        for name, profile in [('agent', state / 'profile'), ('peer', peer)]:
            start(name, ['iris', '--json', '--no-background-sync', '--data-dir', str(profile), 'service', 'run'],
                {'HTREE_DATA_DIR': str(profile / 'htree')})
            wait_until(lambda: service_ready(name), 30)
            run(profile, 'relay', 'set', 'ws://127.0.0.1:18777')
            run(profile, 'account', 'create', '--name', 'Disposable ' + name)
        owner = run(peer, 'whoami')['user_id']
        agent = run(state / 'profile', 'whoami')['user_id']
        invitation = run(peer, 'invite', 'create', '--full')['url']
        spec = importlib.util.spec_from_file_location('iris_transport', ROOT / 'hermes/transport.py')
        transport_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(transport_module)
        os.environ.update(env)
        asyncio.run(transport_module.setup(str(state), 'iris', args.host, owner, invitation))
        print(json.dumps({'host': args.host, 'step': 'paired_disposable_identities'}), flush=True)
        host = start_host(args.host, root, state, start)
        approvals = set()
        def first_reply():
            messages = run(peer, 'read', agent, '--limit', '30')['messages']
            if args.host == 'opencode':
                for message in messages:
                    body = message.get('body', '')
                    if (not message.get('is_outgoing') and body.startswith('Permission request ') and
                            '\nread\n' in body and message['id'] not in approvals):
                        snippet = body.replace('\n', ' ')[:96]
                        run(peer, 'send', agent, f"↩ {message['author']}: {snippet}\n\nallow once")
                        approvals.add(message['id'])
            return [m for m in messages if m.get('is_outgoing') is False and m.get('body') == 'IRIS_TEST_OK']
        wait_until(first_reply, 150)
        if args.host == 'opencode':
            assert approvals, 'Read permission was not requested and approved through Iris.'
            assert any(m.get('body') == 'Allowed once.' for m in run(peer, 'read', agent, '--limit', '30')['messages'])
        print(json.dumps({'host': args.host, 'step': 'first_reply'}), flush=True)
        initial_calls = len(model.requests)
        request = run(peer, 'send', agent, 'Read the test marker and report the result.')
        wait_until(lambda: len([m for m in run(peer, 'read', agent, '--limit', '30')['messages']
                               if m.get('is_outgoing') is False and m.get('body') == 'IRIS_TEST_OK']) >= 2, 150)
        assert len(model.requests) > initial_calls, 'Second message did not reach the model.'
        assert any(m.get('role') == 'tool' and 'IRIS_TOOL_OK' in str(m.get('content'))
                   for request in model.requests for m in request.get('messages', [])), 'No real tool result reached the provider.'
        seen = wait_until(lambda: [m for m in run(peer, 'read', agent, '--limit', '30')['messages']
                                  if m.get('id') == request.get('message', request).get('id') and m.get('delivery') == 'seen'], 30)
        assert seen
        def typing_stopped():
            path = root / 'typing.jsonl'
            if not path.exists(): return False
            events = [json.loads(line) for line in path.read_text().splitlines()]
            return events and events[-1] == {'active': False, 'exit': 0}
        wait_until(typing_stopped, 15)
        typing_events = [json.loads(line) for line in (root / 'typing.jsonl').read_text().splitlines()]
        assert sum(event == {'active': True, 'exit': 0} for event in typing_events) >= 2, 'Typing was not refreshed successfully.'
        print(json.dumps({'host': args.host, 'result': 'PASS', 'checks': ['real_plugin_start', 'throwaway_pairing',
            'encrypted_inbound', 'model_call', 'real_file_tool', 'encrypted_reply', 'second_message', 'seen_receipt', 'typing_refresh_and_stop'] + (['remote_permission_once'] if args.host == 'opencode' else []),
            'model_calls': len(model.requests)}), flush=True)
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
        for process in reversed(processes):
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        for log in logs:
            log.close()
        for server in (relay, model):
            server.shutdown()
            server.server_close()


def start_host(host, root, state, start):
    if host == 'opencode':
        shutil.copytree('/tmp/opencode-deps', root / 'home/.config/opencode')
        (state / 'opencode.json').write_text(json.dumps({'enabled': True, 'directory': '/tmp/test-workspace'}))
        config = {'$schema': 'https://opencode.ai/config.json', 'plugin': [(PLUGIN_ROOT / 'opencode/index.mjs').as_uri()],
            'model': 'fixture/iris-fixture', 'provider': {'fixture': {'npm': '@ai-sdk/openai-compatible',
                'options': {'baseURL': 'http://127.0.0.1:18778/v1', 'apiKey': 'fixture'},
                'models': {'iris-fixture': {'name': 'Fixture', 'limit': {'context': 65536, 'output': 4096}}}}},
            'permission': {'read': 'ask', 'bash': 'deny', 'edit': 'deny'}, 'autoupdate': False}
        config_path = root / 'opencode.json'
        config_path.write_text(json.dumps(config))
        process = start('host', ['/tmp/bin/opencode', 'serve', '--hostname', '127.0.0.1', '--port', '18779'],
            {'OPENCODE_CONFIG': str(config_path), 'IRIS_OPENCODE_STATE_DIR': str(state), 'OPENCODE_DISABLE_MODELS_FETCH': '1', 'OPENCODE_DISABLE_DEFAULT_PLUGINS': '1'})
        # OpenCode initializes project plugins lazily, on the first project request.
        import urllib.request
        for _ in range(60):
            try:
                with urllib.request.urlopen('http://127.0.0.1:18779/session?directory=/tmp/test-workspace', timeout=3) as response:
                    response.read()
                break
            except OSError:
                time.sleep(0.5)
        return process
    if host == 'pi':
        agent_dir = root / 'home/.pi/agent'
        agent_dir.mkdir(parents=True)
        (agent_dir / 'models.json').write_text(json.dumps({'providers': {'fixture': {
            'baseUrl': 'http://127.0.0.1:18778/v1', 'api': 'openai-completions', 'apiKey': 'fixture',
            'models': [{'id': 'iris-fixture', 'name': 'Fixture', 'reasoning': False, 'input': ['text'],
                'contextWindow': 65536, 'maxTokens': 4096,
                'cost': {'input': 0, 'output': 0, 'cacheRead': 0, 'cacheWrite': 0}}]}}}))
        return start('host', ['/tmp/bin/pi/pi', '--mode', 'rpc', '--no-session', '--provider', 'fixture',
            '--model', 'iris-fixture', '--extension', str(PLUGIN_ROOT / 'pi/index.mjs')], {'IRIS_PI_STATE_DIR': str(state)})
    if host == 'nanobot':
        config_path = root / 'nanobot.json'
        config_path.write_text(json.dumps({
            'agents': {'defaults': {'workspace': '/tmp/test-workspace', 'model': 'iris-fixture',
                'provider': 'custom', 'maxTokens': 4096, 'contextWindowTokens': 65536}},
            'providers': {'custom': {'apiKey': 'fixture', 'apiBase': 'http://127.0.0.1:18778/v1'}},
            'channels': {'iris': {'enabled': True, 'stateDir': str(state), 'streaming': False}},
            'tools': {'restrictToWorkspace': True},
        }))
        return start('host', ['python3', '-m', 'nanobot', 'gateway', '--foreground', '--config', str(config_path),
            '--workspace', '/tmp/test-workspace', '--port', '18779'])
    if host == 'zeroclaw':
        import base64
        import hashlib
        import tomllib
        sys.path.insert(0, '/tmp/python')
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        package = root / 'package'
        shutil.copytree('/tmp/zeroclaw-package', package)
        key = Ed25519PrivateKey.generate()  # Throwaway test publisher, never persisted.
        public = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
        digest = hashlib.sha256((package / 'iris_chat.wasm').read_bytes()).hexdigest()
        unsigned = f'wasm_sha256 = "{digest}"\n' + (package / 'manifest.toml').read_text()
        signature = base64.urlsafe_b64encode(key.sign(unsigned.rstrip('\n').encode())).decode().rstrip('=')
        (package / 'manifest.toml').write_text(f'signature = "{signature}"\npublisher_key = "{public}"\n' + unsigned)
        config_dir = root / 'zeroclaw'
        config_dir.mkdir()
        config = f'''schema_version = 3
[providers.models.custom.fixture]
uri = "http://127.0.0.1:18778/v1"
api_key = "fixture"
model = "iris-fixture"
native_tools = true
[agents.iris]
model_provider = "custom.fixture"
risk_profile = "fixture"
runtime_profile = "fixture"
channels = ["plugin.iris"]
[agents.iris.workspace]
path = "/tmp/test-workspace"
[agents.iris.precheck]
enabled = false
[risk_profiles.fixture]
allowed_tools = ["file_read"]
auto_approve = ["file_read"]
allowed_roots = ["/tmp/test-workspace"]
forbidden_paths = ["/etc", "/proc", "/sys"]
[runtime_profiles.fixture]
agentic = true
max_tool_iterations = 4
[gateway]
check_updates = false
host = "127.0.0.1"
port = 18779
[plugins]
enabled = true
plugins_dir = {json.dumps(str(config_dir / 'plugins'))}
[plugins.security]
signature_mode = "strict"
trusted_publisher_keys = ["{public}"]
[channels.plugin.iris]
package = "iris-chat"
enabled = true
'''
        config_path = config_dir / 'config.toml'
        config_path.write_text(config)
        result = subprocess.run(['/tmp/bin/zeroclaw', 'plugin', 'install', str(package), '--config-dir', str(config_dir),
            '--channel-alias', 'iris', '--egress', 'none'], capture_output=True, env=os.environ, timeout=90)
        (root / 'install.log').write_bytes(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError('ZeroClaw signature/ABI install check failed; inspect private install log.')
        entries = tomllib.loads(config_path.read_text())['plugins']['entries']
        assert len(entries) == 1
        owner = json.loads((state / 'pairing.json').read_text())['owner_hex']
        config_path.write_text(config + f'''\n[[plugins.entries]]
name = {json.dumps(entries[0]['name'])}
egress_hosts = ["127.0.0.1"]
egress_allow_private = ["127.0.0.1"]
[plugins.entries.config]
owner = "{owner}"
[peer_groups.iris]
channel = "plugin.iris"
external_peers = ["{owner}"]
''')
        start('bridge', ['python3', str(PLUGIN_ROOT / 'zeroclaw/bridge.py'), '--state', str(state)])
        for _ in range(100):
            if (root / 'bridge.log').exists() and 'ready on loopback' in (root / 'bridge.log').read_text():
                break
            time.sleep(0.1)
        return start('host', ['/tmp/bin/zeroclaw', 'daemon', '--config-dir', str(config_dir), '--verbose'])
    raise ValueError('Host fixture not configured yet: ' + host)


if __name__ == '__main__':
    main()
