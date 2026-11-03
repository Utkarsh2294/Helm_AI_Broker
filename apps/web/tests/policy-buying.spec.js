import { test, expect } from '@playwright/test';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
test.use({ bypassCSP: true });

async function scan(page) {
  await page.addScriptTag({ path: require.resolve('axe-core/axe.min.js') });
  const violations = await page.evaluate(async () =>
    (
      await window.axe.run(document, {
        runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'] },
      })
    ).violations.map((row) => ({ id: row.id, targets: row.nodes.map((node) => node.target) })),
  );
  expect(violations).toEqual([]);
}

for (const basis of ['moratorium', 'fmu']) {
  test(`${basis}: published shortlist through buying documents to green closure`, async ({
    page,
  }) => {
    test.setTimeout(240000);
    const errors = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto('/login');
    await page.getByLabel('Email address').fill('broker@helm.demo');
    await page.getByLabel('Password', { exact: true }).fill('HelmDemo!2026');
    await page.getByRole('button', { name: 'Sign in to your workspace' }).click();
    await expect(page.getByRole('button', { name: 'Start automatic demo' })).toBeVisible();
    const csrf = (await page.context().cookies()).find(
      (cookie) => cookie.name === 'helm_csrf',
    ).value;
    const headers = { 'X-CSRF-Token': csrf };
    async function post(path, data) {
      const result = await page.request.post(`/api/v1${path}`, {
        headers,
        ...(data ? { data } : {}),
      });
      expect(result.ok(), await result.text()).toBeTruthy();
      return result.json();
    }
    const created = await post(`/demo/journeys?underwriting=${basis}`);
    const id = created.id;
    let item;
    await expect
      .poll(
        async () => {
          item = await (await page.request.get(`/api/v1/cases/${id}`)).json();
          return item.state;
        },
        { timeout: 90000 },
      )
      .toBe('BROKER_REVIEW');
    await post(`/demo/journeys/${id}/selection`, {
      ranking_id: item.ranking.id,
      selected: item.ranking.top.slice(0, 3).map((row) => row.plan.id),
      confirm_selection: true,
    });
    await expect
      .poll(
        async () => {
          item = await (await page.request.get(`/api/v1/cases/${id}`)).json();
          return item.state;
        },
        { timeout: 60000 },
      )
      .toBe('AWAIT_APPROVAL');
    const proof = await post('/auth/step-up', { password: 'HelmDemo!2026' });
    await post(`/demo/journeys/${id}/signoff`, {
      pack_hash: item.pack.pack_hash,
      step_up_token: proof.step_up_token,
      confirm_final_review: true,
    });
    await page.goto(`/case/${id}`);
    const choice = page.getByRole('region', { name: 'Demo consumer quote selection' });
    await choice.getByRole('radio').first().check();
    await choice.getByRole('button', { name: 'Simulate: proceed with this plan' }).click();
    await expect(page).toHaveURL(new RegExp(`/policy-buying/cases/${id}`));
    await page.goto(`/policy-buying/cases/${id}?step=ipid`);
    await expect(page.locator('#document-ipid')).toBeFocused();
    await page.getByRole('link', { name: 'Case audit trail' }).click();
    await expect(page.getByRole('dialog', { name: 'Case workspace' })).toBeVisible();
    await page.getByRole('button', { name: 'Close case', exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`/policy-buying/cases/${id}`));
    await expect(page.getByRole('complementary', { name: 'Digital client file' })).toContainText(
      basis === 'fmu' ? 'Full Medical Underwriting' : 'Moratorium',
    );
    await page.getByRole('button', { name: 'I acknowledge this underwriting basis' }).click();
    const ipid = page.locator('#document-ipid');
    await ipid.getByRole('button', { name: 'Approve & Send', exact: true }).click();
    await ipid.getByRole('button', { name: 'Simulate: consumer confirms', exact: true }).click();
    const toba = page.locator('#document-toba');
    await toba.getByRole('button', { name: 'Approve & Send', exact: true }).click();
    await toba.getByRole('button', { name: 'Simulate: consumer confirms', exact: true }).click();
    const declaration = page.locator(
      basis === 'fmu' ? '#document-fmu_questionnaire' : '#document-moratorium_declaration',
    );
    await declaration.getByRole('button', { name: 'Approve & Send', exact: true }).click();
    await declaration
      .getByRole('button', {
        name:
          basis === 'fmu'
            ? 'Simulate: consumer completes and signs questionnaire'
            : 'Simulate: consumer accepts and signs declaration',
      })
      .click();
    if (basis === 'fmu') {
      await declaration
        .getByRole('button', { name: 'Verify to view completed FMU answers' })
        .click();
      await declaration.getByLabel('Security verification password').fill('HelmDemo!2026');
      await declaration.getByRole('button', { name: 'Reveal fictional FMU answers' }).click();
      await expect(declaration).toContainText('Seeded fictional entry');
      await declaration.getByRole('button', { name: 'Hide medical answers' }).click();
    }
    await declaration.getByRole('button', { name: 'Approve underwriting declaration' }).click();
    const banking = page.getByRole('region', { name: 'Fictional banking setup' });
    await banking
      .getByRole('button', {
        name: 'Simulate: consumer submits banking details and mandate consent',
      })
      .click();
    await banking.getByRole('button', { name: 'Open one-time banking verification' }).click();
    await banking.getByLabel('Security verification password').fill('HelmDemo!2026');
    await banking.getByRole('button', { name: 'Reveal dummy banking details' }).click();
    await expect(banking).toContainText('00001234');
    await banking.getByRole('button', { name: 'Hide details', exact: true }).click();
    await banking.getByRole('button', { name: 'Confirm fictional payment setup' }).click();
    const submission = page.getByRole('region', { name: 'Final submission review' });
    await submission.getByRole('button', { name: 'Review & Send', exact: true }).click();
    await expect(
      submission.getByRole('heading', { name: 'Read-only package preview' }),
    ).toBeVisible();
    await page.setViewportSize({ width: 1440, height: 1000 });
    await scan(page);
    await page.setViewportSize({ width: 390, height: 844 });
    await scan(page);
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
    ).toBeTruthy();
    await page.screenshot({ path: `../../.runtime/qa/pb-${basis}-mobile.png`, fullPage: true });
    await submission.getByRole('button', { name: 'Send to mock insurer' }).click();
    await expect(page.getByRole('region', { name: 'Demo policy issued' })).toContainText('DEMO-');
    await expect(page.locator('.pb-working')).not.toContainText('00001234');
    await page.getByRole('link', { name: 'Back to Closed Cases' }).click();
    await expect(page.getByRole('heading', { name: 'Closed Cases', exact: true })).toBeVisible();
    await expect(
      page.locator('.pb-success').filter({ hasText: 'Morgan Demo' }).first(),
    ).toBeVisible();
    expect(errors).toEqual([]);
  });
}
