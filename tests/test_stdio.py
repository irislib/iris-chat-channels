"""Exercise the packaged child-process transport and identity lifecycle offline."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from hermes.transport import ensure_iris

ROOT = Path(__file__).resolve().parents[1]


class StdioContract(unittest.TestCase):
    def test_first_setup_receive_reply_and_repeat_setup_preserve_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            args = [sys.executable,str(ROOT/'hermes/transport.py')]
            # Setup remembers the CLI outside PATH; fresh gateway processes must
            # use that saved location without downloading or receiving --binary.
            ensure_iris(state, str(ROOT/'tests/fake_iris.py'))
            options = ['--state',tmp]
            request = {'owner':'a'*64,'invite':'fixture-invite','name':'Fixture agent'}
            first = subprocess.run([*args,'setup',*options],input=json.dumps(request),capture_output=True,text=True,timeout=20,check=True)
            self.assertFalse(json.loads(first.stdout)['already_paired'])
            identity = (state/'profile/fixture-identity').read_bytes()
            (state/'profile/messages.json').write_text(json.dumps([{'id':'incoming','chat_id':'a'*64,'is_outgoing':False,'body':'Test task','created_at_secs':10}]))
            process = subprocess.Popen([*args,'stdio',*options],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            def call(op, data={}):
                process.stdin.write(json.dumps({'id':1,'op':op,'data':data})+'\n');process.stdin.flush()
                reply = json.loads(process.stdout.readline())
                self.assertTrue(reply['ok'],reply)
                return reply['result']
            try:
                self.assertTrue(call('health')['ready'])
                job = call('receive',{'active':[]})
                self.assertEqual(job['id'],'incoming')
                call('seen',{'id':job['id']})
                call('typing',{'active':True})
                receipt = call('send',{'key':'test-reply','text':'Test reply'})
                self.assertEqual(receipt['delivery'],'sent')
                call('finish',{'id':job['id']})
                call('typing',{'active':False})
            finally:
                process.stdin.close()
                process.wait(timeout=15)
                process.stdout.close();process.stderr.close()
            self.assertEqual(process.returncode,0)
            self.assertFalse((state/'profile/fixture-service.pid').exists())
            repeat = subprocess.run([*args,'setup',*options],input=json.dumps(request),capture_output=True,text=True,timeout=20,check=True)
            self.assertTrue(json.loads(repeat.stdout)['already_paired'])
            self.assertEqual((state/'profile/fixture-identity').read_bytes(),identity)
            self.assertEqual(len(json.loads((state/'profile/messages.json').read_text())),2)


if __name__=='__main__': unittest.main()
