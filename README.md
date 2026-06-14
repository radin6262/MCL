# MCL - A Minecraft Launcher

Python is not Java.

---

## Features

* **Offline Authentication**: Supports offline authentication without requiring Mojang servers.
* **Multi-Version Support**: Launch different Minecraft versions with isolated instances.
* **Custom Java Arguments**: Configure memory allocation and other JVM parameters.
* **Real-Time Logging**: View Minecraft output directly from the launcher interface.

---

## Prerequisites

* Python 3.8 or higher (Python 3.14 recommended)
* Java 17, 21, or 25 (depending on the Minecraft version you run)

---

## Installation From Source

> It is recommended to use a virtual environment (venv).

1. Clone the repository:

```bash
git clone https://github.com/radin6262/MCL.git
cd MCL
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Launcher configuration is handled inside the application.

---

## Windows Installation

1. Go to the GitHub Releases page.
2. Download the latest release.
3. Run the installer or executable.
4. Choose a directory for MCL.
5. (Optional) Create a folder named `MCL` to keep launcher files organized.
6. Launch MCL.

> The first startup may take longer than usual while required files are initialized.

---

## Usage

### Basic Launch

```bash
python main.py
```

---

## Project Structure

```text
.
├── main.py                 # Main launcher application
├── base.py                 # Base authentication handler
├── offline.py              # Offline authentication handler
├── launcher.py             # Minecraft process management
├── requirements.txt        # Python dependencies
└── README.md               # This file
```

---

## Configuration

### Authentication

The launcher uses `player.json` and `offline_account.json` to store account information. These files are generated automatically on first launch.

### Java Settings

Custom Java arguments can be configured from the Settings page.

Only modify these settings if you understand what they do.

---

## In-App Configuration

Before launching Minecraft for the first time, configure your account and authentication settings.

### 1. Configure Your Account

1. Open the **Account Settings** tab.
2. Enter your desired username.
3. Click **Generate Random UUID**.

### 2. Configure Your Settings

1. Open the **Settings** tab.
2. Set your preferred game resolution or enable **Fullscreen** mode.
3. Configure the amount of memory (RAM) allocated to Minecraft.

   * You can restore the recommended default value (**4 GB**) by clicking the reset/default button.
4. Ensure the Java version you want to use is installed and available in your system's PATH.
5. If you have multiple Java installations, select the Java executable you want Minecraft to use.

> **Recommendation:** Java 25 is recommended because it can run all modern Minecraft versions supported by MCL. If you prefer another Java version, make sure the correct Java executable is selected in the launcher settings.

After completing these steps, the launcher is ready to launch Minecraft.

---

## Launching the Game

1. Select a Minecraft version.
2. Click **Download** if the version is not installed.
3. Wait for the download to finish.
4. Click **Launch**.
5. If the game crashes, try downloading the version again.
6. If the issue persists, submit an issue on GitHub.

> Warning: A console window may briefly appear while launching Minecraft. This is normal and is used to start the Java process.

---

## Troubleshooting

### Common Issues

#### Java Errors

Ensure Java is installed and available in your system PATH.

Alternatively, open **Settings → Java** and manually select your Java executable.

#### Authentication Issues

Delete the following files and restart the launcher:

```text
offline_account.json
player.json
```

#### Launcher Crashes After Game Exit

This is a known issue and will be fixed in a future release.

#### Random Launcher Crashes

If you are running MCL directly from an IDE such as VS Code or PyCharm, resource conflicts may occur.

For best results, run the launcher from:

* Windows PowerShell
* Command Prompt (CMD)

---

## Development

### Development Environment Setup

You may use VS Code or PyCharm for development.

```bash
python -m venv .venv

.venv\Scripts\activate

pip install -r requirements-dev.txt
```

---

## Contributing

Coming soon.

---

## License

This project is licensed under the MIT License.

See the `LICENSE` file for details.

---

## Acknowledgments

* Minecraft and Mojang for the game.
* The Minecraft community for launcher-related resources and documentation.
* Contributors to the Python Minecraft launcher ecosystem.

---

## Support

For bug reports, feature requests, and questions, please use the GitHub Issues page.

---

**Disclaimer:** MCL is not affiliated with, endorsed by, or associated with Microsoft, Mojang, or Minecraft.
