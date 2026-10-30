import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createServer } from 'node:http';
import { once } from 'node:events';
import { createWebServer } from '../server.mjs';

test('built web uses per-response script nonces, safe routing and a transparent API proxy', async () => {
  const root = await mkdtemp(join(tmpdir(), 'helm-web-'));
  await mkdir(join(root, 'assets'));
  await writeFile(
    join(root, 'index.html'),
    '<html><script type="module" src="/assets/app.js"></script></html>',
  );
  await writeFile(join(root, 'assets/app.js'), 'export const demo = true;');
  const api = createServer((req, res) => {
    res.setHeader('Set-Cookie', 'demo=session; HttpOnly');
    res.setHeader('Content-Type', 'application/json');
    res.end(JSON.stringify({ path: req.url, csrf: req.headers['x-csrf-token'] }));
  });
  api.listen(0, '127.0.0.1');
  await once(api, 'listening');
  const server = createWebServer({
    dist: root,
    apiProxy: `http://127.0.0.1:${api.address().port}`,
    secure: true,
  });
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  const base = `http://127.0.0.1:${server.address().port}`;
  try {
    const first = await fetch(base + '/queue'),
      html = await first.text();
    const nonce = html.match(/nonce="([^"]+)"/)[1];
    assert.ok(
      first.headers.get('content-security-policy').includes(`'nonce-${nonce}' 'strict-dynamic'`),
    );
    assert.equal(first.headers.get('referrer-policy'), 'no-referrer');
    assert.ok(first.headers.get('strict-transport-security').includes('preload'));
    assert.notEqual(
      (await (await fetch(base + '/case/fictional')).text()).match(/nonce="([^"]+)"/)[1],
      nonce,
    );
    assert.equal((await fetch(base + '/.env')).status, 404);
    assert.equal((await fetch(base + '/assets/missing.js')).status, 404);
    assert.equal((await fetch(base + '/queue', { method: 'POST' })).status, 405);
    assert.equal(
      (await fetch(base + '/assets/app.js')).headers.get('cache-control'),
      'public, max-age=31536000, immutable',
    );
    const proxied = await fetch(base + '/api/v1/check?after=1', {
      headers: { 'X-CSRF-Token': 'fixture-token' },
    });
    assert.ok(proxied.headers.get('set-cookie').includes('HttpOnly'));
    assert.deepEqual(await proxied.json(), {
      path: '/api/v1/check?after=1',
      csrf: 'fixture-token',
    });
  } finally {
    await Promise.all([
      new Promise((resolve) => server.close(resolve)),
      new Promise((resolve) => api.close(resolve)),
    ]);
    // Only remove the newly-created, isolated test directory.
    assert.ok(root.startsWith(join(tmpdir(), 'helm-web-')));
    await rm(root, { recursive: true });
  }
});
