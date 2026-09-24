# Aster Voss 0.2 Stabilization Status

This branch implements the planned hardening roadmap without merging into production.

## Completed in code
- S0: stable baseline and release/non-regression documentation.
- S1: explicit dependencies, Python 3.12, deployment config alignment, config examples.
- S2: vendor-neutral provider contract and OpenAI adapter/registry.
- S3: memory service/repository boundary, durable user scope, Vercel local-persistence guard.
- S4: conversation persistence with created_at/updated_at semantics and migration helper.
- S5: request-scoped Agent construction.
- S6: tool schemas, read-only default, permission checks, sensitive-file blocking.
- S7: rule router with optional Jev fallback.
- S8: service/repository boundaries and dedicated UI template.
- S9: CI tests, optional bearer gate, usage/event observability, security documentation.
- S10: AI Radar service, explicit result states, multi-source collection, daily scheduled skill, cloud archive.
- S11: automation registry with AI Radar as the first scheduled skill.
- S12: reviewable memory extraction suggestions (never silently auto-saves).
- S13: vector retrieval/pgvector foundation, disabled until embeddings are configured.
- S14: multimodal message/content foundation, no UI upload enabled yet.
- S15: request id, server timestamp headers, latency logs and usage endpoint.
- UI 2.0 foundation: extracted HTML template, conversation grouping/timestamps, resilient navigation.

## Not yet production-enabled
- Public multi-user authentication is optional and disabled by default.
- Vector retrieval is dormant until embedding credentials/schema are provisioned.
- Multimodal upload UI is intentionally not enabled.
- Generic user-defined automation scheduling is not enabled; only registered scheduled skills execute.
- Existing legacy conversation JSON has a migration helper but is not deleted automatically.

## Verification
GitHub Actions test suite is the primary automated gate. Production is not merged from this branch.
Vercel preview deployment may be unavailable while the project is under Vercel deployment rate limiting; this does not change the production deployment.
