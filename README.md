# Helm Broker

Independent UK PMI broker workspace. React/JavaScript website, five Python agents,
and an API boundary to the Helm consumer portal. Built from the supplied Parts 1–3.

## Layout

```
apps/web/                   broker website (JavaScript / JSX)
services/api/app/agents/    intake, quotation, ranking, review, learning
services/api/app/engine/    deterministic recommendation mathematics
services/api/app/db/        database models and migrations
packages/contracts/        shared API contracts
tools/                     demo fixtures and development utilities
docs/                      requirements, architecture and runbooks
```

This is a demo-first implementation. Live partner delivery, clinical interpretation,
and automatic model activation are disabled. See docs/STATUS.md for exact boundaries.
