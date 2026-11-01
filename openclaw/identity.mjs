export function normalizeOwner(value) {
  value = String(value ?? '').trim().replace(/^iris:/, '');
  if (/^[0-9a-f]{64}$/.test(value)) return value;
  if (!/^npub1[023456789acdefghjklmnpqrstuvwxyz]{58}$/.test(value)) throw new Error('Expected an Iris public user ID.');
  const chars = 'qpzry9x8gf2tvdw0s3jn54khce6mua7l';
  const data = [...value.slice(5)].map(c => chars.indexOf(c));
  const hrp = [...'npub'].map(c => c.charCodeAt(0) >> 5).concat(0, [...'npub'].map(c => c.charCodeAt(0) & 31));
  let chk = 1;
  for (const v of [...hrp, ...data]) {
    const top = chk >>> 25;
    chk = ((chk & 0x1ffffff) << 5) ^ v;
    [0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3].forEach((g, i) => { if ((top >>> i) & 1) chk ^= g; });
  }
  if (chk !== 1) throw new Error('Invalid Iris public user ID checksum.');
  let acc = 0, bits = 0; const bytes = [];
  for (const v of data.slice(0, -6)) {
    acc = (acc << 5) | v; bits += 5;
    if (bits >= 8) { bits -= 8; bytes.push((acc >>> bits) & 255); }
  }
  if (bytes.length !== 32 || (acc & ((1 << bits) - 1))) throw new Error('Invalid Iris user ID.');
  return Buffer.from(bytes).toString('hex');
}

export function maybeOwner(value) {
  try { return normalizeOwner(value); } catch { return null; }
}
