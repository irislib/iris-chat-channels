"""Native Hermes channel. Model choice and agent execution stay with Hermes."""
import asyncio
import contextlib
import getpass
import hashlib
import logging
from pathlib import Path
import shutil
import uuid

from gateway.config import Platform
from gateway.platforms._shared import extra_or_secret, get_scoped_secret, seed_extra_from_env
from gateway.platforms.access_policy_mixin import OwnAccessPolicyMixin
from gateway.platforms.base import BasePlatformAdapter, SendResult
from gateway.platforms.event import MessageEvent, MessageType

from .transport import Client, owner_hex, setup as pair_transport

log = logging.getLogger(__name__)


class IrisAdapter(OwnAccessPolicyMixin, BasePlatformAdapter):
    ALLOW_ALL_ENV_PREFIX = 'IRIS_CHANNEL'

    def __init__(self, config):
        super().__init__(config, Platform('iris'))
        self.client = client_for(config)
        self.owner = None
        self.pending = {}
        self.thinking = set()
        self.receiver = None
        self._dm_policy = 'allowlist'
        self._group_policy = 'disabled'
        self._allow_from = []
        self._group_allow_from = []

    async def connect(self, *, is_reconnect=False):
        try:
            health = await self.client.open()
            self.owner = owner_hex(health['owner'])
            self._allow_from = [self.owner]
            if not health['ready']:
                raise RuntimeError('Iris is not ready.')
            self._mark_connected()
            self.receiver = asyncio.create_task(self.receive_loop())
            return True
        except Exception:
            await self.client.close()
            log.error('Iris could not connect. Run hermes gateway setup and select Iris Chat.')
            return False

    async def disconnect(self):
        self._mark_disconnected()
        for task in (self.receiver,):
            if task:
                task.cancel()
        await asyncio.gather(*(t for t in (self.receiver,) if t), return_exceptions=True)
        with contextlib.suppress(Exception):
            await self.client.call('typing', active=False)
        await self.client.close()

    async def receive_loop(self):
        while True:
            try:
                if len(self.pending) < 32:
                    job = await self.client.call('receive', active=list(self.pending))
                    if job:
                        if job['owner'] != self.owner:
                            raise ValueError('Iris contact policy changed; reconnect required.')
                        if job['interrupted']:
                            text = job.get('pending_reply') or 'My previous task was interrupted. I did not repeat it automatically. Send a new message to continue.'
                            await self.client.call('send', key='recovery:'+job['id'], text=text)
                            await self.client.call('finish', id=job['id'])
                        else:
                            self.pending[job['id']] = job
                            event = MessageEvent(text=job['text'], message_type=MessageType.TEXT,
                                message_id=job['id'], user_id=self.owner, user_name='Approved contact',
                                source=self.build_source(chat_id=self.owner, chat_type='dm',
                                    user_id=self.owner, user_name='Approved contact', message_id=job['id']))
                            await self.handle_message(event)
                            # The native gateway owns the accepted turn/queue now.
                            # This also handles inline /stop and approval replies,
                            # which intentionally have no processing-complete hook.
                            await self.client.call('finish', id=job['id'])
                            self.pending.pop(job['id'], None)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.warning('Iris receive is waiting for transport recovery; no task is replayed.')
            await asyncio.sleep(2)

    async def on_processing_start(self, event):
        self.thinking.add(event.message_id)
        with contextlib.suppress(Exception):
            await self.client.call('seen', id=event.message_id)
            await self.client.call('typing', active=True)

    async def on_processing_complete(self, event, outcome):
        # Only finish after the gateway has settled the turn and its reply.
        try:
            await self.client.call('finish', id=event.message_id)
            self.pending.pop(event.message_id, None)
        finally:
            self.thinking.discard(event.message_id)
            if not self.thinking:
                with contextlib.suppress(Exception):
                    await self.client.call('typing', active=False)

    async def send(self, chat_id, content, reply_to=None, metadata=None):
        try:
            if owner_hex(chat_id) != self.owner:
                raise ValueError('Only the approved Iris contact is allowed.')
            anchor = reply_to or next(iter(self.thinking), None) or str(uuid.uuid4())
            key = 'reply:'+anchor+':'+hashlib.sha256(content.encode()).hexdigest()
            result = await self.client.call('send', key=key, text=content)
            return SendResult(success=True, message_id=result['message_id'], raw_response=result)
        except Exception:
            return SendResult(success=False, error='Iris reply is unconfirmed; check channel diagnostics.', retryable=False)

    async def send_typing(self, chat_id, **kwargs):
        if owner_hex(chat_id) == self.owner and self.thinking:
            with contextlib.suppress(Exception):
                await self.client.call('typing', active=True)

    async def stop_typing(self, chat_id, **kwargs):
        if owner_hex(chat_id) == self.owner:
            with contextlib.suppress(Exception):
                await self.client.call('typing', active=False)

    async def get_chat_info(self, chat_id):
        if owner_hex(chat_id) != self.owner:
            raise ValueError('Only the approved Iris contact is allowed.')
        return {'name': 'Approved Iris contact', 'type': 'dm'}


def client_for(config):
    extra = getattr(config, 'extra', {}) or {}
    return Client(extra_or_secret(extra, 'state_dir', 'IRIS_CHANNEL_STATE_DIR'),
                  extra_or_secret(extra, 'bridge_url', 'IRIS_CHANNEL_BRIDGE_URL'))


def env_enablement():
    if not (get_scoped_secret('IRIS_CHANNEL_STATE_DIR', '') or get_scoped_secret('IRIS_CHANNEL_BRIDGE_URL', '')):
        return None
    return seed_extra_from_env((('IRIS_CHANNEL_STATE_DIR', 'state_dir', None),
                                ('IRIS_CHANNEL_BRIDGE_URL', 'bridge_url', None)), home_env='IRIS_CHANNEL_OWNER')


def setup_wizard():
    from hermes_cli.config import get_hermes_home, save_env_value
    state = Path(get_hermes_home()) / 'iris-channel'
    if not shutil.which('iris'):
        raise RuntimeError('Install the Iris CLI first: https://github.com/irislib/iris-chat-rs/blob/main/docs/agents.md#install')
    print('Iris creates a separate agent identity. It does not need your secret key.')
    policy = state / 'pairing.json'
    if policy.exists():
        from .transport import Transport
        owner = Transport(state).policy()
        print('Existing Iris identity and approved contact preserved.')
    else:
        owner = owner_hex(input('Your Iris public user ID (npub): '))
        invite = getpass.getpass('Your private Iris invite link: ').strip()
        if not invite:
            raise ValueError('A private invite is required for first contact.')
        result = asyncio.run(pair_transport(str(state), 'iris', 'Hermes', owner, invite))
        owner = result['owner']
    save_env_value('IRIS_CHANNEL_STATE_DIR', str(state))
    save_env_value('IRIS_CHANNEL_OWNER', owner)
    print('Iris is paired. Start or restart the Hermes gateway, then send it a message in Iris.')


async def standalone_send(config, chat_id, message, **kwargs):
    if kwargs.get('media_files'):
        return {'error': 'Iris currently supports text delivery only.'}
    client = client_for(config)
    try:
        # A running native gateway owns its local profile lock. Standalone local
        # delivery connects to the existing CLI service without owning/stopping it.
        if client.transport:
            owner = client.transport.policy()
        else:
            owner = (await client.call('health'))['owner']
        if owner_hex(chat_id) != owner:
            raise ValueError('Unapproved Iris contact.')
        result = await client.call('send', key='scheduled:'+str(uuid.uuid4()), text=message)
        return {'success': True, **result}
    except Exception:
        return {'error': 'Iris delivery unconfirmed; the gateway must be online.'}


def register(ctx):
    ctx.register_platform(name='iris', label='Iris Chat', adapter_factory=IrisAdapter,
        check_fn=lambda: bool(get_scoped_secret('IRIS_CHANNEL_BRIDGE_URL', '') or shutil.which('iris')),
        validate_config=lambda config: bool(extra_or_secret(config.extra, 'state_dir', 'IRIS_CHANNEL_STATE_DIR') or extra_or_secret(config.extra, 'bridge_url', 'IRIS_CHANNEL_BRIDGE_URL')),
        setup_fn=setup_wizard, env_enablement_fn=env_enablement,
        required_env=[], install_hint='Install iris, then run hermes gateway setup and select Iris Chat.',
        allowed_users_env='IRIS_CHANNEL_OWNER', allowlist_suppresses_pairing=True,
        cron_deliver_env_var='IRIS_CHANNEL_OWNER', standalone_sender_fn=standalone_send,
        parse_target_ref_fn=lambda value: (owner_hex(value.removeprefix('iris:')), None),
        validate_target_ref_fn=lambda value: bool(owner_hex(value)),
        max_message_length=12000, display_tier='minimal',
        platform_hint='You are replying in a private Iris Chat. Return text; attachments are not supported.',
        emoji='💬')
