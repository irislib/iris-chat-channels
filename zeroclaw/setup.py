#!/usr/bin/env python3
"""Pair Iris and print the minimum ZeroClaw configuration to review and add."""
import argparse
import base64
import json
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', required=True)
    parser.add_argument('--alias', default='iris')
    args = parser.parse_args()
    if not args.alias or not all(c.isascii() and (c.isalnum() or c in '-_') for c in args.alias):
        parser.error('Use letters, numbers, hyphens, or underscores for the channel alias.')
    state = Path(args.state).expanduser().resolve()
    source = Path(__file__).resolve().parents[1] / 'hermes/transport.py'
    subprocess.run([sys.executable, str(source), 'interactive', '--state', str(state), '--name', 'ZeroClaw'], check=True)
    owner = json.loads((state / 'pairing.json').read_text())['owner_hex']
    identity = json.dumps(['iris-chat', 'channel', args.alias], separators=(',', ':')).encode()
    entry = 'zpi1_' + base64.urlsafe_b64encode(identity).decode().rstrip('=')
    print('\nMerge these sections into config.toml. Preserve your existing plugin entries and agent channels.\n')
    print(f'''[plugins]
enabled = true

[channels.plugin.{args.alias}]
package = "iris-chat"
enabled = true

[[plugins.entries]]
name = "{entry}"
egress_hosts = ["127.0.0.1"]
egress_allow_private = ["127.0.0.1"]
[plugins.entries.config]
owner = "{owner}"

[peer_groups.{args.alias}]
channel = "plugin.{args.alias}"
external_peers = ["{owner}"]
''')
    print(f'Add "plugin.{args.alias}" to the channels list of the existing agent you want to connect.')
    print('Keep the bridge running on the same machine/network namespace as ZeroClaw, then restart the daemon.')
    print('Only the paired contact is admitted. Keep normal agent permissions and signature policy.')


if __name__ == '__main__':
    main()
