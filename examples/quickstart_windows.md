# Quickstart examples (Windows)

## A) Double-click the wizard (recommended)
- Put `Transcripts-Wizard-310-EN.bat` next to `yt_channel_transcripts2_checker.py`.
- Double-click and answer the prompts.

## B) CMD (single line)
py -3.10 yt_channel_transcripts2_checker.py "https://www.youtube.com/@ChannelHandle" -o out -f srt -l es en --existing-policy same-format --workers 8 --since 2024-01-01

## C) PowerShell
py -3.10 yt_channel_transcripts2_checker.py "https://www.youtube.com/@ChannelHandle" `
  -o out -f txt -l es en --existing-policy any-format --max 50

## D) Dry-run to preview
py -3.10 yt_channel_transcripts2_checker.py "https://www.youtube.com/@ChannelHandle" -o out -f txt --dry-run
