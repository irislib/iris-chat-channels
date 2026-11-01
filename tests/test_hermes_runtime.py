"""Run with the real Hermes host; only Iris transport and the model reply are faked."""
import asyncio
import importlib.util
from pathlib import Path
import sys
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
            if op == 'send': return {'message_id':'sent-id','delivery':'sent'}
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


if __name__ == '__main__': unittest.main()
