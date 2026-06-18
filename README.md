# MCL

> A modern, open-source Minecraft launcher written in Python.

> **Running MCL from source is intended for developers only.**
> If you simply want to play Minecraft, **download the latest release from the GitHub Releases page instead.** Running from source may require additional setup and troubleshooting.

---

## Features

* **Offline Authentication** – Play Minecraft without a Microsoft account.
* **Multi-Version Support** – Download and launch multiple Minecraft versions with isolated instances.
* **Custom Java Management** – Select your preferred Java installation and customize JVM arguments.
* **Real-Time Logging** – View Minecraft output directly inside the launcher.
* **Skin Support** – Import custom player skins.
* **Easy Configuration** – Manage launcher settings through a simple graphical interface.

---

## Requirements

### Operating System

* Windows 10 or newer (officially supported)

### Python *(only required when running from source)*

* Python **3.10** or newer
* **Python 3.14 is recommended**

### Java

* Java **17**, **21**, or **25**
* **Java 25 is recommended**, as it supports all Minecraft versions supported by MCL.

---

# Download (Recommended)

For most users, **download a pre-built release**.

1. Go to the GitHub **Releases** page.
2. Download the latest release.
3. Run the installer or executable.
4. Launch MCL.

> The first launch may take a few moments while the launcher initializes and downloads required files.

---

# Building From Source (Developers)

> **Building from source is not recommended unless you are developing or contributing to MCL.**
>
> If you only want to play Minecraft, download the latest release instead.

## Clone the Repository

```bash
git clone https://github.com/radin6262/MCL.git
cd MCL
```

## Create a Virtual Environment (Recommended)

```bash
python -m venv .venv
```

### Windows

```bat
.venv\Scripts\activate
```

### Linux/macOS

```bash
source .venv/bin/activate
```

## Install Dependencies

```bash
pip install -r requirements.txt
```

## Launch MCL

```bash
python main.py
```

---

# First-Time Setup

Before launching Minecraft for the first time:

## Configure Your Account

1. Open the **Account Settings** tab.
2. Enter your preferred username.
3. Click **Generate Random UUID**.

## Configure the Launcher

1. Open the **Settings** tab.
2. Configure your preferred game resolution or enable **Fullscreen**.
3. Adjust the amount of RAM allocated to Minecraft.
4. Install **Authlib** from the **Authlib** section.
5. Select the Java executable you want MCL to use.
6. (Optional) Import a skin from the **Skins** page.

> Java 25 is recommended because it supports all Minecraft versions currently supported by MCL.

---

# Launching Minecraft

1. Select a Minecraft version.
2. Click **Download** if the version is not installed.
3. Wait for the download to complete.
4. Click **Launch**.

If the game fails to start:

* Try downloading the version again.
* Verify that the correct Java installation is selected.
* If the issue persists, open an issue on GitHub.

> A console window may briefly appear while Minecraft is starting. This is expected behavior.

---

# Troubleshooting

## Java Not Found

Ensure Java is installed and available, then open **Settings → Java** and select the correct Java executable.

---

## Authentication Issues

Delete the following files and restart MCL:

```text
offline_account.json
player.json
```

---

## Launcher Crashes

Running MCL directly from an IDE such as VS Code or PyCharm may occasionally cause resource conflicts.

For testing, it is recommended to run MCL from:

* Command Prompt
* Windows PowerShell
* Windows Terminal

---

# Development

Install development dependencies:

```bash
pip install -r requirements-dev.txt
```

Contributions are welcome.

---

# License

This project is licensed under the MIT License.

See the `LICENSE` file for details.

---

# Disclaimer

MCL is an independent project and is **not affiliated with, endorsed by, or associated with Microsoft, Mojang, or Minecraft**.
