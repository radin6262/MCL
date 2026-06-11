# Minecraft Launcher

A custom Minecraft launcher with offline authentication support and skin caching management.

## Features

- **Offline Authentication**: Supports offline/Yggdrasil authentication without requiring Mojang servers
- **Skin Cache Management**: Automatically clears skin cache to prevent persistent skin issues in Minecraft 1.20+
- **Multi-Version Support**: Launch different Minecraft versions with isolated instances
- **Custom Java Arguments**: Configure memory allocation and other JVM parameters
- **Real-time Logging**: View Minecraft output in real-time within the launcher interface

## Prerequisites

- Python 3.8 or higher
- Java 8 or higher (for Minecraft)
- Git (for version control)

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd minecraft-launcher

2. Install dependencies:
bash
pip install -r requirements.txt

3. Configure your launcher settings in `config.json` (if applicable)

## Usage

### Basic Launch
bash
python launcher.py

### Command Line Options

--username <name>      Specify Minecraft username
--version <version>    Specify Minecraft version (default: latest)
--ram <mb>            Set RAM allocation in MB (default: 4096)
--fullscreen          Launch in fullscreen mode

### Skin Cache Management
The launcher automatically handles skin cache clearing to prevent persistent skin issues. This is necessary because Minecraft 1.20+ caches skins locally at `.minecraft/assets/skins/<uuid>/`.

## Project Structure


.
├── launcher.py              # Main launcher application
├── auth.py                  # Authentication handlers
├── game_launcher.py         # Minecraft process management
├── config.json              # Configuration file (ignored)
├── player.json              # Player data (ignored)
├── offline_account.json     # Account cache (ignored)
├── .minecraft/              # Minecraft runtime (ignored)
├── instances/               # Version instances (ignored)
├── .venv/                   # Python virtual environment (ignored)
└── README.md                # This file

## Configuration

### Authentication
The launcher uses `player.json` for player data and `offline_account.json` for account caching. These files are automatically generated on first run.

### Java Settings
Configure Java path and arguments in the launcher settings or via command line:
- `-Xmx4096M`: Default memory allocation (4GB)
- `-XX:+UseG1GC`: Garbage collector optimization
- `-Dfml.ignoreInvalidMinecraftCertificates=true`: Certificate validation bypass

## Troubleshooting

### Common Issues

1. **Skin Persistence**: If skins aren't updating, manually delete `.minecraft/assets/skins/` before launching.

2. **Java Errors**: Ensure Java 8+ is installed and accessible in PATH.

3. **Authentication Failures**: Delete `offline_account.json` and `player.json` to reset authentication.

4. **Launcher Crashes After Game Exit**: This is typically a threading/GUI issue. Ensure GUI updates happen on the main thread.

### Debug Mode
Enable debug logging by setting `DEBUG=True` in the launcher configuration.

## Development

### Setting Up Development Environment
bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

### Running Tests
bash
python -m pytest tests/

### Code Style
This project uses:
- Black for code formatting
- Flake8 for linting
- MyPy for type checking

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- Minecraft and Mojang for the game
- The Minecraft community for various launcher implementations
- Contributors to the Python Minecraft launcher ecosystem

## Support

For issues and feature requests, please use the GitHub Issues page.

---

**Note**: This launcher is for educational purposes. Always respect Mojang's EULA and use official authentication methods when possible.
