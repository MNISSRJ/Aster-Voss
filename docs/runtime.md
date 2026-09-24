# Runtime Contract

Supported runtime: Python 3.12.

Core API contract:
- GET /api/status returns HTTP 200 and includes `server_time`.
- POST /api/chat accepts `message` and optional `conversation_id`.
- POST /api/reset starts a fresh working conversation without deleting durable memory.
- GET/POST/PUT/DELETE /api/memory manage long-term memory.
- GET/POST/DELETE /api/conversations manage archived conversations.
- GET /api/ai-radar/today reads today's stored brief.
- POST /api/ai-radar/refresh creates/refreshed a brief.

Core chat behavior:
- Enter sends a message.
- Shift+Enter inserts a newline.
- A model/provider failure returns an explicit assistant error without corrupting the current conversation.
- Auxiliary archive failures must not turn a successful model response into a 5xx.
