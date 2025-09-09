@echo off
setlocal ENABLEDELAYEDEXPANSION
title Transcripts Wizard (Python 3.10, EN)

REM --------- Fixed Python 3.10 ---------
set "PYCMD=py -3.10"
%PYCMD% --version >nul 2>nul || (
  echo [ERROR] Could not run "py -3.10".
  echo - Make sure Python 3.10 is installed with the Windows launcher "py".
  echo - Try "py -0p" to list installed versions.
  echo - Or edit this .bat and set PYCMD to the full path of your Python 3.10.
  pause
  exit /b 1
)

REM --------- Paths ---------
set "HERE=%~dp0"
set "SCRIPT=%HERE%yt_channel_transcripts2_checker.py"

if not exist "%SCRIPT%" (
  echo [ERROR] Not found: %SCRIPT%
  echo Place this .bat in the SAME folder as yt_channel_transcripts2_checker.py
  pause
  exit /b 1
)

REM --------- Ensure dependencies (for THIS 3.10 interpreter) ---------
call %PYCMD% -c "import yt_dlp" >nul 2>nul
if errorlevel 1 (
  echo Installing 'yt-dlp' for Python 3.10...
  call %PYCMD% -m pip install --user -U yt-dlp || (
    echo [ERROR] Failed to install yt-dlp. Try running as Administrator or remove --user.
    pause
    exit /b 1
  )
)

call %PYCMD% -c "import youtube_transcript_api" >nul 2>nul
if errorlevel 1 (
  echo Installing 'youtube-transcript-api' for Python 3.10...
  call %PYCMD% -m pip install --user -U youtube-transcript-api || (
    echo [ERROR] Failed to install youtube-transcript-api.
    pause
    exit /b 1
  )
)

echo ==============================================
echo   YouTube Transcripts - WIZARD (3.10, EN)
echo ==============================================
echo.

:ask_url
set "URL="
set /p URL=URL (channel/playlist/video): 
if "%URL%"=="" (
  echo URL is required.
  goto ask_url
)

set "OUTDIR="
set /p OUTDIR=Output folder (default: channel_transcripts): 
if "%OUTDIR%"=="" set "OUTDIR=channel_transcripts"

set "FORMAT="
set /p FORMAT=Format (txt/json/srt/vtt) (default: txt): 
if "%FORMAT%"=="" set "FORMAT=txt"

set "LANGS="
set /p LANGS=Languages (space-separated) (default: es en): 
if "%LANGS%"=="" set "LANGS=es en"

echo.
echo Include YouTube Shorts?
echo    Y = Yes
echo    N = No (default)
choice /C YN /N /M "Choose: "
if errorlevel 2 (set "FLAG_SHORTS=") else (set "FLAG_SHORTS=--include-shorts")

echo.
echo Existing files policy:
echo   1 = same-format  (skip if the SAME format already exists) [default]
echo   2 = any-format   (skip if ANY format already exists)
echo   3 = none         (ignore disk check)
choice /C 123 /N /M "Choose: "
set "EXISTPOL=same-format"
if errorlevel 3 set "EXISTPOL=none"
if errorlevel 2 set "EXISTPOL=any-format"

set "SINCE="
set /p SINCE=Since date (YYYY-MM-DD) (Enter to skip): 

set "UNTIL="
set /p UNTIL=Until date (YYYY-MM-DD) (Enter to skip): 

set "TRANSLATE="
set /p TRANSLATE=Translate to language (e.g. es) (Enter to skip): 

set "MAXN="
set /p MAXN=Max number of videos (Enter=all): 

set "WORKERS="
set /p WORKERS=Concurrent workers (default: 8): 
if "%WORKERS%"=="" set "WORKERS=8"

echo.
echo Overwrite EXACT existing files?
echo    Y = Yes (replace)
echo    N = No (default)
choice /C YN /N /M "Choose: "
if errorlevel 2 (set "FLAG_OVER=") else (set "FLAG_OVER=--overwrite")

echo.
echo Dry-run (simulate without downloading)?
echo    Y = Yes
echo    N = No (default)
choice /C YN /N /M "Choose: "
if errorlevel 2 (set "FLAG_DRY=") else (set "FLAG_DRY=--dry-run")

REM Extra flags
set "EXTRA="
if not "%SINCE%"=="" set "EXTRA=!EXTRA! --since %SINCE%"
if not "%UNTIL%"=="" set "EXTRA=!EXTRA! --until %UNTIL%"
if not "%TRANSLATE%"=="" set "EXTRA=!EXTRA! --translate-to %TRANSLATE%"
if not "%MAXN%"=="" set "EXTRA=!EXTRA! --max %MAXN%"

echo.
echo Final command:
echo %PYCMD% "%SCRIPT%" "%URL%" -o "%OUTDIR%" -f %FORMAT% --existing-policy %EXISTPOL% -l %LANGS% --workers %WORKERS% %FLAG_SHORTS% %FLAG_OVER% %FLAG_DRY% %EXTRA%
echo.
pause

call %PYCMD% "%SCRIPT%" "%URL%" -o "%OUTDIR%" -f %FORMAT% --existing-policy %EXISTPOL% -l %LANGS% --workers %WORKERS% %FLAG_SHORTS% %FLAG_OVER% %FLAG_DRY% %EXTRA%
echo.
pause
endlocal
