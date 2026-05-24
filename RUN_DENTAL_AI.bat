@echo off
title Dental OPG AI Assistant
color 0B
cls

echo.
echo  ============================================================
echo   DENTAL OPG AI ASSISTANT
echo   Powered by Claude (Anthropic)
echo  ============================================================
echo.

:: ── Change to script directory ──────────────────────────────────────────────
cd /d "%~dp0"

:: ── Check Python ─────────────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    color 0C
    echo  [ERROR] Python is not installed or not in PATH.
    echo  Download it from: https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

:: ── Check API key (Anthropic or Gemini free) ─────────────────────────────────
if not "%ANTHROPIC_API_KEY%"=="" goto keys_ok
if not "%GEMINI_API_KEY%"=="" goto keys_ok

echo  No API key found. Choose a provider:
echo.
echo    [1] Google Gemini  (FREE - 1500 analyses/day)
echo        Get key at: https://aistudio.google.com/apikey
echo.
echo    [2] Anthropic Claude  (Paid - higher quality)
echo        Get key at: https://console.anthropic.com/settings/keys
echo.
set /p PROVIDER="  Enter 1 or 2: "
echo.

if "%PROVIDER%"=="1" (
    set /p GEMINI_API_KEY="  Paste your Gemini API key: "
    setx GEMINI_API_KEY "%GEMINI_API_KEY%" >nul
    echo  Gemini key saved permanently.
) else (
    set /p ANTHROPIC_API_KEY="  Paste your Anthropic API key: "
    setx ANTHROPIC_API_KEY "%ANTHROPIC_API_KEY%" >nul
    echo  Anthropic key saved permanently.
)
echo.

:keys_ok

:: ── Check if an OPG file was drag-dropped onto this bat ──────────────────────
if not "%~1"=="" (
    echo  File detected: %~nx1
    echo.
    echo  Select analysis mode:
    echo    [1] Full Analysis  (complete 9-section report)
    echo    [2] Quick Screening  (key findings only, faster)
    echo.
    set /p MODE="  Enter 1 or 2: "
    echo.
    if "%MODE%"=="2" (
        python analyse.py "%~1" --quick
    ) else (
        python analyse.py "%~1"
    )
    goto done
)

:: ── No file dropped — show menu ───────────────────────────────────────────────
echo  What would you like to do?
echo.
echo    [1]  Analyse an OPG          (full 9-section report + PDF)
echo    [2]  Quick Screening         (key findings only, faster)
echo    [3]  Analyse without PDF     (console output only)
echo    [4]  Open Web App            (browser interface)
echo    [5]  Exit
echo.
set /p CHOICE="  Enter choice (1-5): "
echo.

if "%CHOICE%"=="1" goto full
if "%CHOICE%"=="2" goto quick
if "%CHOICE%"=="3" goto nopdf
if "%CHOICE%"=="4" goto webapp
if "%CHOICE%"=="5" exit /b 0

echo  Invalid choice.
goto done

:full
python analyse.py
goto done

:quick
python analyse.py --quick
goto done

:nopdf
python analyse.py --no-pdf
goto done

:webapp
echo  Starting web app on http://localhost:8502 ...
start "" http://localhost:8502
start /B streamlit run app.py --server.port 8502
timeout /t 3 >nul
start "" http://localhost:8502
goto done

:done
echo.
echo  ============================================================
echo   Done. Press any key to close.
echo  ============================================================
pause >nul
