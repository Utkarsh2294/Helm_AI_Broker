import { test, expect } from '@playwright/test';
import { createRequire } from 'node:module';
import { writeFile } from 'node:fs/promises';
const require = createRequire(import.meta.url);
const reports = [];
test.use({ bypassCSP: true });

async function login(page) {
  await page.goto('/login');
  await page.getByLabel('Email address').fill('broker@helm.demo');
  await page.getByLabel('Password', { exact: true }).fill('HelmDemo!2026');
  await page.getByRole('button', { name: 'Sign in to your workspace' }).click();
  await expect(page.getByRole('button', { name: 'Start automatic demo' })).toBeVisible();
}
async function scan(page, screen) {
  await page.addScriptTag({ path: require.resolve('axe-core/axe.min.js') });
  const violations = await page.evaluate(async () =>
    (
      await window.axe.run(document, {
        runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'] },
      })
    ).violations.map((value) => ({
      id: value.id,
      targets: value.nodes.map((node) => node.target),
    })),
  );
  reports.push({ screen, violations });
  expect(violations).toEqual([]);
}
test.afterAll(async () => {
  await writeFile(
    new URL('../../../.runtime/qa/assistant-axe.json', import.meta.url),
    JSON.stringify(reports, null, 2),
  );
});

test('workspace assistant streams grounded answers, parses files and opens from the keyboard', async ({
  page,
}) => {
  await page.addInitScript(() => {
    window.SpeechRecognition = class {
      start() {
        queueMicrotask(() => {
          this.onresult({ results: [[{ transcript: 'Show blocked cases' }]] });
          this.onend();
        });
      }
      stop() {
        this.onend();
      }
      abort() {}
    };
  });
  await login(page);
  await page.keyboard.press('Control+k');
  const dock = page.getByRole('complementary', { name: 'Pinned assistant panel' });
  await expect(dock).toBeVisible();
  await dock.getByRole('button', { name: 'Voice input', exact: true }).click();
  await expect(dock.getByLabel('Ask about your workspace')).toHaveValue('Show blocked cases');
  await expect(dock.locator('.assistant-message')).toHaveCount(0);
  await dock.getByRole('button', { name: 'Summarise my workspace', exact: true }).click();
  await expect(dock.locator('.assistant-message.assistant')).toContainText('visible workspace');
  await expect(dock.locator('.assistant-stamp')).toContainText('helm-local-evidence-v2');
  await dock.getByRole('button', { name: 'History', exact: true }).click();
  await dock.getByLabel('Search your last 20 queries in the workspace').fill('Summarise');
  await expect(dock.locator('.assistant-history')).toContainText('Summarise my workspace');
  await dock.locator('input[type=file]').setInputFiles({
    name: 'comparison.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from('Provider,Annual premium\nNorthgate,1200'),
  });
  await expect(dock.getByRole('status')).toContainText('Received and parsed comparison.csv');
  await dock.getByLabel('Ask about your workspace').fill('What is in this document?');
  await dock.getByRole('button', { name: 'Send question' }).click();
  await expect(dock.locator('.assistant-message.assistant').last()).toContainText(
    'Northgate | 1200',
  );
  await expect(dock.getByRole('region', { name: 'Suggested follow-up questions' })).toHaveCount(0);
  await scan(page, 'workspace assistant desktop with history and file');
  const downloaded = page.waitForEvent('download');
  await dock.getByRole('button', { name: 'DOCX', exact: true }).click();
  expect((await downloaded).suggestedFilename()).toBe('helm-assistant.docx');
  await page.setViewportSize({ width: 390, height: 844 });
  await scan(page, 'workspace assistant mobile');
  expect(
    await dock.evaluate((element) => element.scrollWidth <= element.clientWidth + 1),
  ).toBeTruthy();
  await page.screenshot({ path: '.runtime/qa/assistant-workspace-mobile.png', fullPage: true });
  await page.keyboard.press('Escape');
  await expect(dock).toHaveCount(0);
});

test('case assistant saves snapshots and shares an authenticated read-only compliance link', async ({
  page,
}) => {
  test.setTimeout(90000);
  await login(page);
  await page.getByRole('button', { name: 'Start automatic demo' }).click();
  const panel = page.getByRole('dialog', { name: 'Case workspace' });
  await expect(panel.getByRole('heading', { name: 'Choose and rank three policies' })).toBeVisible({
    timeout: 30000,
  });
  await panel.getByRole('button', { name: 'Case assistant', exact: true }).click();
  const assistant = panel.locator('.case-assistant');
  await assistant.getByRole('button', { name: 'Why this ranking?', exact: true }).click();
  await expect(assistant.locator('.assistant-message.assistant')).toContainText('TOPSIS');
  await expect(assistant.getByRole('table')).toBeVisible();
  await assistant.getByRole('button', { name: 'Save to evidence', exact: true }).click();
  await expect(
    assistant.getByRole('button', { name: 'Saved to evidence', exact: true }),
  ).toBeDisabled();
  await expect(assistant.getByRole('button', { name: 'Evidence (1)', exact: true })).toBeVisible();
  await assistant.getByRole('button', { name: 'Share for compliance', exact: true }).click();
  const reviewLink = await assistant.getByLabel('Read-only compliance review link').inputValue();
  expect(reviewLink).toContain('/assistant-review/');
  await scan(page, 'case assistant desktop');
  await page.screenshot({ path: '.runtime/qa/assistant-case-desktop.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await scan(page, 'case assistant mobile');
  expect(
    await panel.evaluate((element) => element.scrollWidth <= element.clientWidth + 1),
  ).toBeTruthy();
  await page.screenshot({ path: '.runtime/qa/assistant-case-mobile.png', fullPage: true });
  await assistant.getByRole('button', { name: 'Pin panel', exact: true }).click();
  const dock = page.getByRole('complementary', { name: 'Pinned assistant panel' });
  await expect(dock).toBeVisible();
  await dock.getByLabel('Ask about this case').fill('What should I do next?');
  await dock.getByRole('button', { name: 'Send question' }).click();
  await expect(dock.locator('.assistant-message.assistant')).toContainText('Choose three policies');
  await page.keyboard.press('Escape');
  await expect(panel).toBeVisible();
  await page.goto(reviewLink);
  await expect(page.getByRole('alert')).toContainText('compliance officer');
});
