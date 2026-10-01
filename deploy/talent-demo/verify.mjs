import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
const base = new URL('https://talent.muchenai.com');
const manifest = JSON.parse(readFileSync('deploy/talent-demo/manifest.json', 'utf8'));
const accounts = JSON.parse(process.env.TALENT_SMOKE_ACCOUNTS ?? '');
assert.equal(accounts.length, 2);
// ACME issuance can finish shortly after the validated Caddy restart.
for (let attempt = 0; ; attempt++) {
  try {
    const health = await fetch(new URL('/health/ready', base), {signal: AbortSignal.timeout(10000)});
    assert.equal(health.status, 200);
    assert.equal((await health.json()).release, manifest.revision);
    break;
  } catch (error) {
    if (attempt === 11) throw error;
    await new Promise(resolve => setTimeout(resolve, 5000));
  }
}
const anonymous = await fetch(new URL('/api/workspace', base));
assert.equal(anonymous.status, 401);
const request = (account, path, options = {}) => fetch(new URL(path, base), {
  signal: AbortSignal.timeout(10000), ...options, headers: {Authorization: `Basic ${Buffer.from(`${account.username}:${account.password}`).toString('base64')}`, ...options.headers},
});
for (const account of accounts) {
  const page = await request(account, '/');
  assert.equal(page.status, 200);
  const html = await page.text();
  const asset = html.match(/src="(\/assets\/[^" ]+\.js)"/);
  assert.ok(asset);
  assert.equal((await request(account, asset[1])).status, 200);
  const snapshot = await request(account, '/api/workspace');
  assert.equal(snapshot.status, 200);
  const data = await snapshot.json();
  assert.ok(data.state);
  const crossOrigin = await request(account, '/api/sandbox-role', {
    method: 'POST', headers: {Origin: 'https://untrusted.example', 'Content-Type': 'application/json'}, body: JSON.stringify({role: 'pm'}),
  });
  assert.equal(crossOrigin.status, 403);
}
const journey = await fetch('https://journey.muchenai.com/health/ready');
assert.equal((await journey.json()).release, '9a35f45053e903aa8e4d113aadbf7168d9ae9d0d');
console.log('EXTERNAL_ACCEPTANCE=PASS TLS, revision, anonymous rejection, authenticated pages/assets/workspaces, cross-origin rejection, Journey baseline');
