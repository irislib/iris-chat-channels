#!/usr/bin/env python3
"""Package exactly one committed source tree without executing package scripts."""
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]

def git(*args):
    return subprocess.check_output(['git',*args],cwd=ROOT)

def main():
    commit = git('rev-parse','HEAD').decode().strip()
    epoch = int(git('show','-s','--format=%ct',commit))
    paths = git('ls-tree','-r','--name-only',commit).decode().splitlines()
    read = lambda name: git('show',commit+':'+name)
    version = json.loads(read('package.json'))['version']
    destination = ROOT/'dist'
    destination.mkdir(exist_ok=True)
    sums = []
    for kind in ('openclaw','hermes'):
        if kind == 'openclaw':
            selected = [p for p in paths if p.startswith('openclaw/') or p in
                ('package.json','openclaw.plugin.json','secret-contract-api.mjs','hermes/transport.py','README.md','LICENSE')]
            files = {'package/'+p:read(p) for p in selected}
            source_path = 'package/SOURCE.json'
        else:
            selected = [p for p in paths if p.startswith('hermes/')]
            files = {p.removeprefix('hermes/'):read(p) for p in selected}
            files['LICENSE'] = read('LICENSE')
            source_path = 'SOURCE.json'
        files[source_path] = (json.dumps({'repository':'https://github.com/irislib/iris-chat-channels','commit':commit,'version':version},sort_keys=True)+'\n').encode()
        name = f'iris-{kind}-{version}.tgz'
        target = destination/name
        with target.open('wb') as output, gzip.GzipFile(filename='',mode='wb',fileobj=output,mtime=epoch) as compressed, tarfile.open(mode='w',fileobj=compressed) as archive:
            for path, data in sorted(files.items()):
                entry = tarfile.TarInfo(path)
                entry.size = len(data);entry.mtime = epoch;entry.mode = 0o644
                archive.addfile(entry,io.BytesIO(data))
        sums.append(hashlib.sha256(target.read_bytes()).hexdigest()+'  '+name)
        print(name)
    (destination/'SHA256SUMS').write_text('\n'.join(sums)+'\n')
    print('Source commit: '+commit)

if __name__=='__main__': main()
