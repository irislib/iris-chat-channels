import test from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { normalizeOwner } from '../openclaw/identity.mjs';
import { IrisClient } from '../openclaw/client.mjs';

test('owner is a strict public ID and cannot widen to a wildcard or arbitrary target', () => {
  assert.equal(normalizeOwner('a'.repeat(64)), 'a'.repeat(64));
  for (const value of ['*','nsec1secret','npub1invalid','http://localhost',null]) assert.throws(() => normalizeOwner(value));
});
test('managed client cannot access another host service', () => {
  for (const bridgeUrl of ['http://127.0.0.1:80','http://localhost:8765','https://example.com']) assert.throws(() => new IrisClient({bridgeUrl}));
});
test('a checksum-valid npub decodes consistently with the Python transport', () => {
  // Public NIP-19 example, not an operator or agent identity.
  const npub='npub180cvv07tjdrrgpa0j7j7tmnyl2yr6yr7l8j4s3evf6u64th6gkwsyjh6w6';
  const hex=normalizeOwner(npub);
  assert.equal(hex,'3bf0c63fcb93463407af97a5e5ee64fa883d107ef9e558472c4eb9aaaefa459d');
  const python=execFileSync('python3',['-c','from hermes.transport import owner_hex; import sys; print(owner_hex(sys.argv[1]))',npub],{encoding:'utf8'}).trim();
  assert.equal(hex,python);
});
