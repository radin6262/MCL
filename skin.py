#!/usr/bin/env python3
"""Yggdrasil auth server for authlib-injector with player.json and local skin serving."""

import json
import random
import uuid as uuid_lib
import time
import os
import mimetypes
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

# ----------------------------------------------------------------------
# Generate keypair (RSA 2048) – still generated but unused if no signing
# ----------------------------------------------------------------------
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
import base64

_private_key = rsa.generate_private_key(
    public_exponent=65537,
    key_size=2048,
    backend=default_backend()
)
_public_key = _private_key.public_key()

_public_der = _public_key.public_bytes(
    encoding=serialization.Encoding.DER,
    format=serialization.PublicFormat.SubjectPublicKeyInfo
)
MOJANG_PUBLIC_KEY_BASE64 = base64.b64encode(_public_der).decode('ascii')

# ----------------------------------------------------------------------
# Load player.json – maps username → UUID
# Supports all three formats:
#   {"user": "uuid", ...}
#   [{"username":"..","uuid":".."}, ...]
#   {"username":"..","uuid":".."}   <-- single object format
# ----------------------------------------------------------------------
PLAYER_JSON_PATH = "player.json"
PLAYER_MAP = {}  # username -> uuid (string)

if os.path.exists(PLAYER_JSON_PATH):
    try:
        with open(PLAYER_JSON_PATH, "r") as f:
            raw = json.load(f)

        if isinstance(raw, dict):
            # Check if this is a single-object format {"username":"..","uuid":".."}
            if "username" in raw and "uuid" in raw:
                PLAYER_MAP[raw["username"]] = raw["uuid"]
                print(f"[INFO] Loaded single player: {raw['username']} -> {raw['uuid']}")
            else:
                # Normal dict mapping: {"player": "uuid", ...}
                PLAYER_MAP.update(raw)
        elif isinstance(raw, list):
            for entry in raw:
                if "username" in entry and "uuid" in entry:
                    PLAYER_MAP[entry["username"]] = entry["uuid"]

        print(f"[INFO] Loaded {len(PLAYER_MAP)} players from {PLAYER_JSON_PATH}")
    except Exception as e:
        print(f"[WARN] Could not load {PLAYER_JSON_PATH}: {e}")
else:
    print(f"[INFO] {PLAYER_JSON_PATH} not found. Using auto-generated UUIDs.")

# ----------------------------------------------------------------------
# In-memory session storage
# STORAGE["users"] = { username: {"uuid": str, "access_token": str|None, "client_token": str|None} }
# STORAGE["server_id"] = str
# ----------------------------------------------------------------------
STORAGE = {
    "users": {},
    "server_id": "0"
}

def generate_uuid():
    return str(uuid_lib.uuid4()).replace("-", "")

# ----------------------------------------------------------------------
# Skin serving directory
# ----------------------------------------------------------------------
SKINS_DIR = "skins"
os.makedirs(SKINS_DIR, exist_ok=True)

# ----------------------------------------------------------------------
# HTTP handler
# ----------------------------------------------------------------------
class YggdrasilHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        print(f"[Yggdrasil] {args[0]} {args[1]} {args[2]}")

    def _send_json(self, data, status=200):
        body = json.dumps(data, separators=(',', ':')).encode('utf-8')
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path, content_type):
        try:
            with open(path, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except FileNotFoundError:
            self._send_json({"error": "Not Found"}, status=404)

    # ---------- GET ----------
    def do_GET(self):
        parsed = urlparse(self.path)

        # ---- metadata ----
        if parsed.path == "/":
            meta = {
                "meta": {
                    "serverName": "Local Yggdrasil Server + Skin Server",
                    "implementationName": "CustomPython",
                    "implementationVersion": "1.0.0"
                },
                "skinDomains": ["localhost", "127.0.0.1"]
            }
            self._send_json(meta)

        # ---- skin PNG serving ----
        elif parsed.path.startswith("/skins/") and parsed.path.endswith(".png"):
            skin_uuid = parsed.path[len("/skins/"):-len(".png")]
            if not skin_uuid:
                self._send_json({"error": "Bad request"}, status=400)
                return
            skin_path = os.path.join(SKINS_DIR, skin_uuid + ".png")
            self._send_file(skin_path, "image/png")

        # ---- profile/<uuid> ----
        elif parsed.path.startswith("/sessionserver/session/minecraft/profile/"):
            profile_path = parsed.path[len("/sessionserver/session/minecraft/profile/"):]
            uuid = profile_path.split("?")[0]  # remove query like ?unsigned=false

            # Normalize for comparison
            uuid_clean = uuid.replace("-", "").lower()

            # Find the username for this UUID
            username = None
            for name, user_data in STORAGE["users"].items():
                stored_uuid = user_data["uuid"].replace("-", "").lower()
                if stored_uuid == uuid_clean:
                    username = name
                    break

            # Also check PLAYER_MAP (for users not yet authenticated but in player.json)
            if username is None:
                for name, stored_uuid in PLAYER_MAP.items():
                    if stored_uuid.replace("-", "").lower() == uuid_clean:
                        username = name
                        # Ensure it's in STORAGE for future lookups
                        if name not in STORAGE["users"]:
                            STORAGE["users"][name] = {
                                "uuid": stored_uuid,
                                "access_token": None,
                                "client_token": None
                            }
                        break

            if username:
                cache_buster = random.randint(1, 999999)  # or use int(time.time() * 1000)
                textures = {
                    "timestamp": int(time.time() * 1000),
                    "profileId": uuid,
                    "profileName": username,
                    "textures": {
                        "SKIN": {
                            "url": f"http://127.0.0.1:25585/skins/{uuid}.png?t={cache_buster}"
                        }
                    }
                }
                textures_str = base64.b64encode(json.dumps(textures).encode()).decode()

                profile = {
                    "id": uuid,
                    "name": username,
                    "properties": [
                        {
                            "name": "textures",
                            "value": textures_str
                            # No "signature" field
                        }
                    ]
                }
                self._send_json(profile, 200)
            else:
                # UUID not found anywhere
                self.send_response(204)
                self.end_headers()

        # ---- hasJoined ----
        elif parsed.path.startswith("/sessionserver/session/minecraft/hasJoined"):
            query = {}
            if parsed.query:
                for part in parsed.query.split("&"):
                    if "=" in part:
                        k, v = part.split("=", 1)
                        query[k] = v

            username = query.get("username", "")
            server_id = query.get("serverId", "")

            # Resolve UUID from STORAGE or PLAYER_MAP
            user_uuid = None
            if username in STORAGE["users"]:
                user_uuid = STORAGE["users"][username]["uuid"]
            elif username in PLAYER_MAP:
                user_uuid = PLAYER_MAP[username]
                # Also register in STORAGE
                STORAGE["users"][username] = {
                    "uuid": user_uuid,
                    "access_token": None,
                    "client_token": None
                }

            if user_uuid and server_id == STORAGE["server_id"]:
                skin_url = f"http://{self.headers.get('Host', 'localhost:25585')}/skins/{user_uuid}.png"
                textures = {
                    "timestamp": int(time.time() * 1000),
                    "profileId": user_uuid,
                    "profileName": username,
                    "textures": {
                        "SKIN": {
                            "url": skin_url,
                            "metadata": {"model": "slim"}
                        }
                    }
                }
                textures_b64 = base64.b64encode(
                    json.dumps(textures, separators=(',', ':')).encode()
                ).decode('ascii')

                profile = {
                    "id": user_uuid,
                    "name": username,
                    "properties": [
                        {"name": "textures", "value": textures_b64}
                    ]
                }
                self._send_json(profile)
            else:
                self._send_json({}, status=204)

        else:
            self._send_json({"error": "Not Found"}, status=404)

    # ---------- POST ----------
    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8")
        data = json.loads(body) if body else {}

        parsed = urlparse(self.path)

        # ---- authenticate ----
        if parsed.path == "/authserver/authenticate":
            username = data.get("username", "Player")

            # Determine UUID: from player.json first, else auto-generate
            if username in PLAYER_MAP:
                user_uuid = PLAYER_MAP[username]
            else:
                user_uuid = generate_uuid()

            # Ensure an in-memory entry exists
            if username not in STORAGE["users"]:
                STORAGE["users"][username] = {
                    "uuid": user_uuid,
                    "access_token": None,
                    "client_token": None
                }

            user = STORAGE["users"][username]
            client_token = data.get("clientToken", generate_uuid())
            access_token = generate_uuid()
            user["access_token"] = access_token
            user["client_token"] = client_token

            skin_url = f"http://{self.headers.get('Host', 'localhost:25585')}/skins/{user_uuid}.png"
            textures = {
                "timestamp": int(time.time() * 1000),
                "profileId": user_uuid,
                "profileName": username,
                "textures": {
                    "SKIN": {
                        "url": skin_url,
                        "metadata": {"model": "slim"}
                    }
                }
            }
            textures_b64 = base64.b64encode(
                json.dumps(textures, separators=(',', ':')).encode()
            ).decode('ascii')

            response = {
                "accessToken": access_token,
                "clientToken": client_token,
                "availableProfiles": [
                    {"id": user_uuid, "name": username}
                ],
                "selectedProfile": {
                    "id": user_uuid,
                    "name": username
                },
                "user": {
                    "id": user_uuid,
                    "properties": [
                        {"name": "preferredLanguage", "value": "en_US"},
                        {"name": "twitch_access_token", "value": ""}
                    ]
                }
            }
            self._send_json(response)

        # ---- refresh ----
        elif parsed.path == "/authserver/refresh":
            access_token = data.get("accessToken", "")
            client_token = data.get("clientToken", "")

            found_user = None
            found_name = None
            for name, user_data in STORAGE["users"].items():
                if user_data["access_token"] == access_token:
                    found_user = user_data
                    found_name = name
                    break

            if found_user and found_user["client_token"] == client_token:
                new_token = generate_uuid()
                found_user["access_token"] = new_token

                skin_url = f"http://{self.headers.get('Host', 'localhost:25585')}/skins/{found_user['uuid']}.png"
                textures = {
                    "timestamp": int(time.time() * 1000),
                    "profileId": found_user["uuid"],
                    "profileName": found_name,
                    "textures": {
                        "SKIN": {
                            "url": skin_url,
                            "metadata": {"model": "slim"}
                        }
                    }
                }
                textures_b64 = base64.b64encode(
                    json.dumps(textures, separators=(',', ':')).encode()
                ).decode('ascii')

                response = {
                    "accessToken": new_token,
                    "clientToken": client_token,
                    "selectedProfile": {
                        "id": found_user["uuid"],
                        "name": found_name
                    },
                    "user": {
                        "id": found_user["uuid"],
                        "properties": []
                    }
                }
                self._send_json(response)
            else:
                self._send_json({"error": "Invalid token"}, status=403)

        # ---- validate ----
        elif parsed.path == "/authserver/validate":
            access_token = data.get("accessToken", "")
            valid = any(
                user_data["access_token"] == access_token
                for user_data in STORAGE["users"].values()
            )
            if valid:
                self._send_json({}, status=204)
            else:
                self._send_json({}, status=403)

        # ---- join ----
        elif parsed.path == "/sessionserver/session/minecraft/join":
            access_token = data.get("accessToken", "")
            server_id = data.get("serverId", "")
            selected_profile = data.get("selectedProfile", "")

            found = False
            for name, user_data in STORAGE["users"].items():
                if user_data["uuid"] == selected_profile and user_data["access_token"] == access_token:
                    found = True
                    break

            if found:
                STORAGE["server_id"] = server_id
                self._send_json({}, status=204)
            else:
                self._send_json({"error": "Invalid token"}, status=403)

        else:
            self._send_json({"error": "Not Found"}, status=404)


def main():
    server = HTTPServer(("0.0.0.0", 25585), YggdrasilHandler)
    print("Yggdrasil + skin server running on http://localhost:25585")
    print("Set authlib-injector URL to: http://localhost:25585")
    print("Place skin PNGs in ./skins/<uuid>.png")
    print("Create player.json (username→uuid mapping)")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.server_close()



if __name__ == "__main__":
    main()
