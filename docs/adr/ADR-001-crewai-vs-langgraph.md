# ADR-001 · CrewAI with application-owned durable state

The pinned CrewAI dependency is retained. `test_crewai_feedback.py` exercises a
nonblocking feedback provider: a decorated step returns pending, the state is JSON
serialisable, and a later feedback event resumes the next step. The full five-agent
smoke test also executes code-only flows without network or model credentials.

Framework feedback never authorises a gate. Authenticated application services and
SQL approval records remain the control plane. Postgres stores snapshots/jobs; no
six-hour wait or human decision depends on an in-memory Flow instance surviving.

LangGraph is not introduced alongside a working framework. If the executable spike
fails on a dependency update, CI must fail and this decision must be reviewed.
