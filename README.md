# YouTube Transcripts Wizard (Windows & Linux)

A powerful cross-platform toolkit to **list videos from a YouTube channel/playlist** and **download transcripts** for each video. It includes robust **Anti-Ban features**, **Proxy support**, and **Smart Merging**.

Includes interactive wizards for **Windows** (BAT/PowerShell) and **Linux** (Bash). No coding required.

---

## 🚀 New Features

* **Cross-Platform:** Works on Windows and Linux (Fedora/Ubuntu/Debian, etc.).
* **Smart Organization:** Saves transcripts in `channel_transcripts/CHANNEL_NAME/`.
* **Readable Format:** TXT files now include **[HH:MM:SS] timestamps**.
* **Anti-Ban System:** Detects if YouTube blocks your IP (429 Too Many Requests), stops the script safely, and waits for you to change IP (e.g., reset router) to resume without losing progress.
* **Proxy Support:** Native integration for **Webshare** and Generic HTTP/HTTPS proxies.
* **Merge Function:** Optionally combines ALL downloaded transcripts into a single chronological `FULL_MERGE.txt` file (perfect for LLMs/ChatGPT).
* **Existing Files Policy:** Skips already downloaded videos to save time and bandwidth.

---

## 📋 Requirements

* **Python 3.10+**
* **Windows** or **Linux**
* Python packages (Auto-installed by the wizards):
    * `yt-dlp`
    * `youtube-transcript-api`

---

## 📂 Files

* `yt_channel_transcripts2_checker.py` — Core Python script (The engine).
* `wizard_linux.sh` — **New** Linux Launcher (Bash). Handles venv & dependencies automatically.
* `Transcripts-Wizard-310-EN.bat` — Windows CMD Launcher.
* `Transcripts-Wizard-310-EN.ps1` — Windows PowerShell Launcher.

---

## ⚡ Quick Start

### 🐧 Linux (Fedora, Ubuntu, etc.)

1.  Open your terminal in the folder.
2.  Give execution permissions (only once):
    ```bash
    chmod +x wizard_linux.sh
    ```
3.  Run the wizard:
    ```bash
    ./wizard_linux.sh
    ```
4.  Follow the prompts (URL, Languages, Proxy options, etc.).

### 🪟 Windows

1.  Double-click `Transcripts-Wizard-310-EN.bat`.
2.  Answer the prompts.

---

## 🛡️ Anti-Ban & Proxies

YouTube often blocks IPs ("Sign in to confirm you are not a bot") when fetching many transcripts rapidly. This tool handles it in two ways:

### 1. The "Router Reset" Method (Free)
If you don't use a proxy and YouTube blocks you:
1.  The script detects the **Critical IP Block** and **STOPS** immediately.
2.  It saves the progress of everything downloaded so far.
3.  **Action:** Turn off your Router/Modem for 10 seconds and turn it on again (to get a new dynamic IP).
4.  Run the script again. It will skip the existing files and continue.

### 2. Proxies (Recommended for heavy use)
The wizard allows you to configure:
* **Webshare:** (Recommended) Enter your Username/Password.
* **Generic Proxy:** `http://user:pass@host:port`.

---

## 📂 Output Structure

The tool creates a folder structure like this:

```text
channel_transcripts/
└── Andrew_Huberman/
    ├── index.csv                     # Database of all videos & status
    ├── FULL_MERGE_Andrew_Huberman.txt # (Optional) All transcripts merged
    ├── Welcome_to_the_Lab-VideoID.txt
    ├── Sleep_Toolkit-VideoID.txt
    └── ...
````

### TXT Format Example

```text Welcome to the Huberman Lab Podcast. Today we are going to discuss...
```

-----

## 🛠️ CLI Usage (Manual)

If you prefer running the Python script directly without the wizard:

```bash
# Basic run
python3 yt_channel_transcripts2_checker.py "[https://www.youtube.com/@Channel](https://www.youtube.com/@Channel)"

# Advanced run (Spanish, Webshare Proxy, Merge compatible)
python3 yt_channel_transcripts2_checker.py "URL" \
  -o out -f txt -l es en \
  --webshare-user "user" --webshare-pass "pass" \
  --include-shorts
```

-----

## License

MIT.
