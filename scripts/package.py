#!/usr/bin/env python3
"""Package exactly one committed source tree without executing package scripts."""
import base64
import csv
import datetime
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
import zipfile

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
    for kind in ('openclaw','hermes','opencode','pi','zeroclaw-bridge'):
        if kind == 'openclaw':
            selected = [p for p in paths if p.startswith('openclaw/') or p in
                ('package.json','openclaw.plugin.json','secret-contract-api.mjs','hermes/transport.py','README.md','LICENSE')]
            files = {'package/'+p:read(p) for p in selected}
            source_path = 'package/SOURCE.json'
        elif kind in ('opencode', 'pi'):
            selected = [p for p in paths if (p.startswith(kind+'/') and not p.endswith('/package.json'))
                or p.startswith('common/') or p in ('openclaw/client.mjs','hermes/transport.py','LICENSE')]
            files = {'package/'+p:read(p) for p in selected}
            manifest = json.loads(read(kind+'/package.json'))
            manifest['bin'] = {name: './'+kind+'/'+path.removeprefix('./') for name,path in manifest['bin'].items()}
            if kind == 'opencode': manifest['main'] = './opencode/index.mjs'
            else: manifest['pi']['extensions'] = ['./pi/index.mjs']
            files['package/package.json'] = (json.dumps(manifest,indent=2)+'\n').encode()
            files['package/README.md'] = read(kind+'/README.md')
            source_path = 'package/SOURCE.json'
        elif kind == 'zeroclaw-bridge':
            selected = [p for p in paths if p in ('zeroclaw/bridge.py','zeroclaw/setup.py','hermes/transport.py','LICENSE')]
            files = {p:read(p) for p in selected}
            files['README.md'] = read('zeroclaw/README.md')
            source_path = 'SOURCE.json'
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
                entry.size = len(data);entry.mtime = epoch;entry.mode = 0o755 if path.endswith('/setup.mjs') else 0o644
                archive.addfile(entry,io.BytesIO(data))
        sums.append(hashlib.sha256(target.read_bytes()).hexdigest()+'  '+name)
        print(name)
    wheel_name = f'iris_nanobot-{version}-py3-none-any.whl'
    metadata = f'iris_nanobot-{version}.dist-info'
    files = {'nanobot/channels/iris/'+p.removeprefix('nanobot/'):read(p) for p in paths if p.startswith('nanobot/') and p.endswith('.py')}
    files['nanobot/channels/iris/transport.py'] = read('hermes/transport.py')
    files[metadata+'/METADATA'] = (f"Metadata-Version: 2.3\nName: iris-nanobot\nVersion: {version}\nSummary: Iris Chat encrypted messaging channel for nanobot\nHome-page: https://irischat.org\nProject-URL: Source, https://github.com/irislib/iris-chat-channels\nLicense: MIT\nRequires-Python: >=3.11\nRequires-Dist: nanobot-ai==0.4.0\nDescription-Content-Type: text/markdown\n\n"+read('nanobot/README.md').decode()).encode()
    files[metadata+'/WHEEL'] = b'Wheel-Version: 1.0\nGenerator: iris-chat-channels\nRoot-Is-Purelib: true\nTag: py3-none-any\n'
    files[metadata+'/LICENSE'] = read('LICENSE')
    files[metadata+'/SOURCE.json'] = (json.dumps({'repository':'https://github.com/irislib/iris-chat-channels','commit':commit,'version':version},sort_keys=True)+'\n').encode()
    record = io.StringIO(); writer = csv.writer(record,lineterminator='\n')
    for path,data in sorted(files.items()):
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip('=')
        writer.writerow([path,'sha256='+digest,len(data)])
    writer.writerow([metadata+'/RECORD','',''])
    files[metadata+'/RECORD'] = record.getvalue().encode()
    timestamp = datetime.datetime.fromtimestamp(epoch,datetime.timezone.utc).timetuple()[:6]
    with zipfile.ZipFile(destination/wheel_name,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for path,data in sorted(files.items()):
            entry = zipfile.ZipInfo(path,timestamp);entry.external_attr = 0o644 << 16
            archive.writestr(entry,data)
    sums.append(hashlib.sha256((destination/wheel_name).read_bytes()).hexdigest()+'  '+wheel_name)
    print(wheel_name)
    (destination/'SHA256SUMS').write_text('\n'.join(sums)+'\n')
    print('Source commit: '+commit)

if __name__=='__main__': main()
