# Aster Voss Data Model

## Durable tables
- aster_memory: one durable memory document per user.
- aster_conversations: one archived conversation per user.
- ai_radar_briefs: one generated daily brief per user/date.

## Timestamps
- created_at: immutable creation time.
- updated_at: last successful persistence time.
- APIs expose ISO timestamps plus server_time where useful.

## Ownership
Every durable record is scoped by user_id. The single-user development default is controlled by ASTER_DEFAULT_USER_ID.
