import React, { useState } from 'react';
import { api } from '../api';
import BottomSheet from './BottomSheet';
import TextArea from './TextArea';

export default function ReferralControls({ item, ratings, container, onSaved }) {
  const [open, setOpen] = useState(false),
    [reason, setReason] = useState(''),
    [reference, setReference] = useState(''),
    [confirmed, setConfirmed] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  const pending = item.state === 'UW_REFERRAL' && item.broker_referral;
  const referred = Object.values(ratings)
    .filter((rating) => rating.decision === 'REFER')
    .map((rating) => rating.plan_id);
  if (!pending && (item.state !== 'BROKER_REVIEW' || !referred.length)) return null;
  async function save(event) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      await api(`/cases/${item.id}/referrals${pending ? '/resolve' : ''}`, {
        method: 'POST',
        body: pending
          ? {
              referral_hash: item.broker_referral_hash,
              underwriter_reference: reference.trim(),
              reason: reason.trim(),
              fictional_confirmation: confirmed,
            }
          : { ranking_id: item.ranking.id, plan_ids: referred, reason: reason.trim() },
      });
      setOpen(false);
      setReason('');
      await onSaved();
    } catch (cause) {
      setError(cause.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className="notice warning">
        <div>
          <strong>
            {pending
              ? 'Underwriter review pending · G3'
              : `${referred.length} plans marked for underwriter referral`}
          </strong>
          <p>
            {pending
              ? 'Agents are on hold. Record the fictional underwriter confirmation, then reassess the original plans.'
              : 'Create a documented referral before continuing. No external message is sent by this demo.'}
          </p>
          <button className="button" onClick={() => setOpen(true)}>
            {pending ? 'Resolve demo referral' : 'Refer marked plans'}
          </button>
        </div>
      </div>
      <BottomSheet
        open={open}
        onClose={() => !busy && setOpen(false)}
        container={container}
        title={pending ? 'Record fictional underwriter response' : 'Request underwriter review'}
        description="The original quotation and ranking evidence stay unchanged. A referral never confirms medical cover."
      >
        <form onSubmit={save}>
          {pending && (
            <label>
              Fictional underwriter reference
              <input
                value={reference}
                maxLength={200}
                required
                onChange={(event) => setReference(event.target.value)}
              />
            </label>
          )}
          <TextArea
            label={pending ? 'Referral resolution reason' : 'Referral reason'}
            required
            minLength={pending ? 30 : 20}
            maxLength={2000}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
          />
          {pending && (
            <label className="check-row">
              <input
                type="checkbox"
                checked={confirmed}
                onChange={(event) => setConfirmed(event.target.checked)}
              />
              This is a fictional underwriter confirmation for the demonstration only.
            </label>
          )}
          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}
          <button
            className="button primary"
            disabled={
              busy ||
              reason.trim().length < (pending ? 30 : 20) ||
              (pending && (!confirmed || reference.trim().length < 3))
            }
          >
            {pending ? 'Record response and return to comparison' : 'Create referral and hold case'}
          </button>
        </form>
      </BottomSheet>
    </>
  );
}
