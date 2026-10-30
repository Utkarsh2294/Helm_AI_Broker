# Fictional document and pilot-review demonstration

The owner requested a document flow to showcase how the portal works instead of supplying real pilot identities and approvals. This is the accepted P11 demonstration scope. It does not mark real-customer release acceptance complete.

Open **Pilot showcase** at `http://127.0.0.1:5180/demo` after signing in. All supplied records are fictional. The separate broker and consumer codebases remain independent; local MockCore stands in for the consumer integration.

## Walkthrough

1. Sign in as `broker@helm.demo`, using the existing demo password `HelmDemo!2026`. Create the showcase case. The action is idempotent and leaves the case awaiting the normal fact-find review.
2. Download the renewal, IPID, ToBA, DPIA, adviser register, operations runbook and go/no-go sample PDFs. Every file is visibly labelled fictional and has a deterministic SHA-256 fingerprint. The parsed renewal is stored as encrypted source evidence.
3. Open the showcase case. Verify access to sensitive documents with your password/passkey, then upload the renewal PDF. Supported PDFs must have a text layer; scanned images need human transcription. Uploads do not alter the fact-find automatically. Check every sourced fact before G0.
4. Sign G0 and explicitly release G1. Five standalone fictional partners supply quotations. Save a star rating, Recommend/Exclude/Refer decision and your own reason for each plan. A saved recommended plan can be selected immediately; your choices stay selected while you assess the others. The comparison guide shows the saved/selected counts and jumps to the next unfinished plan. Finish all five assessments and choose exactly three, then click **Continue to recommendation** and give the short selection feedback.
5. Review the suitability statement, then follow **Client needs → Selected plans → Final confirmation**. Each selected plan shows its readable name and listed gaps with one explicit confirmation covering that plan and those gaps. Click **Save review and continue**. Password approval appears only when the current review is saved; an available passkey is an optional alternative. Re-authenticate and approve G2. In Compose, a committed outbox and a separate worker deliver to MockCore. No real insurer or consumer is contacted.
6. Close the case panel and sign out completely. Sign in as `compliance@helm.demo`, open Pilot showcase, inspect the documents/evidence, complete the document and scope checklist, and verify that persona's review.
7. Sign out and repeat as `legal@helm.demo`. This fictional legal persona cannot approve G2 or obtain general medical access. Both review decisions are bound to the current document manifest, published pack and verified audit chain. Changed evidence requires a new review.
8. Download the review record PDF. It records the actual demo reviewers and fingerprints, and always states **LIVE RELEASE APPROVED: FALSE**.

Additional paths: exclude every plan to close without advice and generate a closure PDF; refer a plan for fictional underwriter clarification, then reassess it; record a complaint to halt work until the designated compliance owner resolves it. Case controls allow reasoned priority changes, lead reassignment and takeover of paused cases without resuming them.

## Operational rehearsal

`tools/demo_recovery.py` takes a consistent SQLite backup, encrypts the database and its existing encryption key with a separate passphrase, and restores only into a new directory. It verifies SQLite integrity, every audit-chain event, and decryption/hash consistency of every snapshot before accepting the restore. Existing directories and backup files are never overwritten.

For the local SQLite demo, run from PowerShell 7:

```powershell
$brokerPython = Join-Path $env:LOCALAPPDATA 'HelmBroker\venv\Scripts\python.exe'
$env:HELM_BACKUP_PASSPHRASE = Read-Host 'Separate backup passphrase (at least 20 characters)' -MaskInput
try {
    & $brokerPython tools/demo_recovery.py backup --database .runtime/broker.db --key-file .runtime/demo.key --bundle .runtime/demo-backup.helm
    & $brokerPython tools/demo_recovery.py restore --bundle .runtime/demo-backup.helm --directory .runtime/demo-restored
} finally {
    Remove-Item Env:HELM_BACKUP_PASSPHRASE
}
```

Choose new output names for a later rehearsal. Store the passphrase separately if retaining a backup; the automatically executed QA rehearsal used an ephemeral passphrase and is not a retained recovery service. [Executed recovery evidence](verification/demo-recovery.json) records counts and timings without keys or customer text.

Nightly verification writes local create-once anchor copies under `HELM_AUDIT_ANCHOR_DIRECTORY`. Changed copies or missing anchored history create a metadata-only P1 alert file and critical log entry. This demonstrates detection and escalation locally; an administrator can still alter local files. External object lock, paging, KMS rotation, PostgreSQL PITR/off-site backups and real incident ownership remain deployment gates.

## Honest completion boundary

The local five-agent and document-review journeys are executable demonstrations. Real FCA identities, policy terms, legal/DPO/compliance sign-off, representative model/OCR evaluation, manual assistive-technology acceptance, production integrations and unresolved strict security/performance gates are not fabricated. See [the full-plan audit](phases/FULL_PLAN_AUDIT.md), [phase ledger](phases/MAIN_PHASES.md) and [live pilot handover](PILOT_READINESS.md).
