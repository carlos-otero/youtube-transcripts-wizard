# YouTube Transcripts Wizard (Windows, Python 3.10)

Small Windows-friendly toolkit to **list videos from a YouTube channel/playlist** and **download transcripts** for each video using [`youtube-transcript-api`](https://pypi.org/project/youtube-transcript-api/) and `yt-dlp`. It includes a simple **interactive wizard** you can double‑click on Windows. No coding required.

> This repo ships with a ready-to-run Python script (`yt_channel_transcripts2_checker.py`) and two Windows launchers (BAT/PowerShell) pinned to **Python 3.10**.

---

## Features

- List all videos from a channel (handles the **Videos** tab, nested shelves, and falls back to the channel's **Uploads** playlist).
- Fetch transcripts in **TXT / JSON / SRT / VTT**.
- **Skip already-downloaded** videos using an **existing files policy**:
  - `same-format` (default): skip if the **same format** already exists.
  - `any-format`: skip if **any** transcript format already exists.
  - `none`: ignore disk checks.
- **Dry-run** mode to preview actions without downloading.
- Optional language fallback and translation (when available on YouTube).

---

## Requirements

- **Windows** (for the launchers; the Python script itself works on other OSes).
- **Python 3.10** with the Windows launcher (`py`).  
- Python packages:
  - `yt-dlp`
  - `youtube-transcript-api`

The launchers will auto-install these packages **for Python 3.10** if missing.

> If you prefer to run the Python script directly, install dependencies manually:
>
> ```bash
> py -3.10 -m pip install -U yt-dlp youtube-transcript-api
> ```

---

## Files

- `yt_channel_transcripts2_checker.py` — Core Python script (channel/playlist listing + transcript downloader + existing-files checker).
- `Transcripts-Wizard-310-EN.bat` — CMD wizard (English prompts), pinned to **Python 3.10**.
- `Transcripts-Wizard-310-EN.ps1` — PowerShell wizard (English prompts), pinned to **Python 3.10**.

> Place the launcher and the Python script **in the same folder**.

---

## Quick Start (Windows)

### Option A — Double‑click the wizard

1. Put `Transcripts-Wizard-310-EN.bat` (or `.ps1`) **next to** `yt_channel_transcripts2_checker.py`.
2. Double‑click the launcher.
3. Answer the prompts:
   - **URL** (channel/playlist/video)
   - **Output folder** (e.g., `out`)
   - **Format** (`txt`, `json`, `srt`, `vtt`)
   - **Languages** (space‑separated, e.g., `es en`)
   - Include **Shorts**?
   - **Existing files policy**: `same-format` / `any-format` / `none`
   - Filters: `since` / `until` (YYYY-MM-DD), `translate-to`
   - Limits: `max`, `workers`
   - **Overwrite** exact file? / **Dry-run**?

The wizard builds and executes the final command for you.

### Option B — Run the Python script directly

```bash
py -3.10 yt_channel_transcripts2_checker.py "https://www.youtube.com/@ChannelHandle" ^
  -o out -f srt -l es en --existing-policy same-format --workers 8 --since 2024-01-01
```

> On PowerShell, remove the `^` line continuations or replace with backticks `` ` ``.

---

## Output

- Transcript files saved in the output folder as:
  ```
  YYYY-MM-DD_<VIDEOID>_<slugified-title>.<ext>
  ```
- An `index.csv` is written with the status of each video:
  - `ok`, `skipped-existing`, `skipped`, `no_transcript`, `write_error`, etc.

---

## Notes

- PowerShell may block scripts by default. To allow running local scripts (once):
  ```powershell
  Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
  ```
- This project **does not** require any YouTube API keys.
- Some videos simply **do not have transcripts** on YouTube. The script will mark them as `no_transcript` unless you later add an ASR fallback (not included in this minimalist version).

---

## License

MIT — do whatever, but no warranty.
