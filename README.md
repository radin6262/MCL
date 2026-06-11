# MCL

A Simple Minecraft launcher.

## Features

- **Offline Authentication**: Supports offline/Yggdrasil authentication without requiring Mojang servers
- **Skin Cache Management**: Automatically clears skin cache to prevent persistent skin issues in Minecraft 1.20+
- **Multi-Version Support**: Launch different Minecraft versions with isolated instances
- **Custom Java Arguments**: Configure memory allocation and other JVM parameters
- **Real-time Logging**: View Minecraft output in real-time within the launcher interface

## Prerequisites

- Python 3.8 or higher (ideally python **3.14**)
- Java 25 or 21 or 17 (Depends on which Minecraft Version you run)

## Installation
- Before Installation: Its recommended to use a Venv

1. Clone the repository:
```bash
git clone https://github.com/radin6262/MCL.git
cd MCL

2. Install dependencies:
bash
pip install -r requirements.txt

3. Configure your launcher settings in `config.json` (if applicable)

## Usage

### Basic Launch
bash
python main.py

### Command Line Options

--username <name>      Specify Minecraft username
--version <version>    Specify Minecraft version (default: latest)
--ram <mb>            Set RAM allocation in MB (default: 4096)
--fullscreen          Launch in fullscreen mode

### Skin Cache Management
The launcher automatically handles skin cache clearing to prevent persistent skin issues. This is necessary because Minecraft 1.20+ caches skins locally at `.minecraft/assets/skins/<uuid>/`.

## Raw Project Structure(Before installing a Minecraft version)


.
├── main.py              # Main launcher application
├── base.py and offline.py                  # Authentication handlers
├── launcher.py         # Minecraft process management
├── skin.py         # Yggdrasil and skin management server/service
├── requirements.txt         # Python Pip requirements
└── README.md                # This file

## Configuration

### Authentication
The launcher uses `player.json` for player data and `offline_account.json` for account caching. These files are automatically generated on first run.

### Java Settings
You can configure custom java args from settings section(just make sure you know what your doing)

## Troubleshooting

### Common Issues

1. **Skin Persistence**: If skins aren't updating, manually delete `.minecraft/assets/skins/` before launching.

2. **Java Errors**: Ensure Java 8+ is installed and accessible in PATH(if isn't go to settings>Java and select your java executable).

3. **Authentication Failures**: Delete `offline_account.json` and `player.json` to reset authentication.

4. **Launcher Crashes After Game Exit**: This is a Known bug and is gonna be fixed asap.

### Debug Mode
authlib-injector (the system we use to inject our skins and etc) has debug to true by default

## Development

### Setting Up Development Environment
- We recommend you using vs code or pycharm to configure and run venv
bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

## Contributing
- Coming soon

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- Minecraft and Mojang for the game
- The Minecraft community for various launcher implementations
- Contributors to the Python Minecraft launcher ecosystem

## Support

For issues and feature requests, please use the GitHub Issues page.

---

**Note**: This launcher is not connected/owned in anyway by microsoft/mojang
