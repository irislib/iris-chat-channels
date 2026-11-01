"""Run with the pinned real nanobot environment and installed Iris wheel."""
import unittest
from unittest.mock import AsyncMock

try:
    from nanobot.channels.iris.runtime import IrisChannel
    from nanobot.bus.events import OutboundMessage
    from nanobot.bus.outbound_events import ProgressEvent, TurnEndEvent
    from nanobot.bus.queue import MessageBus
except ImportError:
    IrisChannel = None


@unittest.skipIf(IrisChannel is None, 'requires the pinned nanobot environment and installed plugin')
class NanobotContract(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.channel = IrisChannel({'stateDir': '/tmp/test-iris'}, MessageBus())
        self.channel.owner = 'a' * 64
        self.channel.client = AsyncMock()
        self.channel.pending = 'new-turn'

    async def test_unknown_contact_cannot_receive_or_submit(self):
        self.assertFalse(self.channel.is_allowed('b' * 64))
        with self.assertRaises(ValueError):
            await self.channel.send(OutboundMessage('iris', 'b' * 64, 'private answer'))
        self.channel.client.call.assert_not_awaited()

    async def test_progress_is_not_forwarded_as_a_final_answer(self):
        await self.channel.send(OutboundMessage('iris', 'a' * 64, 'private reasoning', event=ProgressEvent(reasoning=True)))
        self.channel.client.call.assert_not_awaited()
        self.assertEqual(self.channel.pending, 'new-turn')

    async def test_late_completion_cannot_finish_a_newer_task(self):
        await self.channel.send(OutboundMessage('iris', 'a' * 64, '', event=TurnEndEvent(), metadata={'message_id': 'old-turn'}))
        self.channel.client.call.assert_not_awaited()
        self.assertEqual(self.channel.pending, 'new-turn')

    async def test_matching_reply_finishes_and_clears_typing(self):
        await self.channel.send(OutboundMessage('iris', 'a' * 64, 'done', metadata={'message_id': 'new-turn'}))
        calls = self.channel.client.call.await_args_list
        self.assertEqual([c.args[0] for c in calls], ['send', 'finish', 'typing'])
        self.assertEqual(calls[1].kwargs, {'id': 'new-turn'})
        self.assertEqual(calls[2].kwargs, {'active': False})
        self.assertIsNone(self.channel.pending)
