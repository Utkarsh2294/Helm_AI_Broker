import React from 'react';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import BuyingBanking from './BuyingBanking';

vi.mock('../api', () => ({
  api: vi.fn(async () => ({
    account_holder: 'Fictional',
    sort_code: '000000',
    account_number: '00001234',
  })),
}));
vi.mock('./Reauthenticate', () => ({
  default: ({ onVerified }) => <button onClick={() => onVerified('proof')}>Test reveal</button>,
}));
afterEach(cleanup);

test('confirmation stays disabled until the revealed case version is refreshed', async () => {
  let finishRefresh;
  const refresh = new Promise((resolve) => {
    finishRefresh = resolve;
  });
  const item = {
    case_id: 'demo',
    version: 7,
    stage: 'AWAITING_BANKING_DETAILS',
    banking_received: true,
    documents: [{ doc_type: 'banking_request', id: 'request' }],
  };
  render(<BuyingBanking item={item} onChanged={() => refresh} />);
  fireEvent.click(screen.getByRole('button', { name: 'Open one-time banking verification' }));
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: 'Test reveal' }));
  });
  expect(screen.getByRole('button', { name: 'Confirm fictional payment setup' }).disabled).toBe(
    true,
  );
  expect(screen.queryByText(/Dummy account number/)).toBeNull();
  await act(async () => {
    finishRefresh();
    await refresh;
  });
  expect(await screen.findByText('Dummy account number: 00001234')).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Confirm fictional payment setup' }).disabled).toBe(
    false,
  );
});
