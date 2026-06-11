from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
from datetime import datetime, timedelta

@dataclass
class Account:
    uuid: str
    username: str
    access_token: str          # Minecraft token
    refresh_token: Optional[str]
    expires_at: datetime       # Minecraft token expiry

class AuthProvider(ABC):
    @abstractmethod
    def authenticate(self) -> Account:
        """Runs the full login flow (blocking or async)."""
        ...

    @abstractmethod
    def refresh(self, account: Account) -> Account:
        """Uses refresh_token to get a new set of tokens."""
        ...

    def can_launch_offline(self, account: Optional[Account]) -> bool:
        """True if we have a cached UUID/username and token isn't ancient."""
        if not account:
            return False
        # Allow offline if we logged in within last 30 days
        return account.expires_at > (datetime.utcnow() - timedelta(days=30))
    
    @abstractmethod
    def get_active_account(self) -> Optional[Account]:
        """Load from secure cache."""
        ...
