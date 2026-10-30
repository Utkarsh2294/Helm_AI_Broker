import { test, expect } from '@playwright/test';

async function login(page, email) {
  await page.goto('/login');
  await page.getByLabel('Email address').fill(email);
  await page.getByLabel('Password', { exact: true }).fill('HelmDemo!2026');
  await page.getByRole('button', { name: 'Sign in to your workspace' }).click();
  await expect(
    page.getByRole('heading', { name: 'Good advice starts with clarity.' }),
  ).toBeVisible();
}
test('a complaint pauses work until its compliance owner records resolution', async ({ page }) => {
  await login(page, 'broker@helm.demo');
  const csrf = await page.evaluate(() =>
    decodeURIComponent(
      document.cookie
        .split('; ')
        .find((c) => c.startsWith('helm_csrf='))
        .split('=')
        .slice(1)
        .join('='),
    ),
  );
  const created = await page.request.post('/api/v1/demo/requests', {
    headers: { 'X-CSRF-Token': csrf },
    data: {
      id: 'complaint-browser-' + Date.now(),
      name: 'Fictional complaint case',
      needs: { coverage: { outpatient: { level: 2 } } },
    },
  });
  expect(created.ok()).toBeTruthy();
  const item = await created.json();
  await page.goto('/case/' + item.id);
  const panel = page.getByRole('dialog', { name: 'Case workspace' });
  await panel.getByRole('button', { name: 'Record complaint', exact: true }).click();
  const sheet = page.getByRole('dialog', { name: 'Record a complaint' });
  await sheet
    .getByLabel('Complaint details')
    .fill('Fictional consumer asked for a review of their service experience.');
  await sheet.getByRole('button', { name: 'Record complaint and pause work' }).click();
  await expect(panel.getByRole('heading', { name: 'Complaint hold' })).toBeVisible();
  await expect(panel.getByLabel('Complaint resolution')).toHaveCount(0);
  await page.goto('/queue');
  await page.getByRole('button', { name: 'Sign out' }).click();
  await expect(page).toHaveURL(/signed-out/);
  await login(page, 'compliance@helm.demo');
  await page.goto('/case/' + item.id);
  await panel
    .getByLabel('Complaint resolution')
    .fill(
      'Fictional complaint reviewed with the consumer and resolved with a recorded explanation.',
    );
  await panel.getByRole('button', { name: 'Record resolution and release hold' }).click();
  await expect(panel.getByRole('heading', { name: 'Complaint hold' })).toHaveCount(0);
  await expect(panel.getByText('Demands & needs record', { exact: true })).toBeVisible();
});
