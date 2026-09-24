# Aster Voss Architecture

## Runtime boundaries

- API layer: FastAPI routes in `web_app.py` (to be split incrementally).
- Agent runtime: `agent.py`.
- Provider abstraction: `llm/base.py` + provider adapters.
- Memory/data access: `memory/`.
- Tools: `tools/`.
- Scheduled/skill work: `ai_radar.py`.

## Data ownership

- Identity: `aster/identity.py`.
- Long-term memory: Supabase `aster_memory`.
- Conversations: Supabase `aster_conversations`.
- AI briefs: Supabase `ai_radar_briefs`.
- Local markdown/JSON are development/bootstrap fallbacks only.

## Non-regression rule

Every feature must be tested on a branch/preview before merge. A failure in an auxiliary subsystem must not prevent a successful core chat response.
