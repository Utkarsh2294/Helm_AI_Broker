import React, { useState } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import Input from './Input';
import Button from './Button';
import StarRating from './StarRating';
import PlanDecisionButton from './PlanDecisionButton';
import MfaCodeInput from './MfaCodeInput';
import TextArea from './TextArea';
import Avatar from './Avatar';
import BottomSheet from './BottomSheet';
import { safeNext } from '../auth-pages';

afterEach(cleanup);
describe('accessible shared controls', () => {
  it('labels a password, reveals it and links the error', () => {
    render(
      <Input label="Work password" type="password" defaultValue="fictional" error="Try again" />,
    );
    const input = screen.getByLabelText('Work password');
    expect(input.type).toBe('password');
    fireEvent.click(screen.getByRole('button', { name: 'Show password' }));
    expect(input.type).toBe('text');
    expect(document.getElementById(input.getAttribute('aria-describedby')).textContent).toBe(
      'Try again',
    );
  });
  it('blocks repeated button actions while loading', () => {
    const click = vi.fn();
    render(
      <Button loading onClick={click}>
        Save
      </Button>,
    );
    fireEvent.click(screen.getByRole('button'));
    expect(click).not.toHaveBeenCalled();
    expect(screen.getByRole('button').disabled).toBe(true);
  });
  it('supports star keyboard boundaries and native radio decisions', () => {
    function Rating() {
      const [stars, setStars] = useState(null),
        [decision, setDecision] = useState(null);
      return (
        <>
          <StarRating value={stars} onChange={setStars} />
          <PlanDecisionButton value={decision} onChange={setDecision} />
        </>
      );
    }
    render(<Rating />);
    const slider = screen.getByRole('slider');
    fireEvent.keyDown(slider, { key: 'End' });
    expect(slider.value).toBe('5');
    fireEvent.keyDown(slider, { key: 'ArrowRight' });
    expect(slider.value).toBe('5');
    fireEvent.click(screen.getByRole('radio', { name: 'Exclude' }));
    expect(screen.getByRole('radio', { name: 'Exclude' }).checked).toBe(true);
  });
  it('accepts a pasted MFA code and submits exactly once', () => {
    const complete = vi.fn();
    function Code() {
      const [value, setValue] = useState('');
      return <MfaCodeInput value={value} onChange={setValue} onComplete={complete} />;
    }
    render(<Code />);
    fireEvent.paste(screen.getByLabelText('Digit 1 of 6'), {
      clipboardData: { getData: () => '123456' },
    });
    expect(complete).toHaveBeenCalledExactlyOnceWith('123456');
    expect(screen.getByLabelText('Digit 6 of 6').value).toBe('6');
  });
  it('exposes minimum reason length and handles one-word avatar names', () => {
    render(
      <>
        <TextArea label="Reason" value="Short" onChange={() => {}} minLength={20} />
        <Avatar name="Asha" />
      </>,
    );
    fireEvent.blur(screen.getByLabelText('Reason'));
    expect(screen.getByText(/Minimum 20 characters/)).toBeTruthy();
    expect(screen.getByRole('img', { name: 'Asha' }).textContent).toBe('A');
  });
  it('opens an accessible dialog and closes with Escape', () => {
    const close = vi.fn();
    render(
      <BottomSheet open onClose={close} title="Identity check" description="Verify to continue">
        <Input label="Code" />
      </BottomSheet>,
    );
    expect(screen.getByRole('dialog', { name: 'Identity check' })).toBeTruthy();
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(close).toHaveBeenCalledOnce();
  });
  it('keeps login return navigation inside the known application routes', () => {
    expect(safeNext('/security')).toBe('/security');
    expect(safeNext('/case/fictional')).toBe('/case/fictional');
    for (const target of [
      '//evil.invalid',
      '/\\evil.invalid',
      'https://evil.invalid',
      '/login',
      '/queue\\evil',
    ])
      expect(safeNext(target)).toBe('/queue');
  });
});
