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
      impact: value.impact,
      targets: value.nodes.map((node) => node.target),
    })),
  );
  reports.push({ screen, violations });
}
test.afterAll(async () => {
  await writeFile(
    new URL('../../../.runtime/qa/agentic-axe.json', import.meta.url),
    JSON.stringify(reports, null, 2),
  );
  expect(reports.filter((report) => report.violations.length)).toEqual([]);
});

test('automatic demo needs only policy selection and authenticated final sign-off', async ({
  page,
}) => {
  test.setTimeout(90000);
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await login(page);
  await page.getByRole('button', { name: 'Workspace assistant' }).click();
  await page.getByRole('button', { name: 'Summarise my workspace' }).click();
  await expect(page.locator('.assistant-message.assistant')).toContainText('visible workspace');
  await scan(page, 'workspace assistant');
  await page.getByRole('button', { name: 'Start automatic demo' }).click();
  const panel = page.getByRole('dialog', { name: 'Case workspace' });
  await expect(panel.getByText('Only two human decisions.', { exact: true })).toBeVisible();
  await expect(panel.getByRole('button', { name: 'Sign off fact-find' })).toHaveCount(0);
  await expect(panel.getByRole('button', { name: 'Release demo RFQ' })).toHaveCount(0);
  await expect(panel.getByRole('heading', { name: 'Choose and rank three policies' })).toBeVisible({
    timeout: 30000,
  });
  await expect(panel.locator('.agent-work-item.complete')).toHaveCount(3);
  await expect(panel.getByRole('slider')).toHaveCount(0);
  await scan(page, 'automatic policy selection desktop');
  await page.screenshot({ path: '.runtime/qa/automatic-selection-desktop.png', fullPage: true });
  await panel.getByRole('button', { name: 'Digital client file', exact: true }).click();
  await expect(panel.getByRole('heading', { name: 'Digital client file' })).toBeVisible();
  await expect(panel.locator('.digital-client-file')).toContainText('Not provided');
  await expect(panel.locator('.digital-client-file')).toContainText('£1,800');
  await scan(page, 'digital client file');
  await panel.getByRole('button', { name: 'Case assistant', exact: true }).click();
  await panel.getByRole('button', { name: 'What are the client’s preferences?' }).click();
  await expect(panel.locator('.assistant-message.assistant')).toContainText('£1,800.00');
  await scan(page, 'case assistant');
  await panel.getByRole('button', { name: 'Agent work & audit', exact: true }).click();
  await expect(panel.getByText('Audit chain verified', { exact: false })).toBeVisible();
  await expect(panel.locator('.agent-work-item details[open]')).toHaveCount(5);
  await scan(page, 'readable agent audit');
  await panel.getByRole('button', { name: 'Case journey', exact: true }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await scan(page, 'policy selection mobile');
  expect(
    await panel.evaluate((element) => element.scrollWidth <= element.clientWidth + 1),
  ).toBeTruthy();
  await page.screenshot({ path: '.runtime/qa/automatic-selection-mobile.png', fullPage: true });
  await page.setViewportSize({ width: 1440, height: 1000 });
  const cards = panel.locator('.automatic-policy');
  const secondName = await cards.nth(1).getByRole('heading', { level: 4 }).innerText();
  for (let index = 0; index < 3; index++) await cards.nth(index).getByRole('checkbox').check();
  await panel.getByRole('button', { name: `Move ${secondName} up`, exact: true }).click();
  await panel.getByRole('button', { name: 'Confirm selection & prepare recommendation' }).click();
  await expect(
    panel.getByRole('heading', { name: 'Review once. Sign off when ready.' }),
  ).toBeVisible({ timeout: 20000 });
  await expect(panel.locator('.signed-policy-list > li').first()).toContainText(secondName);
  await expect(panel.getByRole('button', { name: 'Save review and continue' })).toHaveCount(0);
  await expect(panel.getByRole('checkbox')).toHaveCount(0);
  await scan(page, 'single final signoff desktop');
  await page.setViewportSize({ width: 390, height: 844 });
  await scan(page, 'single final signoff mobile');
  expect(
    await panel.evaluate((element) => element.scrollWidth <= element.clientWidth + 1),
  ).toBeTruthy();
  await panel.getByLabel('Confirm your password').fill('HelmDemo!2026');
  await panel.getByRole('button', { name: 'Sign off & deliver demo' }).click();
  await expect(panel.getByRole('heading', { name: 'Signed and delivered.' })).toBeVisible({
    timeout: 20000,
  });
  await expect(panel.locator('.agent-work-item.complete')).toHaveCount(5, { timeout: 20000 });
  await expect(panel.locator('.agent-work-item').last()).toContainText(
    'No model change was applied',
  );
  await scan(page, 'delivered and learning complete');
  await panel.getByRole('button', { name: 'Agent work & audit', exact: true }).click();
  await expect(
    panel.getByText('Automatic delivery after broker approval', { exact: true }),
  ).toBeVisible();
  await scan(page, 'completed case agent audit');
  await panel.getByRole('button', { name: 'Case journey', exact: true }).click();
  await page.screenshot({ path: '.runtime/qa/automatic-complete-mobile.png', fullPage: true });
  const id = page.url().split('/case/')[1];
  const current = await (await page.request.get(`/api/v1/cases/${id}`)).json();
  const decisions = current.events.filter((event) => event.payload.decision);
  expect(decisions.map((event) => event.payload.decision)).toEqual([1, 2]);
  expect(current.pack.survey.thumbs).toEqual({});
  expect(current.pack.broker_ratings).toBeUndefined();
  await expect(panel.getByRole('alert')).toHaveCount(0);
  expect(errors).toEqual([]);
});

test('durable agent jobs reach policy selection without opening the case', async ({ page }) => {
  await login(page);
  const csrf = (await page.context().cookies()).find((cookie) => cookie.name === 'helm_csrf').value;
  const response = await page.request.post('/api/v1/demo/journeys', {
    headers: { 'X-CSRF-Token': csrf },
  });
  expect(response.ok()).toBeTruthy();
  const item = await response.json();
  // Queue reads never process jobs. A completed state here proves a background worker,
  // rather than case detail polling, advanced the journey.
  await expect
    .poll(
      async () => {
        const listing = await (await page.request.get('/api/v1/cases?limit=50')).json();
        return listing.items.find((row) => row.id === item.id)?.state;
      },
      { timeout: 30000 },
    )
    .toBe('BROKER_REVIEW');
});
