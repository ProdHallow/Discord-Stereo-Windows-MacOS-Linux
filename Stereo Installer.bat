@echo off
title Stereo Installer
echo Downloading latest Stereo Installer...
powershell -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/ProdHallow/installer/main/DiscordVoiceFixer.ps1 | iex"
