import { test, expect } from '@playwright/test';
import { createRequire } from 'node:module';
import { writeFile } from 'node:fs/promises';
const require = createRequire(import.meta.url),
  reports = [];
// Instrumentation only; the application's shipped CSP stays enforced for users.
test.use({ bypassCSP: true });

async function scan(page, name) {
  await page.addScriptTag({ path: require.resolve('axe-core/axe.min.js') });
  const result = await page.evaluate(async () => {
    const result = await window.axe.run(document, {
      runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'] },
    });
    return result.violations.map((item) => ({
      id: item.id,
      impact: item.impact,
      targets: item.nodes.map((node) => node.target),
    }));
  });
  reports.push({ screen: name, violations: result });
}
test.afterAll(async () =>
  writeFile(
    new URL('../../../.runtime/qa/axe-report.json', import.meta.url),
    JSON.stringify(reports, null, 2),
  ),
);

test('WCAG automated checks cover authentication, all workspace routes and an open fact-find', async ({
  page,
}) => {
  test.setTimeout(120000);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/login');
  await expect(page.getByLabel('Email address')).toBeVisible();
  await scan(page, 'login');
  await page.getByRole('button', { name: 'Fill demo credentials' }).click();
  await page.getByRole('button', { name: 'Sign in to your workspace' }).click();
  await expect(
    page.getByRole('heading', { name: 'Good advice starts with clarity.' }),
  ).toBeVisible();
  for (const path of ['/queue', '/partners', '/learning', '/security']) {
    await page.goto(path);
    await expect(page.locator('main h1, main h2').first()).toBeVisible();
    await scan(page, path);
  }
  const list = await (await page.request.get('/api/v1/cases?limit=1')).json();
  await page.goto('/case/' + list.items[0].id);
  await expect(page.getByRole('dialog', { name: 'Case workspace' })).toBeVisible();
  await scan(page, 'case fact-find');
  expect(reports.filter((report) => report.violations.length)).toEqual([]);
});
