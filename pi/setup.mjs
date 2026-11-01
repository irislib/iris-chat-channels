#!/usr/bin/env node
import { resolve } from 'node:path';
import { homedir } from 'node:os';
import { pair } from '../common/setup.mjs';

const state = resolve(process.env.IRIS_PI_STATE_DIR ?? `${homedir()}/.local/share/iris-channels/pi`);
await pair(state, 'Pi');
console.log('Iris is paired. Set IRIS_PI_STATE_DIR to this profile when starting the Pi session you want to connect.');
console.log(state);
