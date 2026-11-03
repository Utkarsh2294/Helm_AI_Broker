# Policy Buying demonstration

This continues the published recommendation through a consumer's explicit choice,
document review, underwriting, fictional banking, final package review and mock
policy issuance. It implements PB-0 through PB-6 from the supplied workflow.
The original recommendation journey retains its two broker decisions. Buying
adds the document approvals requested in the new specification.

## Open the prototype

The Docker demonstration runs at http://localhost:5184. Sign in with the existing
fictional broker account, `broker@helm.demo` / `HelmDemo!2026`.

On another checkout, run `powershell -NoProfile -File scripts/start.ps1 -Install`
for the local preview at http://127.0.0.1:5180. The scripts install the locked
dependencies outside OneDrive and migrate the database. Use the documented
Compose setup for PostgreSQL/Redis and HTTP partner simulation.

## Walk through either underwriting path

1. Open **Policy Buying** in the navigation. Choose **Start Moratorium demo** or
   **Start FMU demo**. This creates a predefined fictional consumer fact-find;
   it does not change a real consumer's underwriting preference.
2. Agents prepare quotations and ranking automatically. Complete the existing
   broker decisions: choose and order three policies, then review and authenticate
   the recommendation's final sign-off. No broker ratings or approvals are
   invented by the buying coordinator.
3. In the published case, find **Which plan would the consumer like to proceed
   with?** Choose one shortlisted quote and click **Simulate: proceed with this
   plan**. This explicit action binds the choice to the published pack hash.
   A quote with a different underwriting basis is rejected rather than silently
   changing the recorded preference.
4. The dedicated buying workspace opens. The client file shows existing supplied
   details and the original underwriting basis. Missing details remain **Not
   supplied**. The stepper tracks eight stages. Read and acknowledge the baseline.
5. Review the automatically prepared IPID, TOBA and the applicable declaration.
   The current document is expanded; earlier documents remain available. PDFs
   contain the demo watermark on every page. The IPID targets two pages and is
   rejected if an edited version exceeds three pages; factual content is not cut.
6. For the IPID, use **Approve & Send**, then **Simulate: consumer confirms**.
   Alternatively, enter a correction request and simulate that response. The
   broker must prepare and send a new version before confirmation can continue.
7. Review and send the TOBA, then simulate its separate acknowledgement. The
   consumer cannot edit this broker statement. An unchanged TOBA can reuse a
   recorded standing acceptance for the same stable consumer reference. Matching
   names alone never establish that identity; a changed TOBA needs new acceptance.
8. Complete the applicable underwriting step:
   - **Moratorium:** send the declaration and simulate its explicit acceptance
     and signature. Then choose **Approve underwriting declaration**.
   - **FMU:** send the blank questionnaire and simulate fresh, seeded answers and
     a signature. Choose **Verify to view completed FMU answers**, authenticate,
     and review the untouched fictional answers. Then approve the declaration.
     The existing case consent and medical-access permission are required.
9. The banking request appears automatically after broker underwriting approval.
   Simulate the consumer's fictional account and mandate consent. Open the
   **one-time banking verification**, authenticate, inspect the dummy values and
   confirm the payment setup. The raw view hides after 30 seconds and can only
   be revealed once for that response. Other views show account ending **1234**.
   A later document revision creates a fresh request when banking must be repeated.
10. Choose **Review & Send** in the final submission section. The read-only preview
    lists the accepted document versions and a non-medical cover note. Links open
    individual documents for review. Editing a document invalidates affected
    confirmations and the package review; complete those steps again.
11. Choose **Send to mock insurer**. The adapter returns immediately with a
    `DEMO-{insurer}-{8 digits}` policy number. Repeating the same request returns
    the original issuance instead of creating another policy.
12. The case is green-flagged in **Closed Cases**. Open its local confirmation
    message and download the final accepted IPID. This is a saved demonstration
    email, not a message sent to an external mailbox.

## Review, edit and query

**Edit manually** provides section blocks, basic bold/italic formatting and a
formatted preview. Required headings are preserved. Saving creates a new encrypted
version, tagged as broker edited; it does not replace evidence. Prior versions can
be downloaded from **Document version history**. The required core Moratorium
declaration remains protected from wording changes.

**Request AI changes** uses the user's existing local-demo choice. No external model
is enabled. Its deterministic instruction format is:

```
Section Where am I covered?: UK-only fictional treatment; consult the insurer terms.
```

Use an exact displayed heading followed by the replacement wording. Unsupported
free-form instructions return an explanation and leave the draft unchanged. A
future approved model provider would be needed for unrestricted AI rewriting.

## Updates, priorities and assistance

- The saved per-case feed supplies the list's Updates badge and existing
  notification bell/SSE pipeline. **Mark updates read** affects only this broker's
  read position. The workspace shows the latest 100 feed entries; immutable
  audit metadata remains available through the case audit trail.
- Consumer corrections and returned declarations contribute the same priority
  weight as a halted case. Priority queue entries open the buying workspace.
  The existing Task Copilot adds IPID-response, declaration and submission review
  cards, with existing snooze and explanation behaviour.
- **Ask assistant about this case** uses the same case-scoped assistant. It can
  report buying stages, selected plan and document statuses. Completed FMU
  answers and raw banking details are excluded from its context.
- The communication thread shows sent documents, consumer responses and edits.
  Approval events are recorded before the automatic steps they trigger.
- Source-case complaint holds stop buying mutations. Case ownership and reviewer
  permissions apply to list, detail, document downloads and every action.

## Demo and data boundaries

There is no live consumer connection, real insurer submission, payment collection
or external confirmation email. The consumer endpoints are broker-authenticated
simulation controls, not a public consumer portal. No real electronic signature,
FCA registration or coverage decision is claimed.

Medical responses and banking bodies use the existing AES-256-GCM encrypted
storage. Bank details use that implementation rather than assuming that pgcrypto
provides an interchangeable AES-GCM primitive. Medical answers require the existing
consent and time-limited, session-bound medical-access grant. Completed answers
never become agent inputs or generic document exports. The mock package holds
immutable references to sealed medical attachments and masked banking summaries.

Documents are structurally illustrative, not legal approval or genuine insurer
wording. Benefit amounts absent from a quote are stated as missing. Cancellation
wording is qualified rather than asserting that every product has identical rights.
Real terms, authorisations, privacy arrangements and external integrations require
separate implementation and review before any live use.

Reference checks used during this implementation:

- [FCA IPID handbook entry](https://handbook.fca.org.uk/handbook/ICOBS/6/Annex3.html)
  and [cancellation entry](https://handbook.fca.org.uk/handbook/ICOBS/7/1.html):
  the current site requires JavaScript, so these links do not establish a completed
  legal review of the generated fixtures.
- [Financial Ombudsman complaint guidance](https://www.financial-ombudsman.org.uk/consumers/how-to-complain):
  most complaints have an eight-week business response period, with other limits
  for particular complaint types; the usual final-response referral period is six months.

See the [acceptance record](verification/POLICY_BUYING_2026-11-04.md) for measured
checks and the [implementation checkpoints](POLICY_BUYING_IMPLEMENTATION.md).
