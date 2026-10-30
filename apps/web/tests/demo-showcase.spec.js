import { test, expect } from '@playwright/test';
import { openManualCase } from './manual-case';
import { readFile, writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
const require = createRequire(import.meta.url);
const reports = [];
test.use({ bypassCSP: true }); // Axe instrumentation only; normal workflow tests enforce shipped CSP.

async function login(page, email = 'broker@helm.demo') {
  await page.goto('/login');
  await page.getByLabel('Email address').fill(email);
  await page.getByLabel('Password', { exact: true }).fill('HelmDemo!2026');
  await page.getByRole('button', { name: 'Sign in to your workspace' }).click();
  await expect(
    page.getByRole('heading', { name: 'Good advice starts with clarity.' }),
  ).toBeVisible();
}
async function scan(page, screen) {
  await page.addScriptTag({ path: require.resolve('axe-core/axe.min.js') });
  const violations = await page.evaluate(async () =>
    (
      await window.axe.run(document, {
        runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'] },
      })
    ).violations.map((v) => ({
      id: v.id,
      impact: v.impact,
      targets: v.nodes.map((n) => n.target),
    })),
  );
  reports.push({ screen, violations });
}
test.afterAll(async () => {
  await writeFile(
    new URL('../../../.runtime/qa/demo-axe-report.json', import.meta.url),
    JSON.stringify(reports, null, 2),
  );
  expect(reports.filter((report) => report.violations.length)).toEqual([]);
});

async function comparison(panel) {
  await panel.getByRole('checkbox', { name: 'I reviewed this fact-find', exact: false }).check();
  await panel.getByRole('button', { name: 'Sign off fact-find' }).click();
  await panel.getByRole('button', { name: 'Release demo RFQ' }).click();
  await expect(panel.getByRole('button', { name: 'Compare top five' })).toBeVisible({
    timeout: 25000,
  });
  await panel.getByRole('button', { name: 'Compare top five' }).click();
}
async function assess(panel, decision = 'Recommend') {
  for (let i = 0; i < 5; i++) {
    const card = panel.locator('.quote-card').nth(i);
    await card.getByRole('slider').fill(decision === 'Recommend' ? '4' : '2');
    await card.getByRole('radio', { name: decision, exact: true }).check();
    await card
      .getByRole('textbox', { name: 'Your reason for', exact: false })
      .fill(
        'I reviewed the fictional terms, recorded hospital network and annual premium against the stated needs.',
      );
    await card.getByRole('button', { name: 'Save rating', exact: true }).click();
    await expect(card.getByText('Assessment saved · Broker edited')).toBeVisible();
  }
}

test('fictional documents flow reaches two independent demo reviews through G0 G1 and G2', async ({
  page,
}) => {
  test.setTimeout(180000);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await login(page);
  await page.getByRole('button', { name: 'Pilot showcase', exact: true }).click();
  await page.getByRole('button', { name: 'Create showcase case' }).click();
  await scan(page, 'pilot documents desktop');
  const downloaded = page.waitForEvent('download');
  await page.getByRole('link', { name: 'Download renewal PDF', exact: true }).click();
  const renewal = await downloaded;
  expect((await readFile(await renewal.path())).subarray(0, 5).toString()).toBe('%PDF-');
  await renewal.saveAs(
    fileURLToPath(new URL('../../../.runtime/qa/demo-renewal.pdf', import.meta.url)),
  );
  await page.getByRole('link', { name: 'Open showcase case', exact: false }).click();
  const panel = page.getByRole('dialog', { name: 'Case workspace' });
  await panel.getByRole('button', { name: 'Verify access to sensitive documents' }).click();
  const access = page.getByRole('dialog', { name: 'Reveal medical statements', exact: true });
  await access.getByLabel('Security verification password').fill('HelmDemo!2026');
  await access.getByRole('button', { name: 'Verify medical access', exact: true }).click();
  await expect(access).not.toBeVisible();
  await panel.getByLabel('Source document (PDF or text, up to 1 MB)').setInputFiles({
    name: 'fictional-renewal.pdf',
    mimeType: 'application/pdf',
    buffer: await readFile(await renewal.path()),
  });
  const uploaded = page.waitForResponse(
    (r) => r.url().endsWith('/documents') && r.request().method() === 'POST',
  );
  await panel.getByRole('button', { name: 'Upload for broker review' }).click();
  expect((await uploaded).status()).toBe(200);
  await expect(panel.getByRole('link', { name: 'Download original document' })).toBeVisible();
  await scan(page, 'case uploaded source document');
  await comparison(panel);
  await assess(panel);
  await scan(page, 'case comparison ratings');
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
  await scan(page, 'selection feedback sheet');
  await panel.getByRole('button', { name: 'Prepare recommendation pack' }).click();
  await expect(panel.getByText('Your recommendation pack')).toBeVisible();
  await scan(page, 'recommendation review');
  for (const checkbox of await panel.locator('.review-checklist input[type="checkbox"]').all())
    await checkbox.check();
  await panel.getByRole('button', { name: 'Continue to selected plans' }).click();
  await scan(page, 'guided selected plan review');
  for (const checkbox of await panel.locator('.review-checklist input[type="checkbox"]').all())
    await checkbox.check();
  await panel.getByRole('button', { name: 'Continue to final confirmation' }).click();
  await scan(page, 'guided final review confirmation');
  await panel.locator('.review-checklist input[type="checkbox"]').check();
  await panel.getByRole('button', { name: 'Save review and continue' }).click();
  await scan(page, 'ready for password approval');
  await panel.getByLabel('Confirm your password').fill('HelmDemo!2026');
  await panel.getByRole('button', { name: 'Approve demo recommendation' }).click();
  await expect(panel.getByText('Approved. Ready for the next step.')).toBeVisible();
  for (const tab of ['Fact-find', 'Compare (5)', 'Recommendation', 'Activity']) {
    await panel.getByRole('tab', { name: tab, exact: true }).click();
    await scan(page, 'published case ' + tab);
  }
  await panel.getByRole('button', { name: 'Close case' }).click();
  for (const email of ['compliance@helm.demo', 'legal@helm.demo']) {
    await page.getByRole('button', { name: 'Sign out' }).click();
    await expect(page).toHaveURL(/\/signed-out\/voluntary$/);
    await login(page, email);
    await page.getByRole('button', { name: 'Pilot showcase', exact: true }).click();
    await expect(page.getByText('G2 publication recorded', { exact: true })).toBeVisible();
    for (const checkbox of await page
      .locator('.demo-showcase fieldset input[type="checkbox"]')
      .all())
      await checkbox.check();
    await page
      .getByLabel('Demo reviewer note')
      .fill('I inspected the fictional documents and broker evidence for this demonstration only.');
    await scan(page, 'pilot review ' + email);
    await page.getByRole('button', { name: 'Verify and record demo review' }).click();
    const sheet = page.getByRole('dialog', { name: 'Confirm fictional pilot review' });
    await sheet.getByLabel('Security verification password').fill('HelmDemo!2026');
    await sheet.getByRole('button', { name: 'Record fictional review' }).click();
    await expect(sheet).not.toBeVisible();
  }
  await expect(
    page.getByText('Demonstration review complete. This is not a live go-live decision.'),
  ).toBeVisible();
  const status = await (await page.request.get('/api/v1/demo/showcase')).json();
  expect(status.demo_ready).toBe(true);
  expect(status.live_release_approved).toBe(false);
  expect(status.reviews).toHaveLength(2);
  const report = page.waitForEvent('download');
  await page.getByRole('link', { name: 'Download demo review record' }).click();
  await (
    await report
  ).saveAs(fileURLToPath(new URL('../../../.runtime/qa/demo-review-record.pdf', import.meta.url)));
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: fileURLToPath(new URL('../../../.runtime/qa/demo-showcase-desktop.png', import.meta.url)),
  });
  await page.setViewportSize({ width: 390, height: 900 });
  await page.screenshot({
    path: fileURLToPath(
      new URL('../../../.runtime/qa/demo-showcase-mobile-normal.png', import.meta.url),
    ),
  });
  await page.evaluate(() => (document.documentElement.style.fontSize = '200%'));
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(
    await page
      .locator('.demo-journey, .demo-journey > li, .demo-journey p')
      .evaluateAll((nodes) => nodes.some((node) => node.scrollWidth > node.clientWidth + 1)),
  ).toBe(false);
  await scan(page, 'pilot completed mobile 200 percent reduced motion');
  await page.screenshot({
    path: fileURLToPath(new URL('../../../.runtime/qa/demo-showcase-mobile.png', import.meta.url)),
    fullPage: true,
  });
});

test('all excluded plans close without sending advice and generate a closure PDF', async ({
  page,
}) => {
  test.setTimeout(90000);
  await login(page);
  await openManualCase(page);
  const panel = page.getByRole('dialog', { name: 'Case workspace' });
  await comparison(panel);
  await assess(panel, 'Exclude');
  await panel.getByRole('button', { name: 'Close without advice', exact: true }).click();
  const sheet = page.getByRole('dialog', { name: 'Close without sending advice' });
  await sheet
    .getByLabel('Reason for no suitable recommendation')
    .fill('The fictional comparison does not meet the client priorities after broker review.');
  await sheet.getByRole('checkbox').check();
  await scan(page, 'no advice closure confirmation');
  await sheet.getByRole('button', { name: 'Confirm closure' }).click();
  await expect(sheet).not.toBeVisible();
  const id = new URL(page.url()).pathname.split('/').at(-1);
  const current = await (await page.request.get(`/api/v1/cases/${id}`)).json();
  expect(current.state).toBe('CLOSED');
  expect(current.publication).toBeNull();
  const pdf = await page.request.get(`/api/v1/cases/${id}/closure.pdf`);
  expect(pdf.headers()['content-type']).toContain('application/pdf');
});

test('broker case controls and underwriter referrals keep human review in place', async ({
  page,
}) => {
  test.setTimeout(90000);
  await login(page);
  await openManualCase(page);
  const panel = page.getByRole('dialog', { name: 'Case workspace' });
  await panel.getByRole('button', { name: 'Case controls', exact: true }).click();
  const controls = page.getByRole('dialog', { name: 'Case controls', exact: true });
  await controls.getByLabel('Priority', { exact: true }).selectOption('urgent');
  await controls
    .getByLabel('Reason for changing case controls')
    .fill('Please prioritise review of this fictional client renewal.');
  await scan(page, 'case controls confirmation');
  await controls.getByRole('button', { name: 'Save case controls' }).click();
  await expect(controls).not.toBeVisible();
  await comparison(panel);
  const id = new URL(page.url()).pathname.split('/').at(-1);
  const before = await (await page.request.get(`/api/v1/cases/${id}`)).json();
  const card = panel.locator('.quote-card').first();
  await card.getByRole('slider').fill('3');
  await card.getByRole('radio', { name: 'Refer to UW', exact: true }).check();
  await card
    .getByRole('textbox', { name: 'Your reason for', exact: false })
    .fill('Please clarify the fictional terms with the underwriter before advice.');
  await card.getByRole('button', { name: 'Save rating', exact: true }).click();
  await panel.getByRole('button', { name: 'Refer marked plans' }).click();
  let sheet = page.getByRole('dialog', { name: 'Request underwriter review' });
  await sheet
    .getByLabel('Referral reason', { exact: true })
    .fill('Please clarify the original fictional policy terms before advice.');
  await sheet.getByRole('button', { name: 'Create referral and hold case' }).click();
  await expect(sheet).not.toBeVisible();
  await scan(page, 'underwriter referral hold');
  await panel.getByRole('button', { name: 'Resolve demo referral' }).click();
  sheet = page.getByRole('dialog', { name: 'Record fictional underwriter response' });
  await sheet.getByLabel('Fictional underwriter reference').fill('DEMO-UW-BROWSER-001');
  await sheet
    .getByLabel('Referral resolution reason')
    .fill(
      'Fictional confirmation received; original terms still need independent broker assessment.',
    );
  await sheet.getByRole('checkbox').check();
  await scan(page, 'underwriter response confirmation');
  await sheet.getByRole('button', { name: 'Record response and return to comparison' }).click();
  await expect(sheet).not.toBeVisible();
  const current = await (await page.request.get(`/api/v1/cases/${id}`)).json();
  expect(current.state).toBe('BROKER_REVIEW');
  expect(current.priority).toBe('urgent');
  expect(current.ranking.id).toBe(before.ranking.id);
  await panel.getByRole('button', { name: 'Record complaint', exact: true }).click();
  sheet = page.getByRole('dialog', { name: 'Record a complaint' });
  await sheet
    .getByLabel('Complaint details')
    .fill('The fictional consumer asked us to review the service experience.');
  await sheet.getByRole('button', { name: 'Record complaint and pause work' }).click();
  await expect(panel.getByRole('heading', { name: 'Complaint hold' })).toBeVisible();
  await scan(page, 'complaint hold');
});
