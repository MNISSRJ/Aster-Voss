# Security Baseline

- Browser code must never receive Supabase secret/service-role keys.
- Tool execution defaults to read-only permissions.
- Project file reads reject .env and Git metadata paths.
- Conversation and memory access is scoped by user_id.
- Logs must contain request metadata, never credentials or raw secrets.
- Public multi-user deployment requires authentication before enabling arbitrary user_id input.

## Release gate

A release must pass the core regression matrix and confirm that no secret values are tracked by git.
