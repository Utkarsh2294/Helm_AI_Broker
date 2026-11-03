import { test, expect } from '@playwright/test';

for (const viewport of [
  { width: 1440, height: 900 },
  { width: 390, height: 844 },
]) {
  test.describe(`Priority queue at ${viewport.width}px`, () => {
    test.use({ viewport });

    test('opens a separate ranked queue and returns there after case review', async ({ page }) => {
      const errors = [];
      page.on('pageerror', (error) => errors.push(error.message));
      await page.goto('/login?next=%2Fpriority-queue');
      await page.getByLabel('Email address').fill('broker@helm.demo');
      await page.getByLabel('Password', { exact: true }).fill('HelmDemo!2026');
      await page.getByRole('button', { name: 'Sign in to your workspace' }).click();
      await expect(page).toHaveURL(/\/priority-queue$/);
      await page.getByRole('button', { name: 'Back to workspace' }).click();
      await page.goto('/queue?age_range=10%2B');
      await page.getByLabel('Search cases').fill('no-matching-client-123');
      await page.getByLabel('Filter case status').selectOption('PUBLISHED');
      await page.getByLabel('Filter assignee').selectOption('me');
      await page.getByLabel('Filter priority').selectOption('urgent');
      await page.getByRole('button', { name: 'Review priority queue' }).click();
      await expect(page).toHaveURL(/\/priority-queue$/);
      const heading = page.getByRole('heading', { name: 'Priority queue', exact: true });
      await expect(heading).toBeFocused();
      await expect(
        page.locator('.metrics-grid, .workspace-bottom, .table-toolbar, .priority-banner'),
      ).toHaveCount(0);
      const rows = page.locator('.case-table tbody tr');
      await expect(rows.first()).toBeVisible();
      const scores = await page
        .locator('[data-priority-score]')
        .evaluateAll((elements) =>
          elements.map((element) => Number(element.dataset.priorityScore)),
        );
      expect(scores.length).toBeGreaterThan(0);
      expect(scores.every(Number.isFinite)).toBeTruthy();
      expect(scores).toEqual([...scores].sort((a, b) => b - a));
      expect(await page.locator('.priority-rank').allTextContents()).toEqual(
        scores.map((_, index) => `#${index + 1}`),
      );
      const expected = await (
        await page.request.get('/api/v1/cases?sort=priority&limit=50')
      ).json();
      expect(
        await rows.evaluateAll((elements) => elements.map((element) => element.dataset.caseId)),
      ).toEqual(expected.items.map((item) => item.id));
      expect(
        expected.items.every(
          (item) => item.state !== 'CLOSED' && (item.state !== 'PUBLISHED' || item.buying_href),
        ),
      ).toBeTruthy();

      await rows
        .first()
        .getByRole('button', { name: /^Open / })
        .click();
      if (expected.items[0].buying_href) {
        await expect(page).toHaveURL(new RegExp(expected.items[0].buying_href));
        await expect(
          page.getByRole('complementary', { name: 'Digital client file' }),
        ).toBeVisible();
        await page.getByRole('button', { name: 'Priority queue', exact: true }).click();
      } else {
        await expect(page.getByRole('dialog', { name: 'Case workspace' })).toBeVisible();
        await page.getByRole('button', { name: 'Close case', exact: true }).click();
      }
      await expect(page).toHaveURL(/\/priority-queue$/);
      await rows
        .first()
        .getByRole('button', { name: /^Audit trail for / })
        .click();
      await expect(page).toHaveURL(/view=audit/);
      await page.getByRole('button', { name: 'Close case', exact: true }).click();
      await expect(page).toHaveURL(/\/priority-queue$/);
      await page.reload();
      await expect(heading).toBeVisible();
      await expect(rows.first()).toBeVisible();
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
      ).toBeTruthy();
      await page.screenshot({
        path: `../../.runtime/qa/priority-page-${viewport.width}.png`,
        fullPage: true,
      });
      await page.getByRole('button', { name: 'Back to workspace' }).click();
      await expect(page).toHaveURL(/\/queue$/);
      await expect(page.getByRole('button', { name: 'Start automatic demo' })).toBeVisible();
      expect(errors).toEqual([]);
    });
  });
}
