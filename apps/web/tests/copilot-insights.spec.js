import { test, expect } from '@playwright/test';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
test.use({ bypassCSP: true });

async function login(page) {
  await page.goto('/login');
  await page.getByLabel('Email address').fill('broker@helm.demo');
  await page.getByLabel('Password', { exact: true }).fill('HelmDemo!2026');
  await page.getByRole('button', { name: 'Sign in to your workspace' }).click();
  await expect(page.getByRole('button', { name: 'Start automatic demo' })).toBeVisible();
}
async function scan(page) {
  await page.addScriptTag({ path: require.resolve('axe-core/axe.min.js') });
  const errors = await page.evaluate(async () =>
    (
      await window.axe.run(document, {
        runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'] },
      })
    ).violations.map((row) => ({ id: row.id, targets: row.nodes.map((node) => node.target) })),
  );
  expect(errors).toEqual([]);
}

test('priority banner, scoped task rail, live notification inbox and filtered insights', async ({
  page,
}) => {
  test.setTimeout(180000);
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await login(page);
  await expect(page.getByRole('region', { name: 'Your login priorities' })).toBeVisible();
  await page.getByRole('button', { name: 'Review priority queue' }).click();
  await expect(page).toHaveURL(/\/priority-queue$/);
  await expect(page.getByRole('heading', { name: 'Priority queue', exact: true })).toBeVisible();
  // Create a fresh fictional case while the SSE subscriber is mounted.
  const csrf = (await page.context().cookies()).find((cookie) => cookie.name === 'helm_csrf').value;
  const created = await page.request.post('/api/v1/demo/journeys', {
    headers: { 'X-CSRF-Token': csrf },
  });
  expect(created.ok()).toBeTruthy();
  const item = await created.json();
  await page.getByRole('button', { name: /Tasks / }).click();
  const rail = page.getByRole('complementary', { name: 'Task copilot' });
  await expect(rail).toBeVisible();
  await scan(page);
  await rail.getByRole('button', { name: 'Close task copilot' }).click();
  await page.getByRole('button', { name: /Notifications/ }).click();
  await page.getByRole('menuitem', { name: /Open full inbox/ }).click();
  await expect(page).toHaveURL(/notifications/);
  await expect(page.getByRole('heading', { name: 'Your notifications' })).toBeVisible();
  await expect(
    page.locator('.notification-row').filter({ hasText: item.name }).first(),
  ).toBeVisible();
  await page.locator('.notification-row').filter({ hasText: item.name }).first().click();
  await expect(page).toHaveURL(new RegExp(`/case/${item.id}`));
  const panel = page.getByRole('dialog', { name: 'Case workspace' });
  await expect(panel).toBeVisible();
  await expect(page.getByRole('complementary', { name: 'Pinned assistant panel' })).toHaveCount(0);
  await expect(panel.getByRole('heading', { name: 'Choose and rank three policies' })).toBeVisible({
    timeout: 60000,
  });
  await panel.getByRole('button', { name: /Tasks / }).click();
  await rail.getByRole('checkbox', { name: 'Only this case' }).check();
  await expect(rail.locator('.task-card')).toHaveCount(1);
  await expect(rail).toContainText('Choose and rank three policies');
  await rail.getByRole('button', { name: 'Why this matters' }).click();
  await expect(rail.getByRole('region', { name: 'Why this task matters' })).toContainText('select');
  await rail.getByRole('button', { name: 'Open task' }).click();
  await expect(page).toHaveURL(/view=journey/);
  await page.goto('/insights');
  await expect(page.getByRole('heading', { name: 'Broker insights', exact: true })).toBeVisible();
  await expect(page.locator('.insight-kpis article')).toHaveCount(4);
  await scan(page);
  await page.getByRole('button', { name: 'Summarise my period' }).click();
  await expect(page.getByRole('heading', { name: 'Saved-record period summary' })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await scan(page);
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
  ).toBeTruthy();
  await page.screenshot({ path: '.runtime/qa/workspace-insights-mobile.png', fullPage: true });
  expect(errors).toEqual([]);
});
