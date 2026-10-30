import { test, expect } from '@playwright/test';

async function login(page) {
  await page.goto('/login');
  await page.getByLabel('Email address').fill('broker@helm.demo');
  await page.getByLabel('Password', { exact: true }).fill('HelmDemo!2026');
  await page.getByRole('button', { name: 'Sign in to your workspace' }).click();
  await expect(page.getByRole('button', { name: 'Start automatic demo' })).toBeVisible();
}

test('dashboard audit buttons open only their own case; removed pages stay removed', async ({
  page,
}) => {
  await login(page);
  const csrf = (await page.context().cookies()).find((cookie) => cookie.name === 'helm_csrf').value;
  const automatic = await page.request.post('/api/v1/demo/journeys', {
    headers: { 'X-CSRF-Token': csrf },
  });
  expect(automatic.ok()).toBeTruthy();
  const a = await automatic.json();
  const manual = await page.request.post('/api/v1/demo/requests', {
    headers: { 'X-CSRF-Token': csrf },
    data: {
      id: `scoped-audit-${crypto.randomUUID()}`,
      name: 'Other scoped client',
      needs: { coverage: { outpatient: { level: 2 } } },
    },
  });
  expect(manual.ok()).toBeTruthy();
  const b = await manual.json();
  await page.reload();
  await expect(page.getByRole('button', { name: 'Agent team', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Activity & audit', exact: true })).toHaveCount(0);
  await expect(page.locator('.pipeline-section')).toHaveCount(0);
  await expect(page.getByText('Your team, working in sync', { exact: true })).toHaveCount(0);
  for (const path of ['/agents', '/audit']) {
    await page.goto(path);
    await expect(page).toHaveURL(/\/queue$/);
  }
  const scopedReads = [];
  const globalReads = [];
  page.on('request', (request) => {
    if (request.url().includes('/cases/') && request.url().endsWith('/workspace'))
      scopedReads.push(request.url());
    if (request.url().includes('/audit/search')) globalReads.push(request.url());
  });
  await page
    .locator(`tr[data-case-id="${a.id}"]`)
    .getByRole('button', { name: 'Audit trail', exact: false })
    .click();
  const panel = page.getByRole('dialog', { name: 'Case workspace' });
  await expect(page).toHaveURL(new RegExp(`/case/${a.id}\\?view=audit$`));
  await expect(panel.getByRole('heading', { name: 'Morgan Demo', exact: true })).toBeVisible();
  await expect(panel.getByText('Audit chain verified', { exact: false })).toBeVisible();
  await expect(panel.locator('.agent-work-item details[open]')).toHaveCount(5);
  expect(scopedReads.length).toBeGreaterThan(0);
  expect(scopedReads.every((url) => url.includes(`/cases/${a.id}/workspace`))).toBeTruthy();
  await panel.getByRole('button', { name: 'Close case', exact: true }).click();
  scopedReads.length = 0;
  await page
    .locator(`tr[data-case-id="${b.id}"]`)
    .getByRole('button', { name: 'Audit trail', exact: false })
    .click();
  await expect(panel.getByRole('tab', { name: 'Audit trail', exact: true })).toHaveAttribute(
    'aria-selected',
    'true',
  );
  await expect(
    panel.getByRole('heading', { name: 'Other scoped client', exact: true }),
  ).toBeVisible();
  await expect(panel.getByText('Audit chain verified', { exact: false })).toBeVisible();
  expect(scopedReads.every((url) => url.includes(`/cases/${b.id}/workspace`))).toBeTruthy();
  expect(globalReads).toEqual([]);
});

test('case-row audit action is visible and usable on a phone', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page);
  const row = page.locator('.case-section tbody tr').first();
  await row.getByRole('button', { name: 'Audit trail', exact: false }).click();
  const panel = page.getByRole('dialog', { name: 'Case workspace' });
  await expect(panel.getByText('Audit chain verified', { exact: false })).toBeVisible();
  expect(
    await panel.evaluate((element) => element.scrollWidth <= element.clientWidth + 1),
  ).toBeTruthy();
  await panel.getByRole('button', { name: 'Close case', exact: true }).click();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
  ).toBeTruthy();
  await page.screenshot({ path: '.runtime/qa/case-audit-dashboard-mobile.png', fullPage: true });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.screenshot({ path: '.runtime/qa/case-audit-dashboard-desktop.png', fullPage: true });
});
