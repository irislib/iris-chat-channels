import test from 'node:test';
import assert from 'node:assert/strict';
import { IrisChannel } from '../common/channel.mjs';

function channel(handle) {
  const events = [];
  const instance = new IrisChannel({ stateDir: '/unused' }, { handle });
  instance.client = { call: async (op, data) => { events.push([op, data]); return {}; } };
  const job = { id: 'turn-1', owner: 'a'.repeat(64), text: 'read a file' };
  instance.pending.set(job.id, job);
  return { instance, events, job };
}

test('a failed host task remains claimed and stops typing without replay', async () => {
  let runs = 0;
  const { instance, events, job } = channel(async () => { runs++; throw new Error('host failed'); });
  await instance.process(job);
  assert.equal(runs, 1);
  assert.equal(instance.pending.has(job.id), true);
  assert.deepEqual(events.map(([op]) => op), ['seen', 'typing', 'typing']);
  assert.equal(events.at(-1)[1].active, false);
});

test('a completed task sends one reply then acknowledges it and stops typing', async () => {
  const { instance, events, job } = channel(async () => 'done');
  await instance.process(job);
  assert.deepEqual(events.map(([op]) => op), ['seen', 'typing', 'send', 'finish', 'typing']);
  assert.equal(events[2][1].text, 'done');
  assert.equal(events.at(-1)[1].active, false);
  assert.equal(instance.pending.has(job.id), false);
});

test('shutdown prevents a late response from leaking into a reopened session', async () => {
  const { instance, events, job } = channel(async () => { instance.stopped = true; return 'late'; });
  await instance.process(job);
  assert.equal(events.some(([op]) => op === 'send'), false);
  assert.equal(instance.pending.has(job.id), true);
});
