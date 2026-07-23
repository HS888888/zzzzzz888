@echo off
chcp 65001 >nul
cd /d "%~dp0"
start "" "OPC_UA_Gateway.exe"
