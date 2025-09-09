# Transcripts Wizard (PowerShell, Python 3.10, EN)
# Place next to: yt_channel_transcripts2_checker.py

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$script = Join-Path $here "yt_channel_transcripts2_checker.py"

# Fixed Python 3.10
$py = "py"
$pyver = "-3.10"
try {
  & $py $pyver --version | Out-Null
} catch {
  throw "Could not run 'py -3.10'. Install Python 3.10 or edit this script to point to your python.exe."
}

if (-not (Test-Path $script)) {
  throw "Not found: $script. Place this .ps1 next to yt_channel_transcripts2_checker.py"
}

# Ensure deps for THIS interpreter
try { & $py $pyver -c "import yt_dlp" | Out-Null } catch {
  Write-Host "Installing 'yt-dlp' for Python 3.10..." -ForegroundColor Cyan
  & $py $pyver -m pip install --user -U yt_dlp
}
try { & $py $pyver -c "import youtube_transcript_api" | Out-Null } catch {
  Write-Host "Installing 'youtube-transcript-api' for Python 3.10..." -ForegroundColor Cyan
  & $py $pyver -m pip install --user -U youtube_transcript_api
}

# Inputs
$url = Read-Host "URL (channel/playlist/video)"
if (-not $url) { throw "URL is required" }

$outdir = Read-Host "Output folder (default: channel_transcripts)"
if (-not $outdir) { $outdir = "channel_transcripts" }

$format = Read-Host "Format (txt/json/srt/vtt) (default: txt)"
if (-not $format) { $format = "txt" }

$langs = Read-Host "Languages (space-separated) (default: es en)"
if (-not $langs) { $langs = "es en" }

$inc = Read-Host "Include Shorts? Y/N (default: N)"
$flagShorts = @()
if ($inc -match '^[yY]$') { $flagShorts = @("--include-shorts") }

$exist = Read-Host "Existing policy same-format/any-format/none (default: same-format)"
if (-not $exist) { $exist = "same-format" }

$since = Read-Host "Since date (YYYY-MM-DD) (Enter to skip)"
$until = Read-Host "Until date (YYYY-MM-DD) (Enter to skip)"
$translate = Read-Host "Translate to language (e.g. es) (Enter to skip)"
$max = Read-Host "Max videos (Enter=all)"

$workers = Read-Host "Concurrent workers (default: 8)"; if (-not $workers) { $workers = "8" }
$overw = Read-Host "Overwrite exact existing files? Y/N (default: N)"
$flagOver = @(); if ($overw -match '^[yY]$') { $flagOver = @("--overwrite") }
$dry = Read-Host "Dry-run (simulate)? Y/N (default: N)"
$flagDry = @(); if ($dry -match '^[yY]$') { $flagDry = @("--dry-run") }

$args = @($script, $url, "-o", $outdir, "-f", $format, "--existing-policy", $exist, "-l") + $langs.Split(" ") + @("--workers", $workers) + $flagShorts + $flagOver + $flagDry
if ($since) { $args += @("--since", $since) }
if ($until) { $args += @("--until", $until) }
if ($translate) { $args += @("--translate-to", $translate) }
if ($max) { $args += @("--max", $max) }

Write-Host ""
Write-Host "Final command:" -ForegroundColor Cyan
Write-Host "$py $pyver $($args -join ' ')" -ForegroundColor Yellow
Write-Host ""

& $py $pyver @args
