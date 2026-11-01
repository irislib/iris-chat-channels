#!/usr/bin/env python3
"""Offline CLI fixture. Never connects to Iris or uses an existing profile."""
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
import time

state = Path(os.environ['IRIS_DATA_DIR'])
args = [a for a in sys.argv[1:] if a not in ('--json','--no-background-sync')]
owner = 'a'*64
state.mkdir(parents=True,exist_ok=True)
def read_messages():
    path = state/'messages.json'
    return json.loads(path.read_text()) if path.exists() else []
def result(data): print(json.dumps({'status':'ok','data':data}))

if args[:2] == ['account','create']:
    identity = state/'fixture-identity'
    if identity.exists(): raise SystemExit(2)
    identity.write_text('TEST IDENTITY; NOT A KEY')
    result({'npub':'fixture-agent'})
elif args == ['whoami']:
    if not (state/'fixture-identity').exists(): raise SystemExit(2)
    result({'public_key':'c'*64})
elif args == ['service','run']:
    pidfile = state/'fixture-service.pid'
    pidfile.write_text(str(os.getpid()))
    def stop(*_): raise SystemExit(0)
    signal.signal(signal.SIGTERM,stop)
    try:
        while True: time.sleep(1)
    finally: pidfile.unlink(missing_ok=True)
elif args == ['service','status']:
    running = False
    try:
        os.kill(int((state/'fixture-service.pid').read_text()),0)
        running = True
    except (OSError,ValueError): pass
    result({'running':running,'account_loaded':True,'network_ready':running})
elif args[:2] == ['invite','accept']:
    assert args[2]=='fixture-invite'
    result({'current_chat':{'kind':'direct','chat_id':owner}})
elif args[:2] == ['privacy','unknown-users']:
    assert args[2]=='block'
    result({})
elif args[0] == 'read':
    assert args[1]==owner
    result({'chat':{'kind':'direct','chat_id':owner},'messages':read_messages()})
elif args[0] == 'send':
    assert args[1]==owner
    messages = read_messages()
    message = {'id':hashlib.sha256(str(time.time_ns()).encode()).hexdigest(),'chat_id':owner,
               'is_outgoing':True,'body':args[2],'delivery':'sent','created_at_secs':time.time()}
    messages.append(message)
    (state/'messages.json').write_text(json.dumps(messages))
    result({'message':message})
elif args[0] in ('seen','typing'):
    assert args[1]==owner
    with (state/'fixture-events.jsonl').open('a') as f: f.write(json.dumps(args)+'\n')
    result({})
else: raise SystemExit(2)
