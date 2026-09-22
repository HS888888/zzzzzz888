@echo off

chcp 65001 >nul

setlocal EnableExtensions EnableDelayedExpansion



cd /d "%~dp0"

set "PROJECT_ROOT=%CD%"

set "BUILD_ROOT=%TEMP%\OPC_UA_Gateway_build"



echo === OPC UA Gateway: production build (exe + DLL) ===

echo.



python --version >nul 2>&1

if errorlevel 1 (

    echo [ERROR] Python not found in PATH. Install Python 3.11+ and try again.

    exit /b 1

)



echo [1/6] Preparing build workspace (ASCII path for PyInstaller)...

if exist "%BUILD_ROOT%" rmdir /s /q "%BUILD_ROOT%"

mkdir "%BUILD_ROOT%"

robocopy "%PROJECT_ROOT%" "%BUILD_ROOT%" /E /XD build dist production\OPC_UA_Gateway .git /NFL /NDL /NJH /NJS /nc /ns /np >nul

if errorlevel 8 (

    echo [ERROR] Failed to copy sources to %BUILD_ROOT%

    exit /b 1

)

pushd "%BUILD_ROOT%"



echo.

echo [2/6] Installing runtime dependencies...

python -m pip install --upgrade pip

python -m pip install -r requirements.txt

if errorlevel 1 (

    echo [ERROR] Failed to install requirements.txt

    popd

    exit /b 1

)



echo.

echo [3/6] Installing PyInstaller...

python -m pip install -r requirements-build.txt

if errorlevel 1 (

    echo [ERROR] Failed to install requirements-build.txt

    popd

    exit /b 1

)



echo.

echo [4/6] Building dist\MS SERVICE\ (may take a few minutes)...

set "BUILD_OK=0"

for /L %%I in (1,1,5) do (

    if "!BUILD_OK!"=="0" (

        echo Attempt %%I/5...

        python -m PyInstaller --noconfirm --clean build_exe.spec

        if not errorlevel 1 if exist "dist\MS SERVICE\MS SERVICE.exe" set "BUILD_OK=1"

    )

)

if "!BUILD_OK!"=="0" (

    echo [ERROR] PyInstaller failed after 5 attempts

    popd

    exit /b 1

)



echo.

echo [5/6] Copying to production\MS SERVICE\ in project folder...

if exist "%PROJECT_ROOT%\production\MS SERVICE" rmdir /s /q "%PROJECT_ROOT%\production\MS SERVICE"

mkdir "%PROJECT_ROOT%\production\MS SERVICE"

xcopy "dist\MS SERVICE\*" "%PROJECT_ROOT%\production\MS SERVICE\" /E /I /Y >nul

if errorlevel 1 (

    echo [ERROR] Failed to copy build output to production folder

    popd

    exit /b 1

)



python "%PROJECT_ROOT%\copy_packaging.py"



popd



echo.

echo [6/6] Done.

echo.

echo Production folder:

echo   %PROJECT_ROOT%\production\MS SERVICE\

echo.

echo   MS SERVICE.exe      - launch application

echo   _internal\          - libraries (DLL)

echo   Запуск.vbs          - shortcut without a console window

echo.

echo Copy the whole OPC_UA_Gateway folder to another PC (no Python required).



endlocal

