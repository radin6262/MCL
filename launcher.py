import json
import platform
import re
import subprocess
import zipfile
from pathlib import Path
from typing import List, Optional

from base import Account


class GameLauncher:
    def __init__(self, game_dir: Path, java_path: Path,
                 fullscreen: bool = True, width: int = 854, height: int = 480,
                 ram_mb: int = 2048, java_args: Optional[List[str]] = None):
        self.game_dir = game_dir.resolve()
        self.java = java_path
        self.fullscreen = fullscreen
        self.width = width
        self.height = height
        self.ram_mb = ram_mb
        # Base java_args (can contain anything the user wants)
        self.java_args = java_args if java_args is not None else []
        self.os_name = self._detect_os()

    def _detect_os(self) -> str:
        s = platform.system()
        if s == "Windows":
            return "windows"
        if s == "Darwin":
            return "osx"
        return "linux"

    def _sanitize_version(self, version: str) -> str:
        illegal = r'[<>:"/\\|?*]'
        return re.sub(illegal, '_', version)

    def _get_java_version(self) -> Optional[int]:
        try:
            result = subprocess.run(
                [str(self.java), '-version'],
                capture_output=True,
                text=True,
                timeout=10
            )
            output = result.stderr or result.stdout
            for line in output.splitlines():
                match = re.search(r'version\s+"?(\d+)', line)
                if match:
                    ver = int(match.group(1))
                    if ver == 1:
                        return 8
                    return ver
        except Exception as e:
            print(f"[WARN] Could not detect Java version: {e}")
        return None

    def _version_json(self, version: str) -> Path:
        return self.game_dir / "versions" / version / f"{version}.json"

    def _load_version(self, version: str) -> dict:
        p = self._version_json(version)
        if not p.exists():
            raise FileNotFoundError(
                f"Version JSON not found: {p}\n"
                f"Run the downloader first or copy files from an official install."
            )
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)

    def _rule_matches(self, rule: dict) -> bool:
        os_spec = rule.get("os")
        if not os_spec:
            return True
        if os_spec.get("name") and os_spec["name"] != self.os_name:
            return False
        return True

    def _rules_allow(self, rules: List[dict]) -> bool:
        if not rules:
            return True
        allowed = False
        for rule in rules:
            if self._rule_matches(rule):
                allowed = (rule.get("action") == "allow")
        return allowed

    def _build_classpath(self, version_data: dict, version: str) -> str:
        libs: List[str] = []
        for lib in version_data.get("libraries", []):
            if "rules" in lib and not self._rules_allow(lib["rules"]):
                continue
            artifact = lib.get("downloads", {}).get("artifact")
            if artifact:
                p = self.game_dir / "libraries" / artifact["path"]
                if p.exists():
                    libs.append(str(p))
                else:
                    print(f"[WARN] Missing library: {p}")

        client_jar = self.game_dir / "versions" / version / f"{version}.jar"
        if client_jar.exists():
            libs.append(str(client_jar))
        else:
            raise FileNotFoundError(f"Client jar missing: {client_jar}")

        separator = ";" if self.os_name == "windows" else ":"
        return separator.join(libs)

    def _extract_natives(self, version_data: dict, version: str) -> Path:
        natives_dir = self.game_dir / "versions" / version / "natives"
        natives_dir.mkdir(parents=True, exist_ok=True)

        for lib in version_data.get("libraries", []):
            if "rules" in lib and not self._rules_allow(lib["rules"]):
                continue
            classifiers = lib.get("downloads", {}).get("classifiers", {})
            native_key = None

            if self.os_name == "windows":
                native_key = "natives-windows"
                if "natives-windows-64" in classifiers and platform.architecture()[0] == "64bit":
                    native_key = "natives-windows-64"
            elif self.os_name == "osx":
                native_key = "natives-osx"
                if "natives-macos" in classifiers:
                    native_key = "natives-macos"
            else:
                native_key = "natives-linux"

            if native_key not in classifiers:
                continue

            artifact = classifiers[native_key]
            jar_path = self.game_dir / "libraries" / artifact["path"]
            if not jar_path.exists():
                print(f"[WARN] Missing native: {jar_path}")
                continue

            with zipfile.ZipFile(jar_path, "r") as zf:
                for name in zf.namelist():
                    if name.startswith("META-INF/"):
                        continue
                    if name.endswith("/"):
                        continue
                    try:
                        zf.extract(name, natives_dir)
                    except Exception as e:
                        print(f"[WARN] Failed to extract {name}: {e}")

        return natives_dir

    def _get_jvm_args(self, version_data: dict, natives_path: Path, classpath: str) -> List[str]:
        java_ver = self._get_java_version()
        args: List[str] = []

        # ──────────────────────────────────────────────────────────
        # PROXY ARGS – forward all HTTP/HTTPS traffic through
        # the local skin server (port 9089 by default).
        # Minecraft will use the proxy to resolve sessionserver.
        # ──────────────────────────────────────────────────────────
        proxy_host = "127.0.0.1"
        proxy_port = "9089"
        args.append(f"-Dhttp.proxyHost={proxy_host}")
        args.append(f"-Dhttp.proxyPort={proxy_port}")
        args.append(f"-Dhttps.proxyHost={proxy_host}")
        args.append(f"-Dhttps.proxyPort={proxy_port}")
        args.append("-Dhttp.nonProxyHosts=localhost|127.*|[::1]")
        args.append("-Dhttps.nonProxyHosts=localhost|127.*|[::1]")
        proxy_host = "127.0.0.1"
        proxy_port = "9089"
        args.append(f"-Dhttp.proxyHost={proxy_host}")
        args.append(f"-Dhttp.proxyPort={proxy_port}")
        args.append(f"-Dhttps.proxyHost={proxy_host}")
        args.append(f"-Dhttps.proxyPort={proxy_port}")

        # SOCKS proxy (as backup)
        args.append(f"-DsocksProxyHost={proxy_host}")
        args.append(f"-DsocksProxyPort={proxy_port}")

        # Disable proxy for localhost
        args.append("-Dhttp.nonProxyHosts=localhost|127.*|[::1]")
        args.append("-Dhttps.nonProxyHosts=localhost|127.*|[::1]")
        # Any user-supplied extra java_args
        for arg in self.java_args:
            args.append(arg)

        # RAM
        if self.ram_mb > 0:
            args.append(f"-Xmx{self.ram_mb}M")
            min_heap = max(256, self.ram_mb // 2)
            args.append(f"-Xms{min_heap}M")

        # JVM flags from version JSON
        jvm_args = version_data.get("arguments", {}).get("jvm", [])
        if jvm_args:
            for arg in jvm_args:
                if isinstance(arg, str):
                    if arg.startswith("--sun-misc-unsafe-memory-access") or \
                       arg.startswith("--enable-native-access"):
                        if java_ver is None or java_ver < 22:
                            print(f"[INFO] Skipping unsupported JVM flag (Java {java_ver}): {arg}")
                            continue
                    args.append(arg)
                elif isinstance(arg, dict):
                    if not self._rules_allow(arg.get("rules", [])):
                        continue
                    value = arg.get("value")
                    if isinstance(value, list):
                        for v in value:
                            if isinstance(v, str):
                                if v.startswith("--sun-misc-unsafe-memory-access") or \
                                   v.startswith("--enable-native-access"):
                                    if java_ver is None or java_ver < 22:
                                        continue
                                args.append(v)
                            else:
                                args.append(str(v))
                    elif isinstance(value, str):
                        if value.startswith("--sun-misc-unsafe-memory-access") or \
                           value.startswith("--enable-native-access"):
                            if java_ver is None or java_ver < 22:
                                continue
                        args.append(value)
        else:
            args.append("-Djava.library.path=${natives_directory}")
            args.append("-cp")
            args.append("${classpath}")

        def sub(s: str) -> str:
            return s \
                .replace("${natives_directory}", str(natives_path)) \
                .replace("${launcher_name}", "MCL") \
                .replace("${launcher_version}", "1.0") \
                .replace("${classpath}", classpath)

        return [sub(a) for a in args]

    def _get_game_args(self, version_data: dict, account: Account,
                       instance_dir: Path, version: str) -> List[str]:
        args: List[str] = []
        raw = version_data.get("arguments", {}).get("game", [])
        if raw:
            for arg in raw:
                if isinstance(arg, str):
                    args.append(arg)
                elif isinstance(arg, dict):
                    if not self._rules_allow(arg.get("rules", [])):
                        continue
                    value = arg.get("value")
                    if isinstance(value, list):
                        args.extend(value)
                    elif isinstance(value, str):
                        args.append(value)
        else:
            legacy = version_data.get("minecraftArguments", "")
            if legacy:
                args = legacy.split(" ")

        args = [arg for arg in args if arg != "--demo"]

        asset_index = version_data.get("assetIndex", {}).get("id", "legacy")

        def sub(s: str) -> str:
            return s \
                .replace("${auth_player_name}", account.username) \
                .replace("${version_name}", version) \
                .replace("${game_directory}", str(instance_dir)) \
                .replace("${assets_root}", str(self.game_dir / "assets")) \
                .replace("${assets_index_name}", asset_index) \
                .replace("${auth_uuid}", account.uuid) \
                .replace("${auth_access_token}", account.access_token) \
                .replace("${user_type}", "legacy") \
                .replace("${user_properties}", "{}") \
                .replace("${version_type}", version_data.get("type", "release")) \
                .replace("${resolution_width}", str(self.width)) \
                .replace("${resolution_height}", str(self.height)) \
                .replace("${clientid}", "0") \
                .replace("${auth_xuid}", "0") \
                .replace("${quickPlayPath}", "") \
                .replace("${quickPlaySingleplayer}", "") \
                .replace("${quickPlayMultiplayer}", "") \
                .replace("${quickPlayRealms}", "")

        result = [sub(a) for a in args]

        qp_flags = {"--quickPlayPath", "--quickPlaySingleplayer",
                    "--quickPlayMultiplayer", "--quickPlayRealms"}
        cleaned = []
        i = 0
        while i < len(result):
            if result[i] in qp_flags and i + 1 < len(result) and result[i + 1] == "":
                i += 2
                continue
            cleaned.append(result[i])
            i += 1
        result = cleaned

        mandatory_flags = {
            "--accessToken": account.access_token,
            "--username": account.username,
            "--uuid": account.uuid,
            "--userType": "legacy",
            "--userProperties": "{}",
            "--versionType": version_data.get("type", "release"),
        }
        flags_present = set()
        for i, arg in enumerate(result):
            if arg in mandatory_flags:
                flags_present.add(arg)
        for flag, value in mandatory_flags.items():
            if flag not in flags_present:
                result.append(flag)
                result.append(value)

        if self.fullscreen and "--fullscreen" not in result:
            result.append("--fullscreen")
        elif not self.fullscreen and "--fullscreen" in result:
            result = [arg for arg in result if arg != "--fullscreen"]

        return result

    def build_args(self, version: str, account: Account,
                   instance_dir: Path) -> List[str]:
        version_data = self._load_version(version)
        natives_path = self._extract_natives(version_data, version)
        classpath = self._build_classpath(version_data, version)

        cmd = [str(self.java)]
        cmd.extend(self._get_jvm_args(version_data, natives_path, classpath))
        main_class = version_data.get("mainClass",
                                      "net.minecraft.client.main.Main")
        cmd.append(main_class)
        cmd.extend(self._get_game_args(version_data, account,
                                       instance_dir, version))
        return cmd

    def launch(self, version: str, account: Account, instance_dir: Path,
               log_callback=None):
        import sys

        safe_ver = self._sanitize_version(version)

        safe_instance_dir = (instance_dir.parent / safe_ver).resolve()
        try:
            safe_instance_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            error_msg = (f"Failed to create instance directory "
                         f"'{safe_instance_dir}': {e}")
            if log_callback:
                log_callback(error_msg)
            else:
                print(error_msg)
            raise

        cmd = self.build_args(version, account, safe_instance_dir)
        full_cmd = " ".join(cmd)
        if log_callback:
            log_callback(f"[CMD] {full_cmd}")
        else:
            print(f"[CMD] {full_cmd}")

        process = subprocess.Popen(
            cmd,
            cwd=str(safe_instance_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            encoding='utf-8',
            errors='replace',
            startupinfo=subprocess.STARTUPINFO(),
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return process
