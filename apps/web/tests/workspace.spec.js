import { test, expect } from '@playwright/test';

async function login(page) {
  await page.goto('/');
  await page.getByRole('button', { name: 'Fill demo credentials' }).click();
  await page.getByRole('button', { name: 'Sign in to your workspace' }).click();
  await expect(page.getByRole('heading', { name: 'Good advice starts with clarity.' })).toBeVisible();
}

test('broker completes the five-agent workflow with real approval and evidence', async ({ page }) => {
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await login(page);
  await page.getByRole('button', { name: 'New demo request' }).click();
  const panel = page.getByRole('dialog', { name: 'Case workspace' });
  await expect(panel.getByText('Demands & needs record')).toBeVisible();
  await panel.getByRole('checkbox', { name: 'I reviewed this fact-find', exact: false }).check();
  await panel.getByRole('button', { name: 'Sign off fact-find' }).click();
  await panel.getByRole('button', { name: 'Release demo RFQ' }).click();
  await expect(panel.getByRole('button', { name: 'Compare top five' })).toBeVisible({ timeout: 20000 });
  await panel.getByRole('button', { name: 'Compare top five' }).click();
  for (let i = 0; i < 3; i++) {
    const card = panel.locator('.quote-card').nth(i);
    await card.getByRole('button', { name: 'Select this plan' }).click();
    if (await card.getByRole('checkbox').count()) await card.getByRole('checkbox').check();
  }
  await panel.getByRole('button', { name: 'Review selections & feedback' }).click();
  for (const button of await panel.getByRole('button', { name: 'Score looks right for', exact: false }).all()) await button.click();
  await panel.getByRole('button', { name: 'Prepare recommendation pack' }).click();
  await expect(panel.getByText('Your recommendation pack')).toBeVisible();
  const statement = panel.getByLabel('Suitability statement');
  await statement.fill((await statement.inputValue()) + ' Reviewed with the recorded customer priorities.');
  await panel.getByRole('button', { name: 'Save statement' }).click();
  await expect(panel.getByRole('button', { name: 'Save statement' })).toHaveCount(0);
  for (const checkbox of await panel.locator('.review-checklist input[type="checkbox"]').all()) await checkbox.check();
  await panel.getByRole('button', { name: 'Save review confirmations' }).click();
  await panel.getByLabel('Confirm your password').fill('HelmDemo!2026');
  await panel.getByRole('button', { name: 'Approve demo recommendation' }).click();
  await expect(panel.getByText('Approved. Ready for the next step.')).toBeVisible();
  const download = page.waitForEvent('download');
  await panel.getByRole('button', { name: 'Evidence', exact: true }).click();
  expect((await download).suggestedFilename()).toContain('helm-evidence');
  await panel.getByRole('button', { name: 'Close case' }).click();
  await page.getByRole('button', { name: 'Learning & insights', exact: true }).click();
  const evaluationResponse = page.waitForResponse(r => r.url().endsWith('/models/evaluate') && r.request().method() === 'POST');
  await page.getByRole('button', { name: 'Run evaluation', exact: true }).click();
  const evaluation = await (await evaluationResponse).json();
  expect(evaluation.auto_applied).toBe(false);
  await expect(page.getByRole('heading', { name: evaluation.status.replaceAll('_', ' ').replace(/\b\w/g, c => c.toUpperCase()) }).first()).toBeVisible();
  await page.getByRole('button', { name: 'Sign out' }).click();
  await expect(page.getByRole('heading', { name: 'Welcome back.' })).toBeVisible();
  expect(errors).toEqual([]);
});

for (const width of [1440, 768, 390]) {
  test(`workspace and case panel fit viewport ${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    await login(page);
    await expect(page.getByRole('button', { name: 'Open Asha Patel' })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({ path: `../../.runtime/workspace-${width}.png`, fullPage: true });
    await page.getByRole('button', { name: 'Open Asha Patel' }).click();
    const panel = page.getByRole('dialog', { name: 'Case workspace' });
    await expect(panel).toBeVisible();
    const bounds = await panel.boundingBox();
    expect(bounds.y).toBe(0);
    expect(bounds.width).toBeLessThanOrEqual(width);
    expect(await panel.evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
    await page.screenshot({ path: `../../.runtime/case-${width}.png` });
    await page.keyboard.press('Escape');
    await expect(panel).toHaveCount(0);
  });
}
