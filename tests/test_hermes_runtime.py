"""Run with the real Hermes host; only Iris transport and the model reply are faked."""
import asyncio
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

try:
    from gateway.config import PlatformConfig
    from gateway.platform_registry import platform_registry, PlatformEntry
    from hermes.adapter import IrisAdapter, register
    AVAILABLE = True
except ImportError:
    AVAILABLE = False

OWNER = 'a'*64


@unittest.skipUnless(AVAILABLE, 'Run in the pinned Hermes host')
class HermesNative(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        class Context:
            def register_platform(self, **kwargs):
                platform_registry.register(PlatformEntry(**kwargs))
        register(Context())
        self.client = AsyncMock()
        self.client.open.return_value = {'owner':OWNER,'ready':True}
        self.calls = []
        self.jobs = []
        async def call(op, **data):
            self.calls.append((op,data))
            if op == 'receive': return self.jobs.pop(0) if self.jobs else None
            if op in ('send', 'approval'): return {'message_id':'sent-id','delivery':'sent'}
            return {}
        self.client.call.side_effect = call
        with patch('hermes.adapter.client_for',return_value=self.client):
            self.adapter = IrisAdapter(PlatformConfig(enabled=True,extra={'state_dir':'unused'}))

    async def asyncTearDown(self):
        await self.adapter.disconnect()

    async def wait_for(self, predicate):
        async with asyncio.timeout(10):
            while not predicate(): await asyncio.sleep(0.02)

    async def test_native_dispatch_reply_typing_and_restart_dedup_handoff(self):
        started = asyncio.Event()
        release = asyncio.Event()
        observed = []
        async def handler(event):
            observed.append(event)
            started.set()
            await release.wait()
            return 'A real gateway reply'
        self.adapter.set_message_handler(handler)
        self.jobs.append({'id':'job1','text':'Task','owner':OWNER,'created':10,'interrupted':False})
        self.assertTrue(await self.adapter.connect())
        await asyncio.wait_for(started.wait(),5)
        self.assertEqual(observed[0].source.platform.value,'iris')
        self.assertEqual(observed[0].source.user_id,OWNER)
        self.assertTrue(self.adapter._is_dm_allowed(OWNER))
        self.assertFalse(self.adapter._is_dm_allowed('b'*64))
        self.assertFalse(self.adapter._is_group_allowed(OWNER,OWNER))
        self.assertIn(('typing',{'active':True}),self.calls)
        release.set()
        await self.wait_for(lambda: any(op=='send' for op,_ in self.calls) and not self.adapter.thinking)
        sends=[data for op,data in self.calls if op=='send']
        self.assertEqual(len(sends),1)
        self.assertEqual(sends[0]['text'],'A real gateway reply')
        self.assertIn(('typing',{'active':False}),self.calls)
        self.assertIn(('finish',{'id':'job1'}),self.calls)

    async def test_two_host_requests_resolve_only_the_quoted_one(self):
        from tools.approval import list_gateway_approvals
        from tools.approval_gateway_wait import _await_gateway_decision

        self.adapter.owner = OWNER
        loop = asyncio.get_running_loop()
        async def wait_for_choice(command):
            def notify(data):
                future = asyncio.run_coroutine_threadsafe(self.adapter.send_exec_approval(
                    chat_id=OWNER, command=data['command'], session_key='iris-approval-test', description='Test'), loop)
                assert future.result(5).success
            return await asyncio.to_thread(_await_gateway_decision, 'iris-approval-test', notify,
                                           {'command': command, 'description': 'Test', 'pattern_key': command})
        first = asyncio.create_task(wait_for_choice('first'))
        second = asyncio.create_task(wait_for_choice('second'))
        try:
            await self.wait_for(lambda: len([p for op,p in self.calls if op == 'approval']) == 2)
            keys = {p['details'].splitlines()[0]: p['key'] for op,p in self.calls if op == 'approval'}
            async def reply(key, decision):
                return await self.adapter.handle_approval_reply({'id':'fixture', 'text':'reply',
                    'approval_reply':{'key':key, 'decision':decision}})
            for key, decision in ((None, 'allow-once'), (keys['first'], 'allow-always')):
                self.assertTrue(await reply(key, decision))
                self.assertEqual(len(list_gateway_approvals('iris-approval-test')), 2)
            await reply(keys['second'], 'allow-once')
            self.assertEqual((await asyncio.wait_for(second, 5))['choice'], 'once')
            await reply(keys['second'], 'allow-once')
            self.assertFalse(first.done())
            await reply(keys['first'], 'deny')
            self.assertEqual((await asyncio.wait_for(first, 5))['choice'], 'deny')
        finally:
            from tools.approval import resolve_gateway_approval
            resolve_gateway_approval('iris-approval-test', 'deny', resolve_all=True)
            await asyncio.gather(first, second, return_exceptions=True)

    async def test_failed_turn_and_shutdown_clear_typing(self):
        async def handler(event): raise ValueError('controlled failure')
        self.adapter.set_message_handler(handler)
        self.jobs.append({'id':'job2','text':'Task','owner':OWNER,'created':10,'interrupted':False})
        self.assertTrue(await self.adapter.connect())
        await self.wait_for(lambda: ('typing',{'active':False}) in self.calls)
        self.assertFalse(self.adapter.thinking)
        await self.adapter.disconnect()
        self.assertEqual(self.calls[-1],('typing',{'active':False}))

    async def test_foreign_outbound_and_interrupted_jobs_never_run_agent(self):
        handler = AsyncMock(return_value='should not run')
        self.adapter.set_message_handler(handler)
        self.jobs.append({'id':'old','text':'Task','owner':OWNER,'created':10,'interrupted':True})
        await self.adapter.connect()
        await self.wait_for(lambda: ('finish',{'id':'old'}) in self.calls)
        handler.assert_not_awaited()
        result = await self.adapter.send('b'*64,'wrong recipient')
        self.assertFalse(result.success)


@unittest.skipUnless(AVAILABLE, 'Run in the pinned Hermes host')
class HermesSetup(unittest.TestCase):
    def test_setup_installs_before_pairing_and_saves_the_selected_profile(self):
        from hermes.adapter import setup_wizard
        with tempfile.TemporaryDirectory() as temporary, \
                patch('hermes_cli.config.get_hermes_home', return_value=temporary), \
                patch('hermes_cli.config.save_env_value') as save, \
                patch('hermes.adapter.ensure_iris', return_value='/channel/bin/iris') as install, \
                patch('hermes.adapter.pair_transport', new_callable=AsyncMock, return_value={'owner': OWNER}) as pair, \
                patch('builtins.input', return_value=OWNER), \
                patch('hermes.adapter.getpass.getpass', return_value='fixture-invite'):
            setup_wizard()
            state = Path(temporary) / 'iris-channel'
            install.assert_called_once_with(state)
            pair.assert_awaited_once_with(str(state), '/channel/bin/iris', 'Hermes', OWNER, 'fixture-invite')
            self.assertEqual(save.call_args_list[-1].args, ('IRIS_CHANNEL_OWNER', OWNER))

    def test_repeat_setup_preserves_contact_and_never_pairs_again(self):
        from hermes.adapter import setup_wizard
        from hermes.transport import atomic_json
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary) / 'iris-channel'
            state.mkdir()
            atomic_json(state / 'pairing.json', {'owner_hex': OWNER, 'chat_id': OWNER})
            with patch('hermes_cli.config.get_hermes_home', return_value=temporary), \
                    patch('hermes_cli.config.save_env_value'), \
                    patch('hermes.adapter.ensure_iris', return_value='/channel/bin/iris') as install, \
                    patch('hermes.adapter.pair_transport', new_callable=AsyncMock) as pair, \
                    patch('builtins.input') as prompt:
                setup_wizard()
                install.assert_called_once_with(state)
                pair.assert_not_awaited()
                prompt.assert_not_called()


if __name__ == '__main__': unittest.main()
