# Aster Voss Release Checklist

## Automated gate
- GitHub Actions test suite passes.
- Build/deployment is successful.
- No tracked secret files.
- Core API contracts are green.

## Manual gate
- Send a message with Enter.
- Shift+Enter creates a newline.
- New conversation returns to Chat.
- Existing conversation remains in the sidebar.
- Conversation start/activity timestamps are visible.
- Opening a saved conversation restores all messages.
- Memory add/edit/delete works.
- AI Radar generates and displays content.
- AI Radar refresh failure does not break Chat.
- Settings opens and closes.

## Production gate
- Only merge after Preview passes.
- Confirm main deployment is READY.
- Confirm /api/status returns 200 and server_time.
- Check recent runtime errors after deployment.
