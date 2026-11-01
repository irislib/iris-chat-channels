#!/usr/bin/env python3
"""Test-only passthrough: record typing outcome, never identities or chat text."""
import json
import os
import subprocess
import sys

binary = '/usr/local/bin/iris'
if 'typing' not in sys.argv[1:]:
    os.execv(binary, [binary, *sys.argv[1:]])
result = subprocess.run([binary, *sys.argv[1:]], check=False)
with open(os.environ['IRIS_TEST_AUDIT'], 'a') as log:
    log.write(json.dumps({'active': '--stop' not in sys.argv[1:], 'exit': result.returncode}) + '\n')
raise SystemExit(result.returncode)
