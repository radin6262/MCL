# MCL

A simple Minecraft launcher.

## Features

* **Offline Authentication**: Supports offline/Yggdrasil authentication without requiring Mojang servers.
* **Skin Cache Management**: Automatically clears skin cache to prevent persistent skin issues in Minecraft 1.20+.
* **Multi-Version Support**: Launch different Minecraft versions with isolated instances.
* **Custom Java Arguments**: Configure memory allocation and other JVM parameters.
* **Real-time Logging**: View Minecraft output in real-time within the launcher interface.

## Prerequisites

* Python 3.8 or higher (ideally **Python 3.14**)
* Java 25, 21, or 17 (depends on the Minecraft version you run)

## Installation

> Before installation, it is recommended to use a virtual environment (venv).

1. Clone the repository:

```bash
git clone https://github.com/radin6262/MCL.git
cd MCL
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Configure your launcher settings in `config.json` (if applicable).

## Usage

### Basic Launch

```bash
python main.py
```

### Command Line Options

```text
--username <name>      Specify Minecraft username
--version <version>    Specify Minecraft version (default: latest)
--ram <mb>             Set RAM allocation in MB (default: 4096)
--fullscreen           Launch in fullscreen mode
```

### Skin Cache Management

The launcher automatically handles skin cache clearing to prevent persistent skin issues. This is necessary because Minecraft 1.20+ caches skins locally at:

```text
.minecraft/assets/skins/<uuid>/
```

## Project Structure

```text
.
├── main.py                 # Main launcher application
├── base.py                 # Base authentication handler
├── offline.py              # Offline authentication handler
├── launcher.py             # Minecraft process management
├── skin.py                 # Yggdrasil and skin management service
├── requirements.txt        # Python dependencies
└── README.md               # This file
```

## Configuration

### Authentication

The launcher uses `player.json` for player data and `offline_account.json` for account caching. These files are automatically generated on first run.

### Java Settings

You can configure custom Java arguments from the Settings section (make sure you know what you're doing).

## Troubleshooting

### Common Issues

1. **Skin Persistence**: If skins aren't updating, manually delete `.minecraft/assets/skins/` before launching.
2. **Java Errors**: Ensure Java is installed and accessible in your PATH. If not, go to **Settings → Java** and select your Java executable.
3. **Authentication Failures**: Delete `offline_account.json` and `player.json` to reset authentication.
4. **Launcher Crashes After Game Exit**: This is a known bug and will be fixed as soon as possible.

### Debug Mode

`authlib-injector` (the system used to inject skins, capes, etc.) has debug mode enabled by default.

## Development

### Setting Up the Development Environment

We recommend using VS Code or PyCharm.

```bash
python -m venv .venv

# Linux/macOS
source .venv/bin/activate

# Windows
.venv\Scripts\activate

pip install -r requirements-dev.txt
```

## Contributing

Coming soon.

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.

## Acknowledgments

* Minecraft and Mojang for the game.
* The Minecraft community for various launcher implementations.
* Contributors to the Python Minecraft launcher ecosystem.

## Support

For issues and feature requests, please use the GitHub Issues page.

---

**Disclaimer:** This launcher is not affiliated with, endorsed by, or connected to Microsoft or Mojang in any way.
