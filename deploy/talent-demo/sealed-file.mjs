import { createCipheriv, createDecipheriv, randomBytes } from 'node:crypto';
import { readFileSync, writeFileSync } from 'node:fs';
const [mode, source, destination] = process.argv.slice(2);
const key = Buffer.from(process.env.TALENT_TRANSPORT_KEY ?? '', 'hex');
if (key.length !== 32 || !['seal', 'open'].includes(mode) || !source || !destination)
  throw new Error('Expected seal/open, input, output and a 32-byte transport key');
const input = readFileSync(source);
let result;
if (mode === 'seal') {
  const nonce = randomBytes(12);
  const cipher = createCipheriv('aes-256-gcm', key, nonce);
  const encrypted = Buffer.concat([cipher.update(input), cipher.final()]);
  result = Buffer.concat([Buffer.from('TALENT01'), nonce, cipher.getAuthTag(), encrypted]);
} else {
  if (input.length < 36 || input.subarray(0, 8).toString() !== 'TALENT01')
    throw new Error('Invalid sealed file');
  const decipher = createDecipheriv('aes-256-gcm', key, input.subarray(8, 20));
  decipher.setAuthTag(input.subarray(20, 36));
  result = Buffer.concat([decipher.update(input.subarray(36)), decipher.final()]);
}
writeFileSync(destination, result, { mode: 0o600, flag: 'wx' });
