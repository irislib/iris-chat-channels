"""Real gateway + installed plugin; local fake Iris and model only.

Run inside a task-owned test container with network=none. Never use a personal
OPENCLAW_STATE_DIR. The fixture proves host routing, typing, and final delivery.
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

JOB_ID = 'fixture-'+str(uuid.uuid4())
OWNER = 'a'*64
events = []
model_calls = []
claimed = False
finished = False


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_): pass
    def reply(self, value, content_type='application/json'):
        data = (json.dumps(value)+'\n').encode()
        self.send_response(200)
        self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(data)))
        self.end_headers()
        self.wfile.write(data)
    def do_GET(self):
        self.reply({'models':[{'name':'fixture-model','model':'fixture-model'}]})
    def do_POST(self):
        global claimed, finished
        data = json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))))
        if self.path.startswith('/channel/'):
            op = self.path.removeprefix('/channel/')
            events.append((op,data))
            result = {}
            if op == 'health': result = {'owner':OWNER,'ready':True,'protocol':1}
            elif op == 'receive':
                result = None
                if not claimed:
                    claimed = True
                    result = {'id':JOB_ID,'text':'Reply with NATIVE_IRIS_OK.','owner':OWNER,'created':time.time(),'interrupted':False}
            elif op == 'send': result = {'message_id':'fixture-response','delivery':'sent'}
            elif op == 'finish': finished = True
            self.reply({'ok':True,'result':result})
        elif self.path == '/api/chat':
            model_calls.append(self.path)
            time.sleep(6)
            self.reply({'model':'fixture-model','created_at':'2026-11-01T00:00:00Z',
                'message':{'role':'assistant','content':'NATIVE_IRIS_OK'},'done':True,'done_reason':'stop',
                'prompt_eval_count':10,'eval_count':4}, 'application/x-ndjson')
        elif self.path == '/api/show':
            self.reply({'capabilities':['completion','tools'],'model_info':{'general.architecture':'qwen3','qwen3.context_length':65536}})
        elif self.path == '/v1/chat/completions':
            model_calls.append(self.path)
            time.sleep(6)
            message = {'id':'fixture-completion','object':'chat.completion','model':'fixture-model',
                'choices':[{'index':0,'message':{'role':'assistant','content':'NATIVE_IRIS_OK'},'finish_reason':'stop'}],
                'usage':{'prompt_tokens':10,'completion_tokens':4,'total_tokens':14}}
            if data.get('stream'):
                chunks = [{'id':'fixture-completion','object':'chat.completion.chunk','model':'fixture-model',
                    'choices':[{'index':0,'delta':{'role':'assistant','content':'NATIVE_IRIS_OK'},'finish_reason':None}]},
                    {'id':'fixture-completion','object':'chat.completion.chunk','model':'fixture-model',
                    'choices':[{'index':0,'delta':{},'finish_reason':'stop'}]}]
                body = ''.join('data: '+json.dumps(c)+'\n\n' for c in chunks)+'data: [DONE]\n\n'
                self.send_response(200);self.send_header('Content-Type','text/event-stream')
                self.send_header('Content-Length',str(len(body.encode())));self.end_headers();self.wfile.write(body.encode())
            else: self.reply(message)
        else:
            print('Unexpected local fixture request:',self.path,flush=True)
            self.send_error(404)


def main():
    backend = sys.argv[1] if len(sys.argv)>1 else 'openclaw'
    if backend == 'hermes':
        state = Path(os.environ['HERMES_HOME'])
        assert str(state).startswith('/tmp/')
        config_path = state/'config.yaml'
        config = {'plugins':{'enabled':['iris-chat-channel'],'disabled':[]}}
        config.update({'model':{'provider':'custom','default':'fixture-model','context_length':65536,
            'base_url':'http://127.0.0.1:11435/v1','api_key':'fixture'},
            'terminal':{'backend':'local','cwd':'/tmp'},'agent':{'max_turns':4,'reasoning_effort':'none'},
            'display':{'interface':'cli'},'compression':{'enabled':False}})
        config_path.write_text(json.dumps(config))
        os.environ['IRIS_CHANNEL_BRIDGE_URL']='http://127.0.0.1:8765'
        os.environ['IRIS_CHANNEL_OWNER']=OWNER
        command = ['hermes','gateway','run']
    else:
        configure_openclaw()
        command = ['openclaw','gateway','run','--port','18791']
    servers = [ThreadingHTTPServer(('127.0.0.1',port),Handler) for port in (8765,11435)]
    for server in servers: threading.Thread(target=server.serve_forever,daemon=True).start()
    log_path = Path('/tmp/'+backend+'-native-e2e.log')
    with log_path.open('w') as log:
        gateway = subprocess.Popen(command,stdout=log,stderr=log,start_new_session=True)
    try:
        deadline = time.monotonic()+90
        while time.monotonic()<deadline and gateway.poll() is None:
            if model_calls and finished and any(op=='send' for op,_ in events) and any(op=='typing' and data['active'] is False for op,data in events): break
            time.sleep(0.3)
        sends = [data for op,data in events if op=='send']
        starts = [data for op,data in events if op=='typing' and data['active']]
        stops = [data for op,data in events if op=='typing' and not data['active']]
        print(json.dumps({'backend':backend,'model_calls':len(model_calls),'sends':len(sends),'typing_refreshes':len(starts),
                          'typing_stops':len(stops),'finished':finished,'gateway_exit':gateway.poll()}),flush=True)
        assert model_calls, 'Native gateway never called the model'
        assert len(sends)==1 and sends[0]['text']=='NATIVE_IRIS_OK', 'Reply did not use Iris channel'
        assert len(starts)>=2 and stops, 'Typing was not refreshed and cleared'
        assert finished, 'Native turn was not acknowledged'
    except BaseException:
        print(log_path.read_text()[-18000:],flush=True)
        raise
    finally:
        if gateway.poll() is None:
            os.killpg(gateway.pid,signal.SIGTERM)
            try: gateway.wait(timeout=20)
            except subprocess.TimeoutExpired:
                os.killpg(gateway.pid,signal.SIGKILL);gateway.wait()
        for server in servers: server.shutdown();server.server_close()


def configure_openclaw():
    state = Path(os.environ['OPENCLAW_STATE_DIR'])
    if not str(state).startswith('/tmp/'):
        raise SystemExit('This test requires a temporary OpenClaw profile.')
    config_path = state/'openclaw.json'
    config = json.loads(config_path.read_text())
    config.update({
      'models':{'providers':{'ollama':{'baseUrl':'http://127.0.0.1:11435','api':'ollama','apiKey':'fixture',
        'models':[{'id':'fixture-model','name':'Fixture','input':['text'],'contextWindow':65536,'maxTokens':4096,
                   'cost':{'input':0,'output':0,'cacheRead':0,'cacheWrite':0}}]}}},
      'agents':{'defaults':{'model':{'primary':'ollama/fixture-model'},'workspace':'/tmp/iris-e2e-workspace',
        'skipBootstrap':True,'heartbeat':{'every':'0m'}}},
      'channels':{'iris':{'enabled':True,'owner':OWNER,'bridgeUrl':'http://127.0.0.1:8765'}},
      'gateway':{'mode':'local','auth':{'mode':'none'},'bind':'loopback'},
      'memory':{'search':{'enabled':False}},'update':{'checkOnStart':False},
    })
    config_path.write_text(json.dumps(config))


if __name__=='__main__': main()
