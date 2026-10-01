// Isolated setup UI fixture. No real realm, identity, licensing or enclave calls.
import { chromium, expect } from '@playwright/test';
import { createServer as createViteServer } from 'vite';
import react from '@vitejs/plugin-react';
import { createServer } from 'node:http';
import { resolve } from 'node:path';
import assert from 'node:assert/strict';

const fixtureId = resolve('__setup_fixture__.tsx');
const vite = await createViteServer({ configFile: false, cacheDir: 'node_modules/.vite-browser-setup', appType: 'custom',
  plugins: [react(), { name: 'setup-fixture', resolveId: id => id === '/__setup_fixture__.tsx' ? fixtureId : undefined,
    load: id => id === fixtureId ? `
      import { createRoot } from 'react-dom/client';
      import { TideSetup } from '/src/TideSetup.tsx';
      import '/src/globals.css';
      createRoot(document.getElementById('root')).render(<main className="history-information"><TideSetup identity={{status:'unavailable'}} provider={{}}/></main>);
    ` : undefined }], server: { middlewareMode: true, hmr: false } });
const server = createServer(async (req, res) => {
  if (req.url === '/') { const html = await vite.transformIndexHtml('/', '<html><body><div id="root"></div><script type="module" src="/__setup_fixture__.tsx"></script></body></html>'); res.writeHead(200, { 'Content-Type': 'text/html' }); res.end(html); }
  else vite.middlewares(req, res);
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1100, height: 900 } });
const base = `http://127.0.0.1:${server.address().port}`;
let unlocked = false, exchanges = 0, starts = 0, resumes = 0, busy = false;
let holdCheck = false, releaseCheck, links = 0;
let progress = { stage: 'details', completed: [] };
const errors = []; page.on('pageerror', e => errors.push(e.message));
await page.route('**/api/service/tide/**', async route => {
  const request = route.request(), path = new URL(request.url()).pathname;
  if (path.endsWith('/status')) return route.fulfill({ json: { configured: false, reachable: true, url: 'http://localhost:8080' } });
  if (path.endsWith('/session')) return route.fulfill({ json: unlocked ? { unlocked, csrf: 'fixture-csrf', busy, progress } : { unlocked } });
  if (path.endsWith('/exchange')) {
    assert.equal(request.postDataJSON().token, 'fixture-private-link'); exchanges++; unlocked = true;
    return route.fulfill({ json: { csrf: 'fixture-csrf' } });
  }
  assert.equal(request.headers()['x-setup-csrf'], 'fixture-csrf');
  if (path.endsWith('/begin')) {
    starts++; assert.equal(request.postDataJSON().accept_terms, true);
    assert.equal(request.postDataJSON().email, 'owner@example.test');
    assert.equal(request.postDataJSON().realm, 'redacted-demo');
    assert.equal('password' in request.postDataJSON(), false);
    progress = { stage: 'configure', realm: 'redacted-demo', completed: ['details', 'realm', 'license'], error: 'Connection interrupted. Retry to resume.' };
    return route.fulfill({ json: { started: true } });
  }
  if (path.endsWith('/continue')) {
    resumes++;
    if (holdCheck) await new Promise(resolve => { releaseCheck = resolve; });
    return route.fulfill({ json: { waiting: true } });
  }
  if (path.endsWith('/link')) {
    assert.equal(holdCheck, false, 'Account linking must wait for the pending automatic check.');
    links++;
    return route.fulfill({ json: { url: base + '/linked' } });
  }
  throw new Error('Unexpected fixture request: ' + path);
});
try {
  await page.goto(base, { timeout: 60000 });
  await expect(page.getByText('Start here', { exact: true })).toBeVisible();
  await expect(page.getByLabel('Setup code', { exact: true })).toHaveCount(0);
  await page.goto(base + '/#setup=fixture-private-link');
  await expect(page.getByLabel('Realm name', { exact: true })).toBeVisible();
  assert.equal(new URL(page.url()).hash, '', 'The setup capability must immediately leave the address bar.');
  await expect(page.getByLabel('Local owner password')).toHaveCount(0);
  await page.getByLabel('Realm name', { exact: true }).fill('redacted-demo');
  await page.getByLabel('Email for Tide licensing').fill('owner@example.test');
  await expect(page.getByRole('button', { name: 'Enable secure history' })).toBeDisabled();
  await page.getByLabel(/I accept/).check();
  await page.getByRole('button', { name: 'Enable secure history' }).click();
  await expect(page.getByRole('alert')).toContainText('Connection interrupted');
  await page.getByRole('button', { name: 'Retry this step' }).click();
  assert.equal(starts, 1); assert.equal(resumes, 1);
  await page.reload({ timeout: 60000 });
  await expect(page.getByRole('heading', { name: 'Prepare secure history', exact: true })).toBeVisible();
  assert.equal(exchanges, 1, 'Refresh resumes the same owner session.');
  progress = { stage: 'link', realm: 'redacted-demo', completed: ['details', 'realm', 'license', 'configure'] };
  holdCheck = true;
  await page.reload({ timeout: 60000 });
  await expect(page.getByRole('button', { name: 'Connect my Tide account' })).toBeVisible();
  await expect.poll(() => resumes).toBeGreaterThan(1);
  await expect.poll(() => typeof releaseCheck).toBe('function');
  const popupOpened = page.waitForEvent('popup');
  await page.getByRole('button', { name: 'Connect my Tide account' }).click();
  const popup = await popupOpened;
  await expect(page.getByRole('button', { name: 'Connect my Tide account' })).toBeDisabled();
  assert.equal(links, 0, 'The click queues behind the automatic check.');
  holdCheck = false; releaseCheck();
  await expect.poll(() => links).toBe(1);
  await popup.close();
  await expect(page.getByRole('link', { name: /console/i })).toHaveCount(0);
  progress = { stage: 'admin', completed: ['details', 'realm', 'license', 'configure', 'link'], pending: [{ id: 'request-1', actionType: 'GRANT_ROLES', entityType: 'USER' }] };
  await page.reload({ timeout: 60000 });
  await expect(page.getByText('1 change needs your approval.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Review and approve with Tide' })).toBeVisible();
  await page.screenshot({ path: '/tmp/redacted-embedded-setup.png', fullPage: true });
  unlocked = false;
  await page.reload({ timeout: 60000 });
  await expect(page.getByText('Start here', { exact: true })).toBeVisible();
  progress = { stage: 'link', realm: 'redacted-demo', completed: ['details', 'realm', 'license', 'configure'] };
  await page.goto(base + '/#setup=fixture-private-link');
  await expect(page.getByRole('heading', { name: 'Connect your Tide account', exact: true })).toBeVisible();
  await expect(page.locator('.setup-checklist li.done')).toHaveCount(4);
  await expect(page.locator('.setup-checklist [aria-current="step"]')).toHaveText('5Connect your Tide account');
  await expect(page.getByLabel('Realm name', { exact: true })).toHaveCount(0);
  assert.equal(exchanges, 2, 'A fresh link in an existing tab restores the saved session.');
  assert.equal(starts, 1, 'Resuming must not repeat realm creation or terms acceptance.');
  assert.equal(new URL(page.url()).hash, '');
  assert.deepEqual(errors, []);
  console.log('Embedded setup: private link removal, no code/password form, consent gate, saved progress, automatic link checks, inline approvals and expiry passed.');
} finally { await browser.close(); await new Promise(resolve => server.close(resolve)); await vite.close(); }
