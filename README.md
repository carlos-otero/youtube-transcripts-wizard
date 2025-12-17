# YouTube Transcripts Manager v3.2 (Linux & Windows)

A powerful, cross-platform toolkit to **manage, download, and update** YouTube channel transcripts. Designed for power users and AI enthusiasts.

> **New in v3.2:** > 🧠 **AI-Ready:** Automatically splits massive transcripts into chunks (perfect for ChatGPT/Gemini context limits).  
> 🏠 **Home Assistant Integration:** Auto-restarts your Router/ONT if YouTube blocks your IP.  
> ♾️ **Unattended Mode:** Endless loop that downloads, detects bans, resets internet, and resumes automatically.

---

## 🚀 Key Features

* **Interactive Menu:** Run without arguments to launch the App Mode.
* **Smart Updates:** "Remembers" your channels. Select "Update All" to fetch only new videos.
* **Anti-Ban System:** Detects YouTube 429 errors (IP Block) instantly.
* **Auto-Healing Connection:** Can trigger a **Home Assistant script** to reboot your ONT/Router and waits until the internet connection (Ping 8.8.8.8) is back before resuming.
* **Credential Manager:** Saves Webshare/Proxy secrets locally (`config.json`).
* **Smart Merge & Split:** * Merges all channel videos into chronological text files.
    * **Auto-Split:** If the file exceeds ~1MB (approx 250k tokens), it splits into `Part01`, `Part02`... to fit into LLMs like Gemini Pro 1.5.
* **Readable Format:** `[HH:MM:SS] Text...` format.

---

## 📋 Requirements

* **Python 3.10+**
* **Windows** or **Linux** (Fedora, Ubuntu, Debian...)
* Python packages (Auto-installed): `yt-dlp`, `youtube-transcript-api`

---

## ⚡ Quick Start (Interactive Mode)

### 🐧 Linux
```bash
# Option A: Using the helper script (Recommended)
./menu.sh

# Option B: Using Python directly (activate venv first)
python3 yt_channel_transcripts2_checker.py

```

### 🪟 Windows

Double-click `Transcripts-Wizard-310-EN.bat`.

---

## 🎮 The Menu

```text
==================================================
   📺 YOUTUBE TRANSCRIPTS MANAGER v3.2
==================================================
1. 🔄 Update an existing channel
2. 🚀 Update ALL downloaded channels
3. ➕ Add a new channel
4. 🏠 Configure Home Assistant
5. 📚 Re-Merge & Split (Prepare for AI)
6. 🔌 Reset ONT (Test HA)
7. ♾️  UNATTENDED AUTO MODE (Loop + Auto Reset)
0. ❌ Exit

```

* **Option 5 (Re-Merge):** Scans your downloaded channels and creates/updates the merged files in `full_merges/`. It applies the **Split Logic** automatically.
* **Option 7 (Unattended):** The "Set and Forget" mode. It will download everything. If blocked, it reboots your router, verifies internet connection, and continues exactly where it left off.

---

## 🏠 Home Assistant Setup (Auto-Reset)

To enable automatic IP rotation when blocked:

1. Go to **Option 4** in the menu.
2. Enter your HA URL (e.g., `http://192.168.1.50:8123`).
3. Enter a **Long-Lived Access Token** (Get it from your User Profile in HA).
4. Enter the Script Entity ID that reboots your router (e.g., `script.restart_ont`).

> The tool will verify real internet connectivity (Ping Google DNS) after the restart before resuming downloads.

---

## 📂 Folder Structure

```text
.
├── full_merges/                  # AI-Ready Files
│   ├── Huberman_2024-05-20_Part01.txt
│   └── Huberman_2024-05-20_Part02.txt
├── channel_transcripts/          # Source Data
│   └── Andrew_Huberman/
│       ├── .channel_meta.json    # Metadata (URL, config)
│       ├── index.csv             # Database
│       ├── Video_Title-ID.txt
│       └── ...
├── config.json                   # Secrets (Ignored by Git)
└── yt_channel_transcripts2_checker.py

```

---

## 🛡️ Security Note

The `config.json` file containing your Proxy/HA credentials is automatically added to `.gitignore`. **Never share this file.**

---

## License

MIT.