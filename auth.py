from __future__ import annotations
from dataclasses import dataclass
import hmac

@dataclass(frozen=True)
class UserContext:
    user_id: str
    is_owner: bool = True

class OwnerTokenProvider:
    """Temporary single-owner token gate; not multi-user authentication."""
    def __init__(self, token: str, owner_id: str):
        self._token, self._owner_id = token, owner_id
    def authenticate(self, authorization: str) -> UserContext | None:
        if not self._token or not self._owner_id:
            return None
        if not hmac.compare_digest(authorization or "", "Bearer " + self._token):
            return None
        return UserContext(self._owner_id, True)
