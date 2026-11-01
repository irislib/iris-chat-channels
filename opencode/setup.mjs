#!/usr/bin/env node
import { resolve } from 'node:path';
import { homedir } from 'node:os';
import { pair, readJson, writeJson } from '../common/setup.mjs';

const directory = resolve(process.argv[2] ?? process.cwd());
const state = resolve(process.env.IRIS_OPENCODE_STATE_DIR ?? `${homedir()}/.local/share/iris-channels/opencode`);
const existing = await readJson(`${state}/opencode.json`);
if (existing && resolve(existing.directory) !== directory) throw new Error('This Iris profile belongs to another project. Select a new IRIS_OPENCODE_STATE_DIR.');
await pair(state, 'OpenCode');
await writeJson(`${state}/opencode.json`, { ...existing, enabled: true, directory });
console.log('Iris is paired to this project. Merge this into its opencode.json, then start OpenCode in that directory:');
console.log(JSON.stringify({ plugin: [new URL('./index.mjs', import.meta.url).href] }, null, 2));
