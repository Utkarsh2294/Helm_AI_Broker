import { test, expect } from '@playwright/test';
import { createHmac } from 'node:crypto';

async function login(page, email = 'broker@helm.demo') {
  await page.goto('/');
  await page.getByLabel('Email address').fill(email);
  await page.getByLabel('Password', { exact: true }).fill('HelmDemo!2026');
  await page.getByRole('button', { name: 'Sign in to your workspace' }).click();
  await expect(page.getByRole('heading', { name: 'Good advice starts with clarity.' })).toBeVisible();
}

for (const [scenario, state, count] of [['happy', 'BROKER_REVIEW', 30], ['decline', 'BROKER_REVIEW', 24], ['late', 'BROKER_REVIEW', 24], ['arithmetic', 'PAUSED_NEEDS_HUMAN', 30], ['medical', 'PAUSED_NEEDS_HUMAN', 24], ['duplicate', 'BROKER_REVIEW', 30], ['referral', 'UW_REFERRAL', 24], ['injection', 'BROKER_REVIEW', 30]]) {
  test(`partner scenario ${scenario} reaches its guarded outcome`, async ({ page }) => {
    await login(page);
    await page.getByRole('button', { name: 'New demo request' }).click();
    const panel = page.getByRole('dialog', { name: 'Case workspace' });
    await panel.getByRole('checkbox', { name: 'I reviewed this fact-find', exact: false }).check();
    await panel.getByRole('button', { name: 'Sign off fact-find' }).click();
    await panel.getByLabel('Demo scenario').selectOption(scenario);
    const response = page.waitForResponse(r => r.url().endsWith('/release') && r.request().method() === 'POST');
    await panel.getByRole('button', { name: 'Release demo RFQ' }).click();
    const released = await (await response).json();
    await expect.poll(() => page.evaluate(async id => (await (await fetch(`/api/v1/cases/${id}`)).json()).state, released.id), { timeout: 25000 }).toBe(state);
    const current = await page.evaluate(async id => (await (await fetch(`/api/v1/cases/${id}`)).json()), released.id);
    expect(current.quotes.quotes).toHaveLength(count);
    expect(current.state).not.toBe('PUBLISHED');
    if (scenario === 'duplicate') expect(current.quotes.raw_quotes).toHaveLength(32);
    if (scenario === 'injection') expect(current.quotes.partners.some(p => p.injection_blocked)).toBe(true);
  });
}

test('keyboard command search, Quick Look and case filters work', async ({ page }) => {
  await login(page);
  await page.keyboard.press('Control+k');
  const palette = page.getByRole('dialog', { name: 'Search your workspace' });
  await palette.getByLabel('Command search').fill('Asha');
  await page.keyboard.press('Enter');
  await expect(page.getByRole('dialog', { name: 'Case workspace' })).toBeVisible();
  await page.keyboard.press('Escape');
  await page.getByRole('button').filter({ hasText: 'Asha Patel' }).first().focus();
  await page.keyboard.press('Space');
  await expect(page.getByRole('dialog', { name: 'Quick look', exact: true })).toBeVisible();
  await page.keyboard.press('Escape');
  await page.getByLabel('Sort cases').selectOption('name');
  await page.getByLabel('Filter priority').selectOption('normal');
  await page.getByRole('textbox', { name: 'Search cases' }).fill('No such fictional person');
  await expect(page.getByText('No matching cases')).toBeVisible();
});

test('a server-verified resident passkey can register and sign in', async ({ page }) => {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('WebAuthn.enable');
  const { authenticatorId } = await cdp.send('WebAuthn.addVirtualAuthenticator', { options: { protocol: 'ctap2', transport: 'internal', hasResidentKey: true, hasUserVerification: true, isUserVerified: true, automaticPresenceSimulation: true } });
  try {
    await login(page);
    await page.getByRole('button', { name: 'Security & devices', exact: true }).click();
    await page.getByRole('button', { name: 'Register a passkey' }).click();
    await expect(page.getByText('Passkey registered. You can use it on your next sign-in.')).toBeVisible();
    await page.getByRole('button', { name: 'Sign out' }).click();
    await page.getByRole('button', { name: 'Continue with passkey' }).click();
    await expect(page.getByRole('heading', { name: 'Good advice starts with clarity.' })).toBeVisible();
  } finally { await cdp.send('WebAuthn.removeVirtualAuthenticator', { authenticatorId }); }
});

function otp(secret, offset = 0) {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
  const bits = [...secret].map(c => alphabet.indexOf(c).toString(2).padStart(5, '0')).join('');
  const key = Buffer.from(bits.match(/.{8}/g).map(v => parseInt(v, 2)));
  const counter = Buffer.alloc(8); counter.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30000) + offset));
  const digest = createHmac('sha1', key).update(counter).digest(), start = digest[digest.length - 1] & 15;
  return ((digest.readUInt32BE(start) & 0x7fffffff) % 1000000).toString().padStart(6, '0');
}

test('TOTP enrollment requires the second factor on the next sign-in', async ({ page }) => {
  await login(page, 'lead@helm.demo');
  await page.getByRole('button', { name: 'Security & devices', exact: true }).click();
  await page.getByRole('button', { name: 'Set up authenticator' }).click();
  const secret = await page.locator('.secret-key').textContent();
  await page.getByLabel('Enrollment code').fill(otp(secret));
  await page.getByRole('button', { name: 'Verify and enable' }).click();
  await expect(page.getByText('Authenticator enabled. Store your recovery codes securely.')).toBeVisible();
  await page.getByRole('button', { name: 'Sign out' }).click();
  await page.getByLabel('Email address').fill('lead@helm.demo');
  await page.getByLabel('Password', { exact: true }).fill('HelmDemo!2026');
  await page.getByRole('button', { name: 'Sign in to your workspace' }).click();
  await page.getByLabel('Authenticator code', { exact: true }).fill(otp(secret, 1));
  await page.getByRole('button', { name: 'Sign in to your workspace' }).click();
  await expect(page.getByRole('heading', { name: 'Good advice starts with clarity.' })).toBeVisible();
});
