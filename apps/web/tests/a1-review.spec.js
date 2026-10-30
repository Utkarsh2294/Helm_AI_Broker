import { test, expect } from '@playwright/test';

test('broker reviews medical ambiguity and autosaves successive fact-find versions before G0', async ({
  page,
}) => {
  await page.goto('/login');
  await page.getByRole('button', { name: 'Fill demo credentials' }).click();
  await page.getByRole('button', { name: 'Sign in to your workspace' }).click();
  await expect(
    page.getByRole('heading', { name: 'Good advice starts with clarity.' }),
  ).toBeVisible();
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
  const response = await page.request.post('/api/v1/demo/requests', {
    headers: { 'X-CSRF-Token': csrf },
    data: {
      id: 'a1-browser-' + Date.now(),
      name: 'Fictional wording review',
      medical_items: ['Maybe asthma.'],
      needs: { coverage: { outpatient: { level: 2 } } },
    },
  });
  expect(response.ok()).toBeTruthy();
  const item = await response.json();
  await page.goto('/case/' + item.id);
  const panel = page.getByRole('dialog', { name: 'Case workspace' });
  await expect(panel.getByRole('heading', { name: 'H5 · Review medical wording' })).toBeVisible();
  await expect(panel.getByRole('button', { name: 'Record medical review' })).toBeDisabled();
  await panel.getByRole('button', { name: 'Reveal medical statements' }).click();
  await page.getByLabel('Security verification password', { exact: true }).fill('HelmDemo!2026');
  await page.getByRole('button', { name: 'Verify medical access' }).click();
  await expect(panel.getByText('Maybe asthma.', { exact: true })).toBeVisible();
  await panel
    .getByLabel('Medical wording review reason')
    .fill(
      'Reviewed the verbatim declaration with the consumer without inferring coverage or diagnosis.',
    );
  await panel.getByRole('button', { name: 'Record medical review' }).click();
  await expect(panel.getByRole('heading', { name: 'H5 · Review medical wording' })).toHaveCount(0);
  await panel.getByRole('button', { name: 'Edit stated requirements' }).click();
  const editor = panel.locator('.dnr-editor');
  await editor.getByLabel('Annual budget (£)', { exact: true }).fill('2100');
  await editor
    .getByLabel('Reason for changes')
    .fill('Consumer confirmed the revised annual budget and hospital requirements.');
  await expect(editor.getByRole('status')).toHaveText('All changes saved');
  await editor.getByLabel('Hospital network level').selectOption('3');
  await expect(editor.getByRole('status')).toHaveText('All changes saved');
  const saved = await (await page.request.get('/api/v1/cases/' + item.id)).json();
  expect(saved.dnr.needs.budget_annual_pence).toBe(210000);
  expect(saved.dnr.needs.hospital_level).toBe(3);
  expect(saved.dnr.version).toBeGreaterThanOrEqual(3);
  await editor.getByRole('button', { name: 'Done', exact: true }).click();
  await panel.getByRole('checkbox', { name: 'I reviewed this fact-find', exact: false }).check();
  await panel.getByRole('button', { name: 'Sign off fact-find' }).click();
  await expect(panel.getByRole('heading', { name: 'Ready to explore the panel.' })).toBeVisible();
});
