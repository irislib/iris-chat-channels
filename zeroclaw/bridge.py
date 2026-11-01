#!/usr/bin/env python3
"""Run a paired Iris transport on loopback for the ZeroClaw WASM channel.

The fixed-contact API exposes no command execution, recipient selection, keys,
filesystem operations, or model access. The gateway and bridge must share the
same trusted network namespace; never publish this port from a container.
"""
import argparse
import asyncio
import importlib.util
import json
from pathlib import Path
import signal
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', required=True)
    parser.add_argument('--iris', default='iris')
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[1] / 'hermes/transport.py'
    spec = importlib.util.spec_from_file_location('iris_transport', source)
    transport = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(transport)
    client = transport.Client(args.state, binary=args.iris)
    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True).start()

    def call(op, data):
        return asyncio.run_coroutine_threadsafe(client.call(op, **data), loop).result(timeout=60)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            status = 200
            try:
                # Browser-origin requests cannot invoke the local trusted-process API.
                if self.headers.get('Origin') or self.headers.get_content_type() != 'application/json':
                    raise ValueError('Invalid request origin or type.')
                if not self.path.startswith('/channel/'):
                    raise ValueError('Invalid request.')
                self.connection.settimeout(10)
                # WASI HTTP may stream a known JSON body with HTTP/1.1 chunk framing.
                if self.headers.get('Transfer-Encoding', '').lower() == 'chunked':
                    body = bytearray()
                    while True:
                        line = self.rfile.readline(128)
                        if not line.endswith(b'\r\n'):
                            raise ValueError('Invalid chunk header.')
                        size = int(line.split(b';', 1)[0], 16)
                        if size < 0 or len(body) + size > 128000:
                            raise ValueError('Request too large.')
                        if size == 0:
                            if self.rfile.readline(128) != b'\r\n':
                                raise ValueError('Trailers are not supported.')
                            break
                        chunk = self.rfile.read(size)
                        if len(chunk) != size or self.rfile.read(2) != b'\r\n':
                            raise ValueError('Invalid chunk.')
                        body.extend(chunk)
                else:
                    size = int(self.headers.get('Content-Length', '0'))
                    if not 0 < size <= 128000:
                        raise ValueError('Invalid request size.')
                    body = self.rfile.read(size)
                value = json.loads(body)
                if not isinstance(value, dict):
                    raise ValueError('Expected an object.')
                result = {'ok': True, 'result': call(self.path.removeprefix('/channel/'), value)}
            except Exception:
                status, result = 400, {'ok': False, 'error': 'Iris operation failed. Check the paired profile.'}
            data = json.dumps(result).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = None
    try:
        health = asyncio.run_coroutine_threadsafe(client.open(), loop).result(timeout=90)
        if not health['ready']:
            raise RuntimeError('Iris is not ready.')
        server = ThreadingHTTPServer(('127.0.0.1', 8765), Handler)
        signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=server.shutdown, daemon=True).start())
        print('Iris bridge ready on loopback.', flush=True)
        server.serve_forever()
    finally:
        if server:
            server.server_close()
        try:
            call('typing', {'active': False})
        finally:
            asyncio.run_coroutine_threadsafe(client.close(), loop).result(timeout=15)
            loop.call_soon_threadsafe(loop.stop)


if __name__ == '__main__':
    main()
