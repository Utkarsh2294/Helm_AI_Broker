import React from 'react';
import { afterAll, afterEach, beforeAll, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import GuidedReview, { reviewComplete } from './GuidedReview';
import { api } from '../api';

vi.mock('../api', async (original) => ({ ...(await original()), api: vi.fn() }));
beforeAll(() =>
  Object.defineProperty(Element.prototype, 'scrollIntoView', {
    configurable: true,
    value: vi.fn(),
  }),
);
afterAll(() => {
  delete Element.prototype.scrollIntoView;
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});
const pack = {
  selected: ['a', 'b', 'c'],
  suitability_final: 'Reviewed fictional statement.',
  plans: ['a', 'b', 'c'].map((id) => ({ plan: { id, name: `Plan ${id.toUpperCase()}` } })),
  suitability_assessments: ['a', 'b', 'c'].map((plan_id) => ({
    plan_id,
    gaps: plan_id === 'a' ? ['Outpatient benefit below requested level.'] : [],
  })),
  unmet_needs: [{ plan_id: 'a', need: 'outpatient' }],
};

it('guides explicit human review through three steps and saves every required confirmation together', async () => {
  const onSaved = vi.fn();
  api.mockResolvedValue({ pack: { ...pack } });
  render(<GuidedReview item={{ id: 'fictional', pack }} onSaved={onSaved} onError={vi.fn()} />);
  expect(screen.queryByRole('button', { name: 'Save review and continue' })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Continue to selected plans' }));
  expect(screen.getByRole('alert').textContent).toContain('5 remaining');
  expect(api).not.toHaveBeenCalled();
  for (const input of screen.getAllByRole('checkbox')) fireEvent.click(input);
  fireEvent.click(screen.getByRole('button', { name: 'Continue to selected plans' }));
  expect(screen.getByText('Outpatient benefit below requested level.')).toBeTruthy();
  expect(screen.getAllByRole('checkbox').every((input) => !input.checked)).toBe(true);
  fireEvent.click(screen.getByRole('button', { name: 'Continue to final confirmation' }));
  expect(screen.getByRole('alert').textContent).toContain('3 remaining selected plans');
  for (const input of screen.getAllByRole('checkbox')) fireEvent.click(input);
  fireEvent.click(screen.getByRole('button', { name: 'Continue to final confirmation' }));
  fireEvent.click(screen.getByRole('button', { name: 'Save review and continue' }));
  expect(api).not.toHaveBeenCalled();
  expect(screen.getByRole('alert').textContent).toContain(
    'Confirm that the selected plans represent your advice',
  );
  fireEvent.click(screen.getByRole('checkbox'));
  fireEvent.click(screen.getByRole('button', { name: 'Save review and continue' }));
  await waitFor(() => expect(onSaved).toHaveBeenCalledOnce());
  const body = api.mock.calls[0][1].body;
  expect(body.dnr_sections_confirmed).toHaveLength(5);
  expect(body.suitability_confirmed_plans).toEqual(['a', 'b', 'c']);
  expect(body.unmet_needs_addressed).toEqual(['a:outpatient']);
  expect(body.overall_suitability_confirmed).toBe(true);
  expect(reviewComplete({ ...pack, ...body })).toBe(true);
  expect(reviewComplete({ ...pack, ...body, unmet_needs_addressed: [] })).toBe(false);
});

it('resumes saved review and lets the broker reopen it without silently confirming gaps', () => {
  const saved = {
    ...pack,
    dnr_sections_confirmed: ['priorities', 'coverage', 'budget', 'household', 'medical_flag'],
    suitability_confirmed_plans: ['a', 'b', 'c'],
    unmet_needs_addressed: ['a:outpatient'],
    overall_suitability_confirmed: true,
  };
  const onEditing = vi.fn();
  render(
    <GuidedReview
      item={{ id: 'fictional', pack: saved }}
      onSaved={vi.fn()}
      onError={vi.fn()}
      onEditing={onEditing}
    />,
  );
  expect(screen.getByRole('heading', { name: 'Review saved. Ready to approve.' })).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Edit review confirmations' }));
  expect(onEditing).toHaveBeenCalledOnce();
  fireEvent.click(screen.getByRole('button', { name: 'Continue to selected plans' }));
  fireEvent.click(screen.getAllByRole('checkbox')[0]);
  fireEvent.click(screen.getByRole('button', { name: 'Continue to final confirmation' }));
  expect(screen.getByRole('alert').textContent).toContain('1 remaining selected plans');
  expect(api).not.toHaveBeenCalled();
});
