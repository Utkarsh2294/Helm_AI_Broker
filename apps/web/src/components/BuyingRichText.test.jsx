import React from 'react';
import { render, screen, cleanup } from '@testing-library/react';
import { afterEach, test, expect } from 'vitest';
import { RichText } from './BuyingRichText';
afterEach(cleanup);
test('renders approved inline formatting while keeping HTML inert', () => {
  const { container } = render(
    <RichText value={'**Cover** and *terms* <img src=x onerror=alert(1)>'} />,
  );
  expect(container.querySelector('strong').textContent).toBe('Cover');
  expect(container.querySelector('em').textContent).toBe('terms');
  expect(container.querySelector('img')).toBeNull();
  expect(screen.getByText(/<img/)).toBeTruthy();
});
