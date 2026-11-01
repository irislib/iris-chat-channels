import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from hermes.transport import Transport, Client, owner_hex, atomic_json

OWNER = 'a'*64
OTHER = 'b'*64


class TransportContract(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name)
        self.transport = Transport(self.state)
        atomic_json(self.state/'pairing.json', {'owner_hex':OWNER, 'chat_id':OWNER})
        self.messages = []
        async def cli(*args, **kwargs):
            if args[0] == 'read':
                return {'chat':{'kind':'direct','chat_id':OWNER}, 'messages':self.messages}
            if args[0] == 'send':
                return {'message':{'id':'outgoing-id','delivery':'queued'}}
            return {}
        self.transport.cli = AsyncMock(side_effect=cli)

    def incoming(self, **changes):
        return {'id':'incoming-id','chat_id':OWNER,'is_outgoing':False,'body':'Do a task','created_at_secs':10,**changes}

    async def test_only_owner_direct_incoming_text_becomes_a_task(self):
        self.messages = [self.incoming(id='outgoing',is_outgoing=True), self.incoming(id='other',chat_id=OTHER),
            self.incoming(id='deleted',deleted_for_everyone=True), self.incoming(id='empty',body=' '), self.incoming()]
        job = await self.transport.operation('receive', {'active':[]})
        self.assertEqual(job['id'], 'incoming-id')
        self.assertFalse(job['interrupted'])
        self.assertIsNone(await self.transport.operation('receive', {'active':[job['id']]}))
        await self.transport.operation('finish', {'id':job['id']})
        restarted = Transport(self.state)
        restarted.cli = self.transport.cli
        self.assertIsNone(await restarted.operation('receive', {'active':[]}))

    async def test_running_task_is_reported_interrupted_not_replayed(self):
        self.messages = [self.incoming()]
        await self.transport.operation('receive', {'active':[]})
        restarted = Transport(self.state)
        restarted.cli = self.transport.cli
        self.assertTrue((await restarted.operation('receive', {'active':[]}))['interrupted'])

    async def test_wrong_conversation_is_rejected_before_task_storage(self):
        self.transport.cli = AsyncMock(return_value={'chat':{'kind':'group','chat_id':OWNER},'messages':[self.incoming()]})
        with self.assertRaises(ValueError):
            await self.transport.operation('receive', {'active':[]})

    async def test_no_operation_can_supply_a_recipient(self):
        for operation, payload in [('send',{'key':'k','text':'hello','recipient':OTHER}), ('typing',{'active':True,'recipient':OTHER}), ('raw',{'args':['send',OTHER,'hi']})]:
            with self.assertRaises(ValueError):
                await self.transport.operation(operation, payload)
        self.transport.cli.assert_not_called()

    async def test_duplicate_reply_sends_once_and_retains_receipt_state(self):
        first = await self.transport.operation('send', {'key':'reply:k','text':'Done'})
        second = await self.transport.operation('send', {'key':'reply:k','text':'Done'})
        self.assertEqual(first, second)
        self.assertEqual(first['delivery'], 'queued')
        self.transport.cli.assert_awaited_once_with('send',OWNER,'Done')
        with self.assertRaises(ValueError):
            await self.transport.operation('send', {'key':'reply:k','text':'Different'})

    async def test_ambiguous_send_is_recovered_from_history_without_resending(self):
        self.transport.cli = AsyncMock(side_effect=TimeoutError())
        with self.assertRaises(TimeoutError):
            await self.transport.operation('send', {'key':'reply:k','text':'Done'})
        self.transport.cli = AsyncMock(return_value={'chat':{'kind':'direct','chat_id':OWNER},'messages':[
            {'id':'accepted','is_outgoing':True,'body':'Done','created_at_secs':9999999999,'delivery':'seen'}]})
        result = await self.transport.operation('send', {'key':'reply:k','text':'Done'})
        self.assertEqual(result, {'message_id':'accepted','delivery':'seen'})
        self.assertEqual(self.transport.cli.call_args.args[0], 'read')

    async def test_unconfirmed_send_is_not_blindly_retried(self):
        cli = self.transport.cli
        self.transport.cli = AsyncMock(side_effect=TimeoutError())
        with self.assertRaises(TimeoutError):
            await self.transport.operation('send', {'key':'reply:k','text':'Done'})
        self.transport.cli = cli
        with self.assertRaisesRegex(RuntimeError,'unconfirmed'):
            await self.transport.operation('send', {'key':'reply:k','text':'Done'})
        self.assertEqual([c.args[0] for c in cli.call_args_list], ['read'])

    async def test_typing_is_throttled_and_stop_is_immediate(self):
        with patch('hermes.transport.time.monotonic',return_value=100):
            await self.transport.operation('typing', {'active':True})
            await self.transport.operation('typing', {'active':True})
            await self.transport.operation('typing', {'active':False})
        self.assertEqual([c.args for c in self.transport.cli.call_args_list], [('typing',OWNER),('typing',OWNER,'--stop')])

    async def test_repair_preserves_existing_identity_and_refuses_other_owner(self):
        original = (self.state/'pairing.json').read_bytes()
        self.assertTrue((await self.transport.pair(OWNER,'unused invite'))['already_paired'])
        with self.assertRaisesRegex(ValueError,'different'):
            await self.transport.pair(OTHER,'unused invite')
        self.transport.cli.assert_not_called()
        self.assertEqual((self.state/'pairing.json').read_bytes(),original)

    async def test_invalid_identity_does_not_replace_existing_profile(self):
        self.transport.profile.mkdir()
        marker = self.transport.profile/'existing-profile'
        marker.write_text('preserve')
        self.transport.cli = AsyncMock(side_effect=RuntimeError('damaged profile'))
        with self.assertRaises(RuntimeError):
            await self.transport.open(create=True)
        self.assertEqual(marker.read_text(),'preserve')
        self.transport.cli.assert_awaited_once_with('whoami')
        self.assertIsNone(self.transport.lock)

    async def test_one_transport_owner_per_profile(self):
        self.transport.profile.mkdir()
        (self.transport.profile/'existing').touch()
        self.transport.cli = AsyncMock(return_value={'running':True,'account_loaded':True})
        await self.transport.open()
        try:
            second = Transport(self.state)
            with self.assertRaisesRegex(RuntimeError,'already has'):
                await second.open()
        finally:
            await self.transport.close()

    def test_bridge_cannot_be_repointed_at_other_services(self):
        for url in ('http://localhost:8765','http://127.0.0.1:80','https://example.com','http://127.0.0.1:8765@evil.example'):
            with self.assertRaises(ValueError): Client(bridge_url=url)

    def test_private_state_permissions_and_strict_identity(self):
        self.assertEqual((self.state/'pairing.json').stat().st_mode & 0o777,0o600)
        for value in ('*','npub1bad','nsec1secret',OTHER.upper()):
            with self.assertRaises(ValueError): owner_hex(value)


if __name__ == '__main__':
    unittest.main()
