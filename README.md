# MCL - A Minecraft Launcher

Python is not Java

---

## Features

* **Offline Authentication**: Supports offline/Yggdrasil authentication without requiring Mojang servers.
* **Skin Cache Management**: Automatically clears skin cache to prevent persistent skin issues in Minecraft 1.20+.
* **Multi-Version Support**: Launch different Minecraft versions with isolated instances.
* **Custom Java Arguments**: Configure memory allocation and other JVM parameters.
* **Real-time Logging**: View Minecraft output in real-time within the launcher interface.
---
## Prerequisites

* Python 3.8 or higher (ideally **Python 3.14**)
* Java 25, 21, or 17 (depends on the Minecraft version you run)
---
## Installation From Source

> Before installation, it is recommended to use a virtual environment (venv).
---
> We Do Not recommend using VS Code or PyCharm Or any IDE with an integrated shell.
---
1. Clone the repository:

```bash
git clone https://github.com/radin6262/MCL.git
cd MCL
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Launcher Configuration Will be done in the application

---

## Windows Installation

> Note: Library CryptoGraphy used by some other py libs was the culprit of this issue. It is now patched... Probably...

1. Go to the github releases section.
2. find the **latest** release
3. find the files attached and install the exe file
4. Go the directory you want the launcher to be installed
5. create a folder called MCL(not required but the launcher will generate some files like minecraft assets or settings)
6. Run MCL (it will be slow when you run the app for the **first** time)
7. If windows defender flags the app as potentially unwanted please go to you AV(antivirus) settings and and select allow on device then click apply
8. learn more on why windows security/defender flags this on some device [click me](https://github.com/radin6262/MCL#defender)

## Usage

### Basic Launch

```bash
python main.py
```


### Skin Cache Management

The launcher automatically handles skin cache clearing to prevent persistent skin issues. This is necessary because Minecraft 1.20+ caches skins locally at:

```text
.minecraft/assets/skins/
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

## In-App Configuration

Before launching Minecraft for the first time, you should configure your account and authentication settings.

### 1. Configure Your Account

1. Open the **Account Settings** tab.
2. Edit your desired Minecraft username.
3. Click the **Generate Random UUID** button to create a UUID for your account.

- Restart The Application to apply changes

### 2. Install Authlib(for skin management)

1. Open the **Settings** tab.
2. Navigate to the **Authlib** section.
3. Click **Install Authlib** and wait for the installation to complete.

### 3. Import a Skin

1. Open the **Skin** tab.
2. Click **Import Skin**.
3. Select a valid Minecraft skin PNG file.
4. If skin is vaild you will be prompted by a success msgbox

After completing these steps, your launcher is ready to start Minecraft with custom authentication and skin support.

---

## Launching the Game

1. Select a version
2. Click download to download the version
3. after downloading finished click launch to launch the game
4. if the game crashed re-download it using the button
5. if that fails too reach out to the community or submit an issue at the github issues page
> *Warning*: if a shell gets launched don't worry its the java shell we use it to launch the game but for some issues it shows up. but its not supposed to. this is a known bug and will be fix as soon as possibile(a long time later **:D**)





## Troubleshooting

### Common Issues

1. **Skin Persistence**: If skins aren't updating, manually delete `.minecraft/assets/skins/` before launching.
2. **Java Errors**: Ensure Java is installed and accessible in your PATH. If not, go to **Settings → Java** and select your Java executable.
3. **Authentication Failures**: Delete `offline_account.json` and `player.json` to reset authentication.
4. **Launcher Crashes After Game Exit**: This is a known bug and will be fixed as soon as possible.
5. **Launcher Crashes Randomly Or After Game Launch**: This Issue isn't from the application. if you are running this application on pycharm or vscode this will happen(resource fighting)

### Debug Mode

`authlib-injector` (the system used to inject skins, player data, etc.) has debug mode enabled by default.

---
## Defender
Windows Defender flags MCL's custom skin server(that is running on your device when you launch the game) due to using network and currently i have made a patch(an unused rsa generator was causing this) but windows defender may still flag the skin server... and well i as the main developer can't do something about it.
well i can get a cert but that would cost 300-500$ a month.

> Note: Library CryptoGraphy used by some other py libs was the culprit of this issue. It is now patched... Probably...

---
## Development

### Setting Up the Development Environment

We Recommend You Use VsCode or Pycharm but for running the application we recommend you use the windows powershell or cmd

```bash
python -m venv .venv

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
