# Integration boundary

The broker never reads the consumer database. Proposed `/v1` Core endpoints in
docs/spec/part2.md require reconciliation with the consumer backend before live use.
The runnable API publishes its own OpenAPI contract at `/openapi.json`.
