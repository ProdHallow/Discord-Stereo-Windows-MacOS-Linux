@echo off
title Discord Voice Node Patcher
echo Downloading Discord Voice Node Patcher...

set "PS1=%TEMP%\discord_voice_node_patcher.ps1"

powershell -ExecutionPolicy Bypass -Command ^
"Invoke-RestMethod 'https://raw.githubusercontent.com/ProdHallow/Discord-Node-Patcher-Feb-9-2026/main/Discord_voice_node_patcher.ps1' -OutFile '%PS1%'"

powershell -ExecutionPolicy Bypass -File "%PS1%"

pause
