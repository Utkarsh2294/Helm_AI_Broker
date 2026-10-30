import { test, expect } from '@playwright/test';

for (const [reason, title] of [
  ['voluntary', "You've been signed out."],
  ['session-expired', 'Your session timed out for security.'],
  ['step-up-failed', 'Step-up verification failed.'],
]) {
  test(`signed-out screen ${reason} has a keyboard sign-in path`, async ({ page }) => {
    await page.goto(`/signed-out/${reason}`);
    await expect(page.getByRole('heading', { name: title })).toBeVisible();
    await page.getByRole('link', { name: 'Sign back in' }).focus();
    await page.keyboard.press('Enter');
    await expect(page.getByRole('heading', { name: 'Welcome back.' })).toBeVisible();
  });
}

test('login preserves a safe destination and never accepts external navigation', async ({
  page,
}) => {
  await page.goto('/login?next=%2Fagents');
  await page.getByRole('button', { name: 'Fill demo credentials' }).click();
  await page.getByRole('button', { name: 'Sign in to your workspace' }).click();
  await expect(page).toHaveURL(/\/agents$/);
  await page.getByRole('button', { name: 'Sign out' }).click();
  await expect(page).toHaveURL(/\/signed-out\/voluntary$/);
  await page.goto('/login?next=https%3A%2F%2Fevil.invalid');
  await page.getByRole('button', { name: 'Fill demo credentials' }).click();
  await page.getByRole('button', { name: 'Sign in to your workspace' }).click();
  await expect(page).toHaveURL(/\/queue$/);
});

test('credential changes require session re-authentication in the interface', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Fill demo credentials' }).click();
  await page.getByRole('button', { name: 'Sign in to your workspace' }).click();
  await page.getByRole('button', { name: 'Security & devices', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Register a passkey' })).toHaveCount(0);
  await page.getByLabel('Security verification password').fill('HelmDemo!2026');
  await page.getByRole('button', { name: 'Verify security changes' }).click();
  await expect(page.getByRole('button', { name: 'Register a passkey' })).toBeVisible();
});
