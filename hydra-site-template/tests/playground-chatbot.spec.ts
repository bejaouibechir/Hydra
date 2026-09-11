import { expect, test } from 'playwright/test';
import { existsSync } from 'node:fs';
import { resolve } from 'node:path';

const distRoot = resolve(process.cwd(), 'dist');
const mockupRoot = resolve(process.cwd(), '..', 'documentations', 'mockups');

test.beforeEach(async ({ page }) => {
  await page.route('http://hydra.local/**', async (route) => {
    const url = new URL(route.request().url());
    const pathname = decodeURIComponent(url.pathname);
    let target = pathname.startsWith('/mockup/')
      ? resolve(mockupRoot, `.${pathname.slice('/mockup'.length)}`)
      : resolve(distRoot, `.${pathname}`);
    if (target.endsWith('playground')) target = resolve(target, 'index.html');
    if (target.endsWith('playground\\')) target = resolve(target, 'index.html');
    if (!existsSync(target) && !target.includes('.')) target = resolve(target, 'index.html');
    if (!existsSync(target)) return route.fulfill({ status: 404, body: 'Not found' });
    return route.fulfill({ status: 200, path: target });
  });
});

test('uses the local engine, progressive hints, and the current editor context', async ({ page }) => {
  const requestedUrls: string[] = [];
  page.on('request', (request) => requestedUrls.push(request.url()));

  await page.goto('/playground/');
  await page.getByRole('button', { name: 'Ask me :)' }).click();
  await expect(page.getByText('No LLM or network request is used.')).toBeVisible();

  await page.locator('#chatLevel').selectOption('hint_1');
  await page.getByLabel('Question for Ask Hydra').fill('How do I filter paid orders?');
  await page.getByRole('button', { name: 'Send' }).click();
  await expect(page.getByText('Write the condition against exact input column names.')).toBeVisible();

  await page.getByRole('button', { name: 'Show another hint' }).click();
  await expect(page.getByText(/Combine conditions with and/u)).toBeVisible();
  await page.getByRole('button', { name: 'Show the solution' }).click();
  await expect(page.getByText(/Load the matched example/u)).toBeVisible();

  await page.locator('#fTransform').fill('transformations:\n  steps:\n    - filter:\n        expr: ammount > 100');
  await page.locator('#chatLevel').selectOption('explanation');
  await page.getByLabel('Question for Ask Hydra').fill('Why does this transformation fail?');
  await page.getByRole('button', { name: 'Send' }).click();
  await expect(page.getByRole('link', { name: 'filter guide' }).last()).toBeVisible();

  expect(requestedUrls.every((url) => url.startsWith('http://hydra.local/'))).toBe(true);
});

test('warns about a secret without exposing it in the response', async ({ page }) => {
  await page.goto('/playground/');
  await page.getByRole('button', { name: 'Ask me :)' }).click();
  await page.getByLabel('Question for Ask Hydra').fill('password: super-secret-password');
  await page.getByRole('button', { name: 'Send' }).click();
  await expect(page.getByText(/Remove it before continuing/u)).toBeVisible();
  await expect(page.locator('.msg.bot.warning')).toBeVisible();
});

test('remains usable with keyboard navigation on a mobile viewport', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/playground/');
  const launcher = page.getByRole('button', { name: 'Ask me :)' });
  await launcher.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('dialog', { name: 'Ask Hydra · DSL assistant' })).toBeVisible();
  await page.getByLabel('Question for Ask Hydra').fill('How does select work?');
  await page.keyboard.press('Enter');
  await expect(page.getByText(/select keeps only the columns/u)).toBeVisible();
  await page.getByRole('button', { name: 'Close Ask Hydra' }).click();
  await expect(launcher).toBeFocused();
});

test('runs the real deterministic engine in the standalone mockup', async ({ page }) => {
  await page.goto('/mockup/playground.html');
  await page.getByRole('button', { name: 'Ask me :)' }).click();
  await page.getByLabel('Question for Ask Hydra').fill('Can I use derive in Hydra DSL?');
  await page.getByRole('button', { name: 'Send' }).click();
  await expect(page.getByText('Hydra DSL 1.1 uses calculate, not derive. I can help you use a supported Hydra DSL construct instead.')).toBeVisible();
  await expect(page.getByText(/this mock gives canned answers/u)).toHaveCount(0);

  await page.getByLabel('Question for Ask Hydra').fill('What is the weather tomorrow?');
  await page.getByRole('button', { name: 'Send' }).click();
  await expect(page.getByText(/outside Hydra DSL learning/u)).toBeVisible();
});
