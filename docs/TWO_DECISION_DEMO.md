# Automatic broker demonstration

This is the owner's 31 October workflow update. It adds an automatic fictional
journey to the existing main-plan prototype. It does not establish live customer,
insurer, legal or FCA authority. The existing manual showcase remains available
for its G0/G1 and exception scenarios.

## Run the demonstration

1. Start PostgreSQL/Redis if needed with `docker compose up -d postgres redis`.
2. Run `scripts/start.ps1`. It starts the website, API and the local background
   runner for automatic demo cases. The seven-service Compose stack uses its Arq
   worker instead. Existing databases, cases and keys are retained.
3. Open <http://127.0.0.1:5180/> and sign in as `broker@helm.demo` with
   `HelmDemo!2026`. An enrolled authenticator remains required for that account.
4. Press **Start automatic demo**. The generated Morgan Demo case opens. Leave it
   open to watch, or close it: durable jobs continue preparing it in the background.
5. **Human decision 1:** choose three policies, review their displayed gaps and put
   them in preference order. The order of selection is the initial order; arrow
   controls change it. Press **Confirm selection & prepare recommendation**.
6. Agent 4 prepares the recommendation automatically. Read the client facts,
   budget, benefit levels, chosen policy order, statement, gaps and disclosures.
7. **Human decision 2:** enter the password, or the enrolled authenticator code,
   and press **Sign off & deliver demo**. That gesture explicitly confirms the
   displayed review declaration and signs this recommendation version. There is
   no separate stars form, feedback survey, fact-find/release button, saved
   checklist or automatic signature in this journey.
8. Delivery is recorded locally, or acknowledged by MockCore when enabled. Agent
   5 evaluates the actual policy choices automatically. An insufficient-evidence
   result is valid; a small demonstration does not justify a learned model.

## Inspect the workspace

**Agent work & audit** shows all five agents, waiting/running/complete/held status,
their purpose, saved output, timestamp and evidence reference. Expanded events
distinguish automatic preparation, agent outputs and human decisions. The audit
chain is verified from persisted events. Evidence can be downloaded as JSON.

**Digital client file** shows available identity facts, preferences, priority order,
budget, benefit targets, consent, source references, document metadata, versioned
workflow records, selected policies and delivery/response history. A missing date
of birth, contact information or clinical history is labelled as not supplied.
Sensitive statements and original uploaded documents retain verified case access.
This is a case file, not an invented clinical record or a cross-case identity match.

**Case assistant** answers questions about the open case's saved requirements,
ranking, agent work, documents and next action, with links back to its sources.
Use a policy's full name to get its saved explanation. It is a local, evidence-based
assistant with bounded question handling; it does not call a paid language model,
execute instructions, select policies or approve advice. Conversation stays in
the open case view. **Workspace assistant** summarises only cases the signed-in
user can access and links to them.

## Agent responsibilities

| Agent | Automatic work | Why it is needed |
|---|---|---|
| 1 Research | Extract source facts and demands/needs | Ground later work in the client's stated requirements |
| 2 Quotations | Prepare a minimised simulator RFQ and collect checked replies | Obtain comparable policy evidence from eligible fictional partners |
| 3 Ranking | Apply the existing ranking engine and save explanations | Show fit, balance and trade-offs against saved priorities |
| 4 Review | Draft a three-policy recommendation in the broker's order | Expose the statement, terms and gaps before signature |
| 5 Learning | Evaluate authentic ordered choices after delivery | Record evidence or a bounded proposal without activating model changes |

## Control boundaries

The server creates this flow from a fixed safe fictional fixture; a normal case
cannot opt into it by using a request-ID prefix. Automatic preparation is bound to
the original request and current fact-find hash. Only fictional simulator partners
are permitted. No G0/G1 human approvals, star ratings, written reviews or thumbs-up
feedback are manufactured by automation.

Selection binds the authenticated broker, current ranking, fact-find and ordered
policies. Final signature requires an explicit declaration, current pack hash,
authorised adviser and fresh single-use session-bound verification. Failed or stale
signatures roll back their proposed acknowledgements. Agent functions never sign
or publish advice. Global agent pause, case holds, partner eligibility, medical
clarification and complaint controls remain effective. Exceptions stop automation;
the two-decision happy-path demo does not silently resolve them.

The local background runner is enabled by `HELM_DEMO_BACKGROUND_JOBS=true` in the
start script. Direct API startup without that setting needs the existing Arq worker.
Automatic case GETs do not execute jobs; normal legacy cases retain their preview
polling behaviour. Source snapshots remain encrypted and event payloads contain
metadata rather than patient text. No schema migration or data reset is needed.
