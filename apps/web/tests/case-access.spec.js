import { test, expect } from '@playwright/test';

test('medical reveal requires verification, survives polling and can be hidden', async ({
  page,
}) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Fill demo credentials' }).click();
  await page.getByRole('button', { name: 'Sign in to your workspace' }).click();
  await expect(
    page.getByRole('heading', { name: 'Good advice starts with clarity.' }),
  ).toBeVisible();
  const csrf = await page.evaluate(() =>
    decodeURIComponent(
      document.cookie
        .split('; ')
        .find((cookie) => cookie.startsWith('helm_csrf='))
        .split('=')
        .slice(1)
        .join('='),
    ),
  );
  const unique = `medical-browser-${Date.now()}`;
  const response = await page.request.post('/api/v1/demo/requests', {
    headers: { 'X-CSRF-Token': csrf },
    data: {
      id: unique,
      name: 'Fictional medical access test',
      medical_items: ['PHI_BROWSER_CANARY_5702'],
      needs: { coverage: {} },
    },
  });
  expect(response.ok()).toBe(true);
  const item = await response.json();
  await page.goto(`/case/${item.id}`);
  const panel = page.getByRole('dialog', { name: 'Case workspace' });
  await expect(panel.locator('.medical-verbatim')).toHaveText('[REDACTED]');
  await panel.getByRole('button', { name: 'Reveal medical statements' }).click();
  const reveal = page.getByRole('dialog', { name: 'Reveal medical statements', exact: true });
  await reveal.getByLabel('Security verification password').fill('HelmDemo!2026');
  await reveal.getByRole('button', { name: 'Verify medical access' }).click();
  await expect(panel.locator('.medical-verbatim')).toHaveText('PHI_BROWSER_CANARY_5702');
  await page.waitForResponse(
    (result) => result.url().includes('include_medical=true') && result.status() === 200,
  );
  await expect(panel.locator('.medical-verbatim')).toHaveText('PHI_BROWSER_CANARY_5702');
  await panel.getByRole('button', { name: 'Hide medical statements' }).click();
  await expect(panel.locator('.medical-verbatim')).toHaveText('[REDACTED]');
  await page.reload();
  await expect(panel).toBeVisible();
  await expect(panel.locator('.medical-verbatim')).toHaveText('[REDACTED]');
});
