@echo off

chcp 65001 >nul

setlocal EnableExtensions



cd /d "%~dp0"



set "PYEXE=python"

if exist ".venv\Scripts\python.exe" (

    set "PYEXE=.venv\Scripts\python.exe"

)



"%PYEXE%" --version >nul 2>&1

if errorlevel 1 (

    where py >nul 2>&1

    if not errorlevel 1 (

        set "PYEXE=py -3"

    ) else (

        echo [ERROR] Python not found. Install Python 3.11+ and add to PATH.

        pause

        exit /b 1

    )

)



if not exist "paper_ops_app.html" (

    echo [ERROR] paper_ops_app.html not found in:

    echo %CD%

    pause

    exit /b 1

)



if not exist "app.py" (

    echo [ERROR] app.py not found in:

    echo %CD%

    pause

    exit /b 1

)



"%PYEXE%" -c "import PySide6; from PySide6.QtWebEngineWidgets import QWebEngineView" >nul 2>&1

if errorlevel 1 (

    echo [ERROR] Missing dependencies. Installing...

    "%PYEXE%" -m pip install -r requirements.txt

    if errorlevel 1 (

        echo [ERROR] pip install failed.

        pause

        exit /b 1

    )

)



echo Starting OPC UA Gateway...

"%PYEXE%" app.py

set "EXIT_CODE=%ERRORLEVEL%"



if not "%EXIT_CODE%"=="0" (

    echo.

    echo [ERROR] Program exited with code %EXIT_CODE%

    pause

)



exit /b %EXIT_CODE%

