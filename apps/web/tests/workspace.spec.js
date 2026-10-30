import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { createHmac } from 'node:crypto';

async function login(page) {
  await page.goto('/');
  await page.getByRole('button', { name: 'Fill demo credentials' }).click();
  await page.getByRole('button', { name: 'Sign in to your workspace' }).click();
  await expect(
    page.getByRole('heading', { name: 'Good advice starts with clarity.' }),
  ).toBeVisible();
}

test('broker completes the five-agent workflow with real approval and evidence', async ({
  page,
}) => {
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await login(page);
  await page.getByRole('button', { name: 'New demo request' }).click();
  const panel = page.getByRole('dialog', { name: 'Case workspace' });
  await expect(panel.getByText('Demands & needs record')).toBeVisible();
  await panel.getByRole('checkbox', { name: 'I reviewed this fact-find', exact: false }).check();
  await panel.getByRole('button', { name: 'Sign off fact-find' }).click();
  await panel.getByRole('button', { name: 'Release demo RFQ' }).click();
  await expect(panel.getByRole('button', { name: 'Compare top five' })).toBeVisible({
    timeout: 20000,
  });
  await panel.getByRole('button', { name: 'Compare top five' }).click();
  const copilotReply = page.waitForResponse((r) => r.url().endsWith('/ranking/copilot'));
  await panel.getByRole('button', { name: 'Why #2 above #3?' }).click();
  expect((await (await copilotReply).json()).cited_fields.length).toBeGreaterThan(0);
  await expect(panel.getByRole('button', { name: 'Select this plan' }).first()).toBeDisabled();
  for (let i = 0; i < 5; i++) {
    const card = panel.locator('.quote-card').nth(i);
    await card.getByRole('slider').fill('4');
    await card.getByRole('radio', { name: 'Recommend', exact: true }).check();
    await card
      .getByRole('textbox', { name: 'Your reason for', exact: false })
      .fill(
        'I reviewed the recorded coverage, annual cost and hospital network against the stated consumer priorities.',
      );
    await card.getByRole('button', { name: 'Save rating', exact: true }).click();
    await expect(card.getByText('Assessment saved · Broker edited')).toBeVisible();
  }
  await expect(panel.getByText('Rated 5 of 5 plans.', { exact: false })).toBeVisible();
  for (let i = 0; i < 3; i++) {
    const card = panel.locator('.quote-card').nth(i);
    await card.getByRole('button', { name: 'Select this plan' }).click();
    if (await card.getByRole('checkbox').count()) await card.getByRole('checkbox').check();
  }
  await panel.getByRole('button', { name: 'Review selections & feedback' }).click();
  for (const button of await panel
    .getByRole('button', { name: 'Score looks right for', exact: false })
    .all())
    await button.click();
  await panel.getByRole('button', { name: 'Prepare recommendation pack' }).click();
  await expect(panel.getByText('Your recommendation pack')).toBeVisible();
  const statement = panel.getByLabel('Suitability statement');
  await statement.fill(
    (await statement.inputValue()) + ' Reviewed with the recorded customer priorities.',
  );
  await panel.getByRole('button', { name: 'Save statement' }).click();
  await expect(panel.getByRole('button', { name: 'Save statement' })).toHaveCount(0);
  for (const checkbox of await panel.locator('.review-checklist input[type="checkbox"]').all())
    await checkbox.check();
  await panel.getByRole('button', { name: 'Save review confirmations' }).click();
  await panel.getByLabel('Confirm your password').fill('HelmDemo!2026');
  await panel.getByRole('button', { name: 'Approve demo recommendation' }).click();
  await expect(panel.getByText('Approved. Ready for the next step.')).toBeVisible();
  const download = page.waitForEvent('download');
  await panel.getByRole('button', { name: 'Evidence', exact: true }).click();
  const jsonDownload = await download;
  expect(jsonDownload.suggestedFilename()).toContain('helm-evidence');
  const evidence = JSON.parse(await readFile(await jsonDownload.path(), 'utf8'));
  expect(evidence.compliance_checklist).toHaveLength(18);
  expect(evidence.audit_chain.verified).toBe(true);
  const pdf = page.waitForEvent('download');
  await panel.getByRole('button', { name: 'PDF', exact: true }).click();
  await (
    await pdf
  ).saveAs(fileURLToPath(new URL('../../../.runtime/qa/complete-evidence.pdf', import.meta.url)));
  await panel.getByLabel('Case time-machine').focus();
  await page.keyboard.press('Home');
  await expect(panel.getByText('Historical view · read only')).toBeVisible();
  await panel.getByRole('button', { name: 'Return to present' }).click();
  await expect(panel.getByText('Historical view · read only')).toHaveCount(0);
  const caseId = new URL(page.url()).pathname.split('/').at(-1);
  const current = await (await page.request.get(`/api/v1/cases/${caseId}`)).json();
  const event = JSON.stringify({
    id: `expiry-${Date.now()}`,
    type: 'consumer.magic_link_expired',
    case_id: caseId,
    pack_hash: current.pack.pack_hash,
  });
  const timestamp = String(Math.floor(Date.now() / 1000));
  const signature =
    'sha256=' +
    createHmac('sha256', 'demo-webhook-secret-change-before-live')
      .update(timestamp + '.' + event)
      .digest('hex');
  const expired = await page.request.post('/api/v1/webhooks/core', {
    data: event,
    headers: {
      'Content-Type': 'application/json',
      'X-Helm-Timestamp': timestamp,
      'X-Helm-Signature': signature,
    },
  });
  expect(expired.ok()).toBeTruthy();
  await panel.getByRole('tab', { name: 'Fact-find', exact: true }).click();
  await expect(panel.getByText('The consumer link expired.', { exact: false })).toBeVisible();
  await panel.getByRole('button', { name: 'Close case' }).click();
  await page.getByRole('button', { name: 'Learning & insights', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Run evaluation', exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: 'Sign out' }).click();
  await expect(page).toHaveURL(/\/signed-out\/voluntary$/);
  await page.goto('/login');
  await page.getByLabel('Email address').fill('compliance@helm.demo');
  await page.getByLabel('Password', { exact: true }).fill('HelmDemo!2026');
  await page.getByRole('button', { name: 'Sign in to your workspace' }).click();
  await page.getByRole('button', { name: 'Learning & insights', exact: true }).click();
  const evaluationResponse = page.waitForResponse(
    (r) => r.url().endsWith('/models/evaluate') && r.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Run evaluation', exact: true }).click();
  const evaluation = await (await evaluationResponse).json();
  expect(evaluation.auto_applied).toBe(false);
  await expect(
    page
      .getByRole('heading', {
        name: evaluation.status.replaceAll('_', ' ').replace(/\b\w/g, (c) => c.toUpperCase()),
      })
      .first(),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Sign out' }).click();
  await expect(page.getByRole('heading', { name: "You've been signed out." })).toBeVisible();
  expect(errors).toEqual([]);
});

test('broker can pause release with a reason and resume before sending RFQs', async ({ page }) => {
  await login(page);
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
  const headers = { 'X-CSRF-Token': csrf };
  const created = await page.request.post('/api/v1/demo/requests', {
    headers,
    data: {
      id: 'release-pause-' + Date.now(),
      name: 'Fictional release pause',
      needs: { coverage: { outpatient: { level: 2 } } },
    },
  });
  expect(created.ok()).toBeTruthy();
  const item = await created.json();
  expect(
    (
      await page.request.post('/api/v1/cases/' + item.id + '/sign-off', {
        headers,
        data: { dnr_acknowledged: true },
      })
    ).ok(),
  ).toBeTruthy();
  await page.goto('/case/' + item.id);
  const panel = page.getByRole('dialog', { name: 'Case workspace' });
  await panel.getByRole('button', { name: 'Pause', exact: true }).click();
  const sheet = page.getByRole('dialog', { name: 'Pause this case' });
  await expect(sheet.getByRole('button', { name: 'Confirm pause' })).toBeDisabled();
  await sheet
    .getByLabel('Reason for pausing')
    .fill('Verify the stated hospital network with the consumer before release.');
  await sheet.getByRole('button', { name: 'Confirm pause' }).click();
  await expect(sheet).not.toBeVisible();
  await panel.getByRole('button', { name: 'Resume', exact: true }).click();
  await expect(panel.getByRole('heading', { name: 'Ready to explore the panel.' })).toBeVisible();
  const current = await (await page.request.get('/api/v1/cases/' + item.id)).json();
  expect(current.state).toBe('AWAIT_BROKER_RELEASE');
  expect(current.quotes).toBeNull();
});

test('workspace counts include cases beyond the loaded page', async ({ page }) => {
  await login(page);
  const listing = await (await page.request.get('/api/v1/cases?limit=50')).json();
  const total = Object.values(listing.summary).reduce((sum, count) => sum + count, 0);
  const open = total - (listing.summary.PUBLISHED || 0) - (listing.summary.CLOSED || 0);
  await expect(
    page.locator('.metric').filter({ hasText: 'Open cases' }).locator('strong'),
  ).toHaveText(String(open).padStart(2, '0'));
  await expect(page.locator('.case-section .count-badge')).toHaveText(String(listing.total));
  await page.getByRole('textbox', { name: 'Search cases' }).fill('Asha');
  const filtered = await (await page.request.get('/api/v1/cases?limit=50&q=Asha')).json();
  await expect(page.locator('.case-section .count-badge')).toHaveText(String(filtered.total));
});

for (const width of [1440, 768, 390]) {
  test(`workspace and case panel fit viewport ${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    await login(page);
    await page.getByRole('textbox', { name: 'Search cases' }).fill('Asha');
    await expect(page.getByRole('button', { name: 'Open Asha Patel' })).toBeVisible();
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true);
    await page.screenshot({
      path: fileURLToPath(new URL(`../../../.runtime/qa/workspace-${width}.png`, import.meta.url)),
      fullPage: true,
    });
    await page.getByRole('button', { name: 'Open Asha Patel' }).click();
    const panel = page.getByRole('dialog', { name: 'Case workspace' });
    await expect(panel).toBeVisible();
    const bounds = await panel.boundingBox();
    expect(bounds.y).toBe(0);
    expect(bounds.width).toBeLessThanOrEqual(width);
    expect(await panel.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true);
    await page.screenshot({
      path: fileURLToPath(new URL(`../../../.runtime/qa/case-${width}.png`, import.meta.url)),
    });
    await page.keyboard.press('Escape');
    await expect(panel).toHaveCount(0);
  });
}
