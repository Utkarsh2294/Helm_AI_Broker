import { test, expect } from '@playwright/test';
test('light workspace remains readable even when the device prefers dark mode', async ({
  page,
}) => {
  await page.emulateMedia({ colorScheme: 'dark' });
  await page.addInitScript(() => {
    localStorage.setItem('helm-theme', 'dark');
    localStorage.setItem('helm-theme-policy', 'light-default-v2');
  });
  await page.setViewportSize({ width: 1440, height: 1050 });
  await page.goto('/');
  await page.getByRole('button', { name: 'Fill demo credentials' }).click();
  await page.getByRole('button', { name: 'Sign in to your workspace' }).click();
  await expect(
    page.getByRole('heading', { name: 'Good advice starts with clarity.' }),
  ).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  await expect(page.getByRole('button', { name: /Switch to .* mode/ })).toHaveCount(0);
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  await expect(page.getByRole('button', { name: 'Start automatic demo' })).toBeVisible();
  const colours = await page.evaluate(() => {
    const style = (el) => {
      const c = getComputedStyle(el);
      return { text: c.color, background: c.backgroundColor };
    };
    return {
      content: style(document.querySelector('.main-content')),
      action: style(
        [...document.querySelectorAll('button')].find((b) =>
          b.textContent.includes('Start automatic demo'),
        ),
      ),
      muted: getComputedStyle(document.querySelector('.main-content .muted')).color,
    };
  });
  function luminance(rgb) {
    const values = rgb
      .match(/[\d.]+/g)
      .slice(0, 3)
      .map(Number)
      .map((v) => {
        v /= 255;
        return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
      });
    return values[0] * 0.2126 + values[1] * 0.7152 + values[2] * 0.0722;
  }
  const contrast = (a, b) =>
    (Math.max(luminance(a), luminance(b)) + 0.05) / (Math.min(luminance(a), luminance(b)) + 0.05);
  expect(contrast(colours.content.text, colours.content.background)).toBeGreaterThanOrEqual(4.5);
  expect(contrast(colours.muted, colours.content.background)).toBeGreaterThanOrEqual(4.5);
  expect(contrast(colours.action.text, colours.action.background)).toBeGreaterThanOrEqual(4.5);
  await page.screenshot({ path: '../../.runtime/qa/light-workspace.png', fullPage: true });
});
