// UI smoke test with an explicit fixture API; backend tests exercise actual files.
import { chromium } from '@playwright/test';
import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1150 } });
const errors = [];
page.on('pageerror', error => errors.push(error.message));
let docs = [];
await page.route('**/api/service/**', async route => {
  const request = route.request();
  const url = new URL(request.url());
  let body;
  if (url.pathname.endsWith('/health')) body = { model_installed: true, model_loaded: false, device: 'cpu' };
  else if (request.method() === 'POST') {
    assert.equal(url.searchParams.get('mode'), 'synthetic');
    assert.equal(url.searchParams.get('type'), '.pdf');
    assert.equal(request.postDataBuffer().toString(), '%PDF-fixture');
    docs = [{ id: '11111111-1111-4111-8111-111111111111', created: new Date().toISOString(), mode: 'synthetic', status: 'processing', counts: { private_person: 2 } }];
    body = { id: docs[0].id };
  } else if (request.method() === 'DELETE') { docs = []; body = { deleted: true }; }
  else if (url.pathname.endsWith('/preview')) body = { text: 'Alex Example 1 contacted Alex Example 1.' };
  else body = docs;
  await route.fulfill({ json: body });
});
try {
  await page.goto(process.env.BASE_URL || 'http://127.0.0.1:3000');
  await page.getByText('No files yet.').waitFor();
  await mkdir('artifacts', { recursive: true });
  await page.screenshot({ path: 'artifacts/desktop.png', fullPage: true });
  await page.getByLabel('Synthetic data', { exact: false }).check();
  await page.locator('input[type=file]').setInputFiles({ name: 'sample.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-fixture') });
  await page.getByRole('button', { name: 'Cleanse', exact: true }).click();
  await page.locator('.processing-ring').waitFor();
  assert.equal(await page.locator('.processing-ring').evaluate(el => getComputedStyle(el).animationName), 'spin');
  await page.screenshot({ path: 'artifacts/processing.png', fullPage: true });
  docs[0].status = 'complete';
  await page.getByText('2 names', { exact: true }).waitFor();
  assert.equal(await page.locator('.processing-ring').count(), 0);
  assert.equal(await page.getByText('complete', { exact: true }).count(), 0);
  await page.getByRole('button', { name: 'Preview', exact: true }).click();
  await page.getByText('Alex Example 1 contacted Alex Example 1.', { exact: true }).waitFor();
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: /Delete document/ }).click();
  await page.getByText('No files yet.').waitFor();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: 'artifacts/mobile.png', fullPage: true });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth), false);
  assert.deepEqual(errors, []);
  console.log('Browser smoke passed: upload, synthetic mode, counts, preview, deletion, mobile overflow, no runtime errors.');
} finally { await browser.close(); }
