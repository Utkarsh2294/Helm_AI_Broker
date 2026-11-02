import { test, expect } from '@playwright/test';

for (const viewport of [
  { width: 1440, height: 900 },
  { width: 390, height: 844 },
]) {
  test.describe(`Priority queue at ${viewport.width}px`, () => {
    test.use({ viewport });

    test('clears old filters, focuses the queue and works on repeated clicks', async ({ page }) => {
      const errors = [];
      page.on('pageerror', (error) => errors.push(error.message));
      await page.goto('/login');
      await page.getByLabel('Email address').fill('broker@helm.demo');
      await page.getByLabel('Password', { exact: true }).fill('HelmDemo!2026');
      await page.getByRole('button', { name: 'Sign in to your workspace' }).click();
      await expect(page.getByRole('button', { name: 'Start automatic demo' })).toBeVisible();
      await page.goto('/queue?age_range=10%2B');
      await page.getByLabel('Search cases').fill('no-matching-client-123');
      await page.getByLabel('Filter case status').selectOption('PUBLISHED');
      await page.getByLabel('Filter assignee').selectOption('me');
      await page.getByLabel('Filter priority').selectOption('urgent');

      for (let click = 0; click < 2; click++) {
        await page.getByRole('button', { name: 'Review priority queue' }).click();
        await expect(page).toHaveURL(/\/queue\?sort=priority#casework$/);
        await expect(page.getByLabel('Sort cases')).toHaveValue('priority');
        for (const label of [
          'Search cases',
          'Filter case status',
          'Filter assignee',
          'Filter priority',
        ]) {
          await expect(page.getByLabel(label)).toHaveValue('');
        }
        const heading = page.getByRole('heading', { name: 'Your priority queue', exact: true });
        await expect(heading).toBeFocused();
        const box = await heading.boundingBox();
        expect(box.y).toBeGreaterThanOrEqual(0);
        expect(box.y).toBeLessThan(viewport.height / 2);
        expect(
          await heading.evaluate((element) => {
            const rect = element.getBoundingClientRect();
            return element.contains(
              document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2),
            );
          }),
        ).toBeTruthy();
        await expect(page.getByRole('status')).toContainText('highest task priority first');
        await expect(page.locator('.case-table tbody tr').first()).toBeVisible();
        if (click === 0) await page.getByLabel('Search cases').fill('no-matching-client-123');
      }
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
      ).toBeTruthy();
      await page.screenshot({
        path: `../../.runtime/qa/priority-queue-${viewport.width}.png`,
        fullPage: true,
      });
      expect(errors).toEqual([]);
    });
  });
}
