import { expect } from '@playwright/test';

// Exception/legacy gate tests keep their explicit G0/G1 fixture. The primary UI
// starts the new two-decision journey, which has its own end-to-end coverage.
export async function openManualCase(page) {
  const csrf = (await page.context().cookies()).find(
    (cookie) => cookie.name === 'helm_csrf',
  )?.value;
  const response = await page.request.post('/api/v1/demo/requests', {
    headers: { 'X-CSRF-Token': csrf },
    data: {
      id: `manual-browser-${crypto.randomUUID()}`,
      name: 'Manual demo applicant',
      cover_type: 'individual',
      needs: {
        budget_annual_pence: 180000,
        coverage: { cancer: { level: 3, must_have: true }, outpatient: { level: 3 } },
      },
    },
  });
  expect(response.ok(), await response.text()).toBeTruthy();
  const item = await response.json();
  await page.goto(`/case/${item.id}`);
}
