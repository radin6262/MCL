import uuid
import hashlib
import json
from datetime import datetime, timedelta
from typing import Optional
from pathlib import Path
from base import AuthProvider, Account


class OfflineAuthProvider(AuthProvider):
    """
    Offline authentication provider.

    Reads persistent username and UUID from 'player.json'.
    If the file does not exist or lacks valid data, generates a deterministic
    offline UUID and falls back to a default username.

    Also maintains a cache file ('offline_account.json') for the last used account,
    so 'get_active_account()' can return it without re‑reading player.json.
    """

    def __init__(self, cache_path: str = "offline_account.json", player_data_path: str = "player.json"):
        self.cache_path = cache_path
        self.player_data_path = player_data_path

    def authenticate(self, username: Optional[str] = None) -> Account:
        # 1. Try to load username and UUID from player.json
        saved_username, saved_uuid = self._load_player_data()

        # Use provided username, or fall back to saved one, then "Player"
        if username:
            final_username = username
        else:
            final_username = saved_username if saved_username else "Player"

        # Use saved UUID, or generate offline UUID
        if saved_uuid:
            uuid_str = saved_uuid
        else:
            uuid_str = self._generate_offline_uuid(final_username)

        account = Account(
            uuid=uuid_str,
            username=final_username,
            access_token="0",
            refresh_token=None,
            expires_at=datetime.utcnow() + timedelta(days=365)
        )

        self._save_to_cache(account)
        return account

    def refresh(self, account: Account) -> Account:
        return account

    def get_active_account(self) -> Optional[Account]:
        try:
            with open(self.cache_path, "r") as f:
                data = json.load(f)
                return Account(
                    uuid=data["uuid"],
                    username=data["username"],
                    access_token=data["access_token"],
                    refresh_token=data.get("refresh_token"),
                    expires_at=datetime.fromisoformat(data["expires_at"])
                )
        except (FileNotFoundError, KeyError, ValueError):
            return None

    def can_launch_offline(self, account: Optional[Account]) -> bool:
        return account is not None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_player_data(self) -> tuple[Optional[str], Optional[str]]:
        """
        Returns (username, uuid) from player.json.
        Both are None if the file is missing or invalid.
        """
        try:
            path = Path(self.player_data_path)
            if not path.exists():
                return None, None
            with open(path, "r") as f:
                data = json.load(f)
            username = data.get("username", "").strip()
            uuid_str = data.get("uuid", "").strip()
            # Validate UUID format
            if uuid_str:
                uuid.UUID(uuid_str)
            else:
                uuid_str = None
            return username if username else None, uuid_str
        except (FileNotFoundError, json.JSONDecodeError, ValueError, KeyError):
            return None, None

    @staticmethod
    def _generate_offline_uuid(username: str) -> str:
        """
        Standard offline UUID: MD5 hash of "OfflinePlayer:<username>".
        Follows the same algorithm as vanilla Minecraft.
        """
        data = f"OfflinePlayer:{username}".encode('utf-8')
        md5 = hashlib.md5(data).digest()
        uuid_bytes = bytearray(md5)
        # Set version and variant bits
        uuid_bytes[6] = (uuid_bytes[6] & 0x0f) | 0x30
        uuid_bytes[8] = (uuid_bytes[8] & 0x3f) | 0x80
        return str(uuid.UUID(bytes=bytes(uuid_bytes)))

    def _save_to_cache(self, account: Account):
        """Save the account to the cache file (offline_account.json)."""
        with open(self.cache_path, "w") as f:
            json.dump({
                "uuid": account.uuid,
                "username": account.username,
                "access_token": account.access_token,
                "expires_at": account.expires_at.isoformat()
            }, f, indent=2)
