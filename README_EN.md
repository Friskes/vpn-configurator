# VPN Configurator

> [🇷🇺 Russian version — README.md](README.md)

> [!IMPORTANT]
> This material is prepared for scientific and technical purposes. Using the provided materials for purposes other than familiarization may be a violation of applicable law.
> The author is not responsible for any improper use of this material!

**VPN Configurator** is an interactive command-line tool for creating VPN client configuration files with **split tunneling**, as well as for converting and merging IP address files.

**Split tunneling** is a VPN mode where only traffic to specified websites or services goes through the VPN, while everything else continues to work at full speed without any slowdown.

---

### Ready-to-use IP address sets in the `ips/` folder

The repository already includes IP address files for the following services:

| File | Service |
|---|---|
| `youtube.txt` | YouTube |
| `chatgpt.txt` | ChatGPT / OpenAI |
| `discord.txt` | Discord |
| `ghcopilot.txt` | GitHub Copilot |
| `instagram.txt` | Instagram |
| `jetbrains.txt` | JetBrains |
| `telegram.txt` | Telegram |
| `whatsapp.txt` | WhatsApp |
| `all.txt` | All services above merged into a single file |

You can use these files as-is or find additional sets using the links in the [Where to get IP addresses](#where-to-get-ip-addresses) section.

---

## What the Program Can Do

After launching, the program shows an interactive menu with five modes:

**1. Create a config for Amnezia / WireSock / WireGuard**
Based on an existing `.conf` VPN file, creates a new configuration file with the specified IP addresses for split tunneling over the WireGuard protocol.
- Option A: only the **specified IPs** go through the VPN
- Option B: **all traffic** goes through the VPN (only obfuscation is added to the file)
- Supported clients: **Amnezia**, **WireSock**, **WireGuard**, and other compatible WG clients.

**2. Create a config for Nekobox (Android)**
Creates a `.json` configuration file for the Nekobox app on Android using the VLESS protocol.
- Option A: only the **specified IPs** go through the VPN, all other traffic is direct
- Option B: **all traffic** goes through the VPN, except the specified IPs

**3. Convert: Amnezia → plaintext**
Converts an IP address file from the Amnezia format (`.json`) to a plain text format (`.txt`), where each IP is on its own line.

**4. Convert: plaintext → Amnezia**
Reverse conversion — from plain text format to Amnezia format (`.json`).

**5. Merge IP address files**
Combines multiple IP address files (in plaintext or Amnezia format) into a single file, automatically removing duplicates.

---

## How to Run the Program

### Option 1 — .exe file (Windows)

1. Download the `.exe` file from the releases page: **[⬇ GitHub Releases](https://github.com/Friskes/vpn-configurator/releases/latest)**
2. **Double-click** the downloaded file — a console window with the program menu will open
3. Type the number of the desired option and follow the prompts

---

### Option 2 — file for macOS

> Unlike Windows, double-clicking a binary file on macOS does not open it in a terminal — you need to launch it manually through the **Terminal** app (not "Console").

1. Download the file for your CPU architecture from the releases page: **[⬇ GitHub Releases](https://github.com/Friskes/vpn-configurator/releases/latest)**

   | Processor | File to download |
   |---|---|
   | Apple M1/M2/M3/M4 | `vpn_configurator_vX.X.X.macos-arm64` |
   | Intel | `vpn_configurator_vX.X.X.macos-x86_64` |

   > Not sure which one you have? Click  → "About This Mac" — the "Chip" or "Processor" line will tell you.
2. Open the **Terminal** app (not "Console")
3. Navigate to the folder with the downloaded file:
   ```bash
   cd ~/Downloads
   ```
4. Grant the file permission to run (replace with the name of your downloaded file):
   ```bash
   chmod +x vpn_configurator_vX.X.X.macos-arm64
   ```
5. Run the program:
   ```bash
   ./vpn_configurator_vX.X.X.macos-arm64
   ```

---

### Option 3 — Python script

If you have Python 3.10 or higher installed, you can run the source script directly.

1. Clone or download this repository
2. Open a terminal in the project folder and run the following commands one by one:

   **Windows:**
   ```
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   python vpn_configurator.py
   ```

   **macOS / Linux:**
   ```bash
   python3 -m venv venv
   . venv/bin/activate
   pip3 install -r requirements.txt
   python3 vpn_configurator.py
   ```

---

## How the Program Works

The program is fully interactive — no command-line arguments or technical knowledge required. After launching, it displays a numbered main menu. You type the number of the action you need, and the program guides you from there: it asks questions one step at a time, hints at what to enter, and reports any errors in plain language. At the end of each scenario it confirms that the file was created successfully and exits.

---

## Importing the Configuration into an App

### Amnezia (Windows / Android)

1. Tap the `+` icon on the main screen of the app
2. Select **"The connection settings file"**
3. Choose the generated `.conf` file
4. If the app suggests enabling obfuscation — be sure to agree
5. Tap **"Connect"**

Done — the profile is created and ready to use!

---

### WireGuard / WireSock (Windows)

Open the WireGuard (or WireSock) app and import the generated `.conf` file via the **"Add tunnel from file"** menu.

---

### Nekobox (Android)

1. Go to the **"Configuration"** page in the Nekobox app
2. Tap the `file+` icon
3. Select **"Import from file"**
4. Point to the generated `.json` file

Done — the profile is created and ready to use!

---

## Where to Get IP Addresses

Ready-to-use sets are already available in the [`ips/`](https://github.com/Friskes/vpn-configurator/tree/main/ips) folder. If you need additional services, use these resources:

- [Various IP address collections (gist)](https://gist.github.com/iamwildtuna/7772b7c84a11bf6e1385f23096a73a15)
- [IP addresses in Amnezia format (gist)](https://gist.github.com/iamwildtuna/ea245d39c60753db9150e5fb0da4a5b7)
- [IP address ranges website 1](https://rockblack.su/vpn/dopolnitelno/diapazon-ip-adresov)
- [IP address ranges website 2](https://rockblack.pro/vpn/dopolnitelno/diapazon-ip-adresov)
- [iplist.opencck.org](https://iplist.opencck.org)
- [antifilter.download](https://antifilter.download/)
- [Discord IP addresses](https://github.com/GhostRooter0953/discord-voice-ips)

---

## Useful Links

- [Amnezia VPN](https://github.com/amnezia-vpn/amnezia-client) — VPN client with obfuscation support for Windows, macOS, Android, iOS
- [WireSock VPN Client](https://www.wiresock.net/) — WireGuard client for Windows with split tunneling support
- [WireGuard](https://github.com/WireGuard/wireguard-windows) — official WireGuard client for Windows
- [Nekobox for Android](https://github.com/MatsuriDayo/NekoBoxForAndroid) — proxy client for Android with VLESS support
- [Nekobox for Windows / Linux / macOS](https://github.com/MatsuriDayo/nekoray) — desktop proxy client with VLESS support
