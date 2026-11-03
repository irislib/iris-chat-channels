"""Iris CLI transport shared by the native channels and isolated Docker bridge.

Only one locally approved direct contact is addressable. No raw CLI or arbitrary
recipient operation is exposed by the wire protocol. Python standard library only.
"""
import argparse
import asyncio
import contextlib
import fcntl
import hashlib
import getpass
import json
import os
from pathlib import Path
import platform
import re
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request


# Tagged GitHub workflow artifacts, pinned here rather than trusting a mutable
# installer or fetching checksums from the same server during installation.
IRIS_VERSION = '2026.10.30'
IRIS_RELEASES = {
    ('Darwin', 'arm64'): ('aarch64-apple-darwin', '79748e246adbfebae3fb353ebe9e9d61dee257f741891c1bc474552ede8782ca'),
    ('Darwin', 'x86_64'): ('x86_64-apple-darwin', 'cc60426826970b0d8c2faadd7fab8cbd54b52b76e8e08704006a301d6859e717'),
    ('Linux', 'x86_64'): ('x86_64-unknown-linux-gnu', 'e4da5384fb713546db2af1f3b087fdc134ee1d4e73e40d6d32cb1643280037eb'),
}


class IrisInstallError(RuntimeError):
    """A setup error safe to display without private contact or profile data."""


def resolve_iris(state, binary='iris'):
    if binary != 'iris':
        return str(Path(binary).expanduser())
    saved = Path(state).expanduser() / 'cli.json'
    if saved.exists():
        try:
            path = json.loads(saved.read_text())['path']
            if not isinstance(path, str) or not Path(path).is_absolute():
                raise ValueError()
            return path
        except (ValueError, KeyError, TypeError):
            raise IrisInstallError('The saved Iris location is invalid. Fix cli.json in the channel folder and rerun setup.') from None
    return shutil.which('iris') or 'iris'


def check_iris(binary):
    try:
        result = subprocess.run([binary, '--version'], stdin=subprocess.DEVNULL,
            capture_output=True, text=True, timeout=15, check=True)
        if not result.stdout.strip().startswith('iris '):
            raise ValueError()
    except (OSError, subprocess.SubprocessError, ValueError):
        raise IrisInstallError('Iris could not run. Check the installed CLI and system libraries, then rerun setup. The existing installation was preserved.') from None


def download_iris(destination, target, digest):
    name = f'iris-v{IRIS_VERSION}-{target}.tar.gz'
    url = f'https://github.com/irislib/iris-chat-rs/releases/download/v{IRIS_VERSION}/{name}'
    # The staging directory is task-owned and on the same filesystem as the
    # destination. Only the named regular binary is copied; no archive paths,
    # links, permissions, or installer scripts are extracted or executed.
    with tempfile.TemporaryDirectory(prefix='.iris-install-', dir=destination.parent) as temporary:
        folder = Path(temporary)
        archive = folder / 'release.tar.gz'
        checksum = hashlib.sha256()
        size = 0
        try:
            with urllib.request.urlopen(url, timeout=60) as source, archive.open('wb') as output:
                while chunk := source.read(1024 * 1024):
                    size += len(chunk)
                    if size > 128 * 1024 * 1024:
                        raise IrisInstallError('The Iris download exceeded the expected size. Nothing was installed.')
                    checksum.update(chunk)
                    output.write(chunk)
        except (OSError, TimeoutError):
            raise IrisInstallError('Could not download Iris. Check your internet connection and free disk space, then rerun setup.') from None
        if checksum.hexdigest() != digest:
            raise IrisInstallError('The Iris download failed its checksum check. Nothing was installed; rerun setup to retry.')
        staged = folder / 'iris'
        try:
            with tarfile.open(archive, 'r:gz') as bundle:
                candidates = [member for member in bundle if member.name == 'iris/iris']
                if len(candidates) != 1 or not candidates[0].isfile() or not 0 < candidates[0].size <= 256 * 1024 * 1024:
                    raise IrisInstallError('The Iris release archive does not contain a valid CLI binary.')
                with bundle.extractfile(candidates[0]) as source, staged.open('wb') as output:
                    shutil.copyfileobj(source, output, 1024 * 1024)
            staged.chmod(0o755)
            check_iris(str(staged))
            # link is atomic and refuses to replace a destination created by
            # another process, unlike rename/replace.
            os.link(staged, destination)
        except (tarfile.TarError, OSError):
            raise IrisInstallError('Could not install the Iris release archive. Check the channel folder and free disk space, then rerun setup.') from None


def ensure_iris(state, binary='iris'):
    """Interactive setup only. Runtime resolution never prompts or downloads."""
    state = Path(state).expanduser().resolve()
    candidate = resolve_iris(state, binary)
    existing = shutil.which(candidate)
    if existing:
        selected = str(Path(existing).absolute())
        check_iris(selected)
    else:
        if binary != 'iris' or (state / 'cli.json').exists():
            raise IrisInstallError('The configured Iris CLI is missing. Restore it or correct its configured location, then rerun setup.')
        release = IRIS_RELEASES.get((platform.system(), platform.machine()))
        if not release:
            raise IrisInstallError('Automatic Iris installation is unavailable on this platform. Please install the Iris CLI yourself, then rerun setup: https://irischat.org/#command-line-interface')
        try:
            accepted = input(f'Iris is missing. Install Iris {IRIS_VERSION} for this channel? [Y/n] ').strip().lower()
        except EOFError:
            raise IrisInstallError('Run setup in a terminal to install Iris, or install the Iris CLI yourself and rerun setup.') from None
        if accepted not in ('', 'y', 'yes'):
            raise IrisInstallError('Iris was not installed. Install the CLI yourself or rerun setup when ready.')
        selected = str(state / 'bin/iris')
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (state / 'install.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise IrisInstallError('Another Iris setup is running. Wait for it to finish, then rerun setup.') from None
        if not existing:
            destination = Path(selected)
            destination.parent.mkdir(exist_ok=True, mode=0o700)
            if destination.is_symlink():
                raise IrisInstallError('The Iris install location is a link. Preserve it and choose an existing CLI explicitly.')
            if destination.exists():
                check_iris(selected)
            else:
                print(f'Downloading and checking Iris {IRIS_VERSION}…', flush=True)
                download_iris(destination, *release)
        atomic_json(state / 'cli.json', {'path': selected})
    return selected


def owner_hex(value):
    value = value.strip()
    if len(value) == 64 and all(c in '0123456789abcdef' for c in value):
        return value
    charset = 'qpzry9x8gf2tvdw0s3jn54khce6mua7l'
    if not value.startswith('npub1') or len(value) != 63:
        raise ValueError('Enter your Iris public user ID (npub), not a secret key.')
    try:
        data = [charset.index(c) for c in value[5:]]
    except ValueError:
        raise ValueError('Invalid Iris public user ID.') from None
    chk = 1
    for v in [ord(c) >> 5 for c in 'npub']+[0]+[ord(c) & 31 for c in 'npub']+data:
        top = chk >> 25
        chk = ((chk & 0x1ffffff) << 5) ^ v
        for i, g in enumerate((0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3)):
            if (top >> i) & 1:
                chk ^= g
    if chk != 1:
        raise ValueError('Invalid Iris public user ID checksum.')
    acc = bits = 0
    out = []
    for v in data[:-6]:
        acc = (acc << 5) | v
        bits += 5
        if bits >= 8:
            bits -= 8
            out.append((acc >> bits) & 255)
    if len(out) != 32 or acc & ((1 << bits)-1):
        raise ValueError('Invalid Iris public user ID data.')
    return bytes(out).hex()


def atomic_json(path, value):
    temporary = path.with_suffix('.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as handle:
        json.dump(value, handle)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


APPROVAL_CHOICES = {'allow once': 'allow-once', 'always allow': 'allow-always', 'deny': 'deny'}


def approval_reply(body, history, db):
    # Released Iris clients quote a display name and a snippet, not a message ID.
    # Display names are local to each device. Resolve only a unique sent prompt
    # in this direct chat, then recover its host key from the confirmed outbox.
    header, separator, answer = body.partition('\n\n')
    quoted = separator and header.startswith('↩ ')
    choice = APPROVAL_CHOICES.get((answer if quoted else body).strip().lower())
    if not choice:
        return None
    key = None
    if quoted:
        author, split, snippet = header[2:].partition(': ')
        if author and split and re.match(r'Permission request #[0-9a-f]{12}(?: |$)', snippet):
            matches = []
            for message in history:
                source = message.get('body') or ''
                # Iris quotes the visible body when someone replies to a reply.
                if source.startswith('↩ ') and '\n\n' in source:
                    source = source.partition('\n\n')[2]
                if source.replace('\n', ' ').strip().startswith(snippet):
                    matches.append(message)
            if len(matches) == 1:
                prompt = matches[0]
                if prompt.get('is_outgoing') is True and not prompt.get('deleted_for_everyone'):
                    row = db.execute("SELECT id FROM outbox WHERE message_id=? AND body=? AND id LIKE 'approval:%'",
                                     (prompt['id'], prompt['body'])).fetchone()
                    if row:
                        key = row['id'][len('approval:'):]
    return {'key': key, 'decision': choice}


class Transport:
    def __init__(self, state_dir, binary='iris', profile_dir=None):
        self.state = Path(state_dir).expanduser().resolve()
        self.profile = Path(profile_dir).resolve() if profile_dir else self.state / 'profile'
        self.binary = resolve_iris(self.state, binary)
        self.service = None
        self.lock = None
        self.operation_lock = asyncio.Lock()
        self.last_typing = float('-inf')
        self.last_refresh = float('-inf')

    def policy(self):
        policy = json.loads((self.state / 'pairing.json').read_text())
        owner = owner_hex(policy['owner_hex'])
        if policy.get('chat_id') != owner:
            raise ValueError('Invalid direct-contact policy.')
        return owner

    def database(self):
        db = sqlite3.connect(self.state / 'bridge.sqlite3', timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, body TEXT NOT NULL, status TEXT NOT NULL, created REAL NOT NULL, reply TEXT, sent_id TEXT)')
        db.execute('CREATE TABLE IF NOT EXISTS outbox (id TEXT PRIMARY KEY, body TEXT NOT NULL, created REAL NOT NULL, message_id TEXT, delivery TEXT)')
        db.execute('CREATE TABLE IF NOT EXISTS approval_replies (job_id TEXT PRIMARY KEY, decision TEXT NOT NULL, prompt_key TEXT)')
        return db

    async def cli(self, *args, timeout=45):
        env = {**os.environ, 'IRIS_DATA_DIR': str(self.profile)}
        process = await asyncio.create_subprocess_exec(self.binary, '--json', '--no-background-sync', *args,
            env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            out, _ = await asyncio.wait_for(process.communicate(), timeout)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            if process.returncode is None:
                process.kill()
            await process.wait()
            raise
        if process.returncode:
            raise RuntimeError('Iris command failed; check the private transport log and connectivity.')
        result = json.loads(out)
        if result.get('status') == 'error' or result.get('ok') is False:
            raise RuntimeError('Iris could not complete the operation.')
        return result.get('data', result)

    async def open(self, create=False, name='Iris agent'):
        self.state.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = open(self.state / 'channel.lock', 'a')
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.lock.close()
            self.lock = None
            raise RuntimeError('This Iris identity already has an active channel.') from None
        try:
            if not self.profile.exists() or not any(self.profile.iterdir()):
                if not create:
                    raise RuntimeError('Run the Iris channel setup first.')
                await self.cli('account', 'create', '--name', name)
            # Never replace an existing identity, even if it is damaged or locked.
            await self.cli('whoami')
            status = await self.cli('service', 'status')
            if not status.get('running'):
                log = open(self.state / 'transport.log', 'ab')
                try:
                    self.service = await asyncio.create_subprocess_exec(self.binary, '--json', 'service', 'run',
                        env={**os.environ, 'IRIS_DATA_DIR': str(self.profile)}, stdout=log, stderr=log)
                finally:
                    log.close()
                for _ in range(45):
                    if self.service.returncode is not None:
                        raise RuntimeError('Iris service exited; inspect the private transport log.')
                    status = await self.cli('service', 'status', timeout=5)
                    if status.get('running') and status.get('account_loaded'):
                        break
                    await asyncio.sleep(1)
                else:
                    raise RuntimeError('Iris service is not ready yet; retry setup.')
            with self.database():
                pass
        except BaseException:
            await self.close()
            raise

    async def close(self):
        if self.service and self.service.returncode is None:
            self.service.terminate()
            try:
                await asyncio.wait_for(self.service.wait(), 10)
            except asyncio.TimeoutError:
                self.service.kill()
                await self.service.wait()
        self.service = None
        if self.lock:
            self.lock.close()
            self.lock = None

    async def pair(self, owner, invite):
        owner = owner_hex(owner)
        target = self.state / 'pairing.json'
        if target.exists():
            if self.policy() != owner:
                raise ValueError('Already paired to a different person; existing identity preserved.')
            return {'owner': owner, 'already_paired': True}
        result = await self.cli('invite', 'accept', invite)
        self.validate_chat(result.get('current_chat') or {}, owner)
        await self.cli('privacy', 'unknown-users', 'block')
        with self.database() as db:
            db.execute('INSERT OR IGNORE INTO jobs(id,body,status,created) VALUES (?,?,?,?)',
                ('operator:hello', 'Introduce yourself briefly and say that your Iris chat channel is ready. Keep it to two sentences.', 'new', time.time()))
        atomic_json(target, {'owner_hex': owner, 'chat_id': owner})
        return {'owner': owner, 'already_paired': False}

    @staticmethod
    def validate_chat(chat, owner):
        if chat.get('kind') != 'direct' or chat.get('chat_id') != owner:
            raise ValueError('Only the approved direct conversation is allowed.')

    async def history(self):
        owner = self.policy()
        value = await self.cli('read', owner, '--limit', '1000')
        self.validate_chat(value['chat'], owner)
        return value['messages']

    async def receive(self, active):
        if not isinstance(active, list) or len(active) > 64 or any(not isinstance(i, str) for i in active):
            raise ValueError('Invalid active task list.')
        owner = self.policy()
        if time.monotonic() - self.last_refresh >= 2:
            history = await self.history()
            with self.database() as db:
                for message in history:
                    if (message.get('chat_id') == owner and message.get('is_outgoing') is False
                        and not message.get('deleted_for_everyone') and isinstance(message.get('body'), str)
                        and message['body'].strip() and isinstance(message.get('id'), str)):
                        inserted = db.execute('INSERT OR IGNORE INTO jobs(id,body,status,created) VALUES (?,?,?,?)',
                            (message['id'], message['body'], 'new', message.get('created_at_secs', time.time())))
                        if inserted.rowcount:
                            reply = approval_reply(message['body'], history, db)
                            if reply:
                                db.execute('INSERT INTO approval_replies VALUES (?,?,?)',
                                           (message['id'], reply['decision'], reply['key']))
            self.last_refresh = time.monotonic()
        with self.database() as db:
            rows = db.execute("SELECT * FROM jobs WHERE status != 'done' ORDER BY created,id").fetchall()
            row = next((r for r in rows if r['id'] not in active), None)
            if not row:
                return None
            interrupted = row['status'] != 'new'
            db.execute("UPDATE jobs SET status='running' WHERE id=?", (row['id'],))
            reply = db.execute('SELECT prompt_key,decision FROM approval_replies WHERE job_id=?', (row['id'],)).fetchone()
        return {**({'approval_reply': {'key': reply['prompt_key'], 'decision': reply['decision']}} if reply else {}),
                'id': row['id'], 'text': row['body'], 'owner': owner, 'created': row['created'],
                'interrupted': interrupted, 'pending_reply': row['reply']}

    async def send(self, key, text):
        if not isinstance(key, str) or not 0 < len(key) <= 300 or not isinstance(text, str) or not 0 < len(text) <= 60000:
            raise ValueError('Expected a stable delivery ID and reply text.')
        owner = self.policy()
        with self.database() as db:
            row = db.execute('SELECT * FROM outbox WHERE id=?', (key,)).fetchone()
            if row:
                if row['body'] != text:
                    raise ValueError('A different reply already uses this delivery ID.')
                if row['message_id']:
                    return {'message_id': row['message_id'], 'delivery': row['delivery']}
                # A previous send may have succeeded before its command timed out.
                matches = [m for m in await self.history() if m.get('is_outgoing') and m.get('body') == text
                           and m.get('created_at_secs', 0) >= row['created'] - 1]
                if not matches:
                    raise RuntimeError('Previous send is unconfirmed; inspect Iris history before retrying.')
                message = matches[-1]
            else:
                db.execute('INSERT INTO outbox(id,body,created) VALUES (?,?,?)', (key, text, time.time()))
                db.commit()
                result = await self.cli('send', owner, text)
                message = result.get('message', result)
            if not message.get('id'):
                raise RuntimeError('Iris accepted no message ID; delivery is unconfirmed.')
            db.execute('UPDATE outbox SET message_id=?,delivery=? WHERE id=?',
                (message['id'], message.get('delivery', 'unconfirmed'), key))
            return {'message_id': message['id'], 'delivery': message.get('delivery', 'unconfirmed')}

    async def operation(self, op, data):
        # Operations are serialized across local, stdio, and HTTP clients.
        async with self.operation_lock:
            if op == 'approval' and set(data) == {'key', 'details', 'choices'}:
                key, details, choices = data['key'], data['details'], data['choices']
                if (not isinstance(key, str) or not re.fullmatch(r'[a-z]+:[A-Za-z0-9._:-]{1,200}', key)
                        or not isinstance(details, str) or not details.strip() or not isinstance(choices, list)
                        or not choices or any(c not in APPROVAL_CHOICES for c in choices)):
                    raise ValueError('Invalid approval request.')
                ref = hashlib.sha256(key.encode()).hexdigest()[:12]
                options = ' or '.join(choices)
                return await self.send('approval:' + key, f'Permission request #{ref}\n{details}\n\nReply to this message with {options}.')
            if op == 'health' and not data:
                owner = self.policy()
                status = await self.cli('service', 'status', timeout=5)
                return {'owner': owner, 'ready': bool(status.get('running') and status.get('account_loaded')), 'protocol': 1}
            if op == 'receive' and set(data) == {'active'}:
                return await self.receive(data['active'])
            if op == 'send' and set(data) == {'key', 'text'} and not str(data['key']).startswith('approval:'):
                return await self.send(data['key'], data['text'])
            if op == 'finish' and set(data) == {'id'}:
                with self.database() as db:
                    db.execute("UPDATE jobs SET status='done' WHERE id=? AND status='running'", (data['id'],))
                return {}
            if op == 'seen' and set(data) == {'id'}:
                if not data['id'].startswith('operator:'):
                    await self.cli('seen', self.policy(), data['id'])
                return {}
            if op == 'typing' and set(data) == {'active'} and type(data['active']) is bool:
                if not data['active'] or time.monotonic() - self.last_typing >= 4:
                    await self.cli('typing', self.policy(), *([] if data['active'] else ['--stop']), timeout=5)
                    self.last_typing = time.monotonic() if data['active'] else float('-inf')
                return {}
            raise ValueError('Unsupported Iris channel operation.')


class Client:
    """Local CLI by default; a loopback-only broker keeps keys outside containers."""
    def __init__(self, state_dir=None, bridge_url=None, binary='iris'):
        if bridge_url and bridge_url != 'http://127.0.0.1:8765':
            raise ValueError('Managed bridge must be http://127.0.0.1:8765 in the same network namespace.')
        self.url = bridge_url
        self.transport = None if bridge_url else Transport(state_dir, binary)

    async def open(self):
        if self.transport:
            await self.transport.open()
        return await self.call('health')

    async def close(self):
        if self.transport:
            await self.transport.close()

    async def call(self, op, **data):
        if self.transport:
            return await self.transport.operation(op, data)
        def request():
            body = json.dumps(data).encode()
            req = urllib.request.Request(self.url+'/channel/'+op, data=body, headers={'Content-Type': 'application/json'})
            try:
                with urllib.request.urlopen(req, timeout=55) as response:
                    result = json.load(response)
            except Exception:
                raise RuntimeError('Iris bridge unavailable; inspect its private transport log.') from None
            if not result.get('ok'):
                raise RuntimeError(result.get('error', 'Iris operation failed.'))
            return result.get('result')
        return await asyncio.to_thread(request)


async def stdio(state, binary):
    client = Client(state, binary=binary)
    try:
        await client.open()
        while line := await asyncio.to_thread(sys.stdin.readline):
            request = json.loads(line)
            try:
                result = await client.call(request['op'], **request.get('data', {}))
                response = {'id': request['id'], 'ok': True, 'result': result}
            except Exception:
                response = {'id': request.get('id'), 'ok': False, 'error': 'Iris operation failed; check channel diagnostics.'}
            print(json.dumps(response), flush=True)
    finally:
        with contextlib.suppress(Exception):
            await client.call('typing', active=False)
        await client.close()


async def setup(state, binary, name, owner, invite):
    transport = Transport(state, binary)
    await transport.open(create=True, name=name)
    try:
        return await transport.pair(owner, invite)
    finally:
        await transport.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['stdio', 'setup', 'interactive'])
    parser.add_argument('--state', required=True)
    parser.add_argument('--binary', default='iris')
    parser.add_argument('--name', default='OpenClaw')
    args = parser.parse_args()
    try:
        if args.mode == 'stdio':
            asyncio.run(stdio(args.state, args.binary))
        elif args.mode == 'setup':
            request = json.load(sys.stdin)
            print(json.dumps(asyncio.run(setup(args.state, args.binary, request['name'], request['owner'], request['invite']))))
        else:
            args.binary = ensure_iris(args.state, args.binary)
            transport = Transport(args.state, args.binary)
            if (transport.state / 'pairing.json').exists():
                transport.policy()
                print('Existing Iris identity and approved contact preserved.')
            else:
                print('Iris creates a separate agent identity. It does not need your secret key.')
                owner = owner_hex(input('Your Iris public user ID (npub): '))
                invite = getpass.getpass('Your private Iris invite link: ').strip()
                if not invite:
                    raise ValueError('A private invite is required.')
                asyncio.run(setup(args.state, args.binary, args.name, owner, invite))
                print('Iris identity created and paired.')
    except IrisInstallError as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
    except Exception:
        print('Iris channel could not start. Check CLI installation, pairing, and the private transport log.', file=sys.stderr)
        sys.exit(1)
