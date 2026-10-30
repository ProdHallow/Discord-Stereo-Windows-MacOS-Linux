@echo off
setlocal DisableDelayedExpansion
title Discord Voice Node Patcher
set "STEREO_BOOTSTRAP_SELF=%~f0"
set "STEREO_BOOTSTRAP_SCRIPT=Discord_voice_node_patcher.ps1"
set "STEREO_BOOTSTRAP_DIR=%TEMP%\StereoBootstrap-%RANDOM%-%RANDOM%"
echo Fetching Discord_voice_node_patcher.ps1 from GitHub...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$s=[IO.File]::ReadAllText($env:STEREO_BOOTSTRAP_SELF); & ([ScriptBlock]::Create($s.Substring($s.LastIndexOf('# BOOTSTRAP_POWERSHELL'))))"
if errorlevel 1 goto download_failed
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%STEREO_BOOTSTRAP_DIR%\Discord_voice_node_patcher.ps1" %*
set "STEREO_EXIT=%ERRORLEVEL%"
goto cleanup
:download_failed
set "STEREO_EXIT=1"
echo Download failed. No patcher or installer was started.
:cleanup
powershell.exe -NoProfile -NonInteractive -Command "$p=[IO.Path]::GetFullPath($env:STEREO_BOOTSTRAP_DIR); $t=[IO.Path]::GetFullPath($env:TEMP).TrimEnd([IO.Path]::DirectorySeparatorChar); if([IO.Path]::GetDirectoryName($p) -eq $t -and [IO.Path]::GetFileName($p) -match '^StereoBootstrap-\d+-\d+$'){ $f=Join-Path $p $env:STEREO_BOOTSTRAP_SCRIPT; if(Test-Path -LiteralPath $f){Remove-Item -LiteralPath $f -Force}; if(Test-Path -LiteralPath $p){Remove-Item -LiteralPath $p -ErrorAction SilentlyContinue} }"
if "%~1"=="" pause
exit /b %STEREO_EXIT%

# BOOTSTRAP_POWERSHELL
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    $directory = [IO.Path]::GetFullPath($env:STEREO_BOOTSTRAP_DIR)
    $tempRoot = [IO.Path]::GetFullPath($env:TEMP).TrimEnd([IO.Path]::DirectorySeparatorChar)
    if ([IO.Path]::GetDirectoryName($directory) -ne $tempRoot -or [IO.Path]::GetFileName($directory) -notmatch '^StereoBootstrap-\d+-\d+$' -or (Test-Path -LiteralPath $directory)) {throw 'Invalid or occupied download folder.'}
    if ($env:STEREO_BOOTSTRAP_SCRIPT -notin @('Discord_voice_node_patcher.ps1','DiscordVoiceFixer.ps1')) {throw 'Invalid launcher target.'}
    [void][IO.Directory]::CreateDirectory($directory)
    $file = Join-Path $directory $env:STEREO_BOOTSTRAP_SCRIPT
    $uri = 'https://raw.githubusercontent.com/ProdHallow/Discord-Stereo-Windows-MacOS-Linux/main/Updates/Windows/'+$env:STEREO_BOOTSTRAP_SCRIPT+'?t='+[guid]::NewGuid().ToString('N')
    Invoke-WebRequest -Uri $uri -OutFile $file -UseBasicParsing -TimeoutSec 120 -Headers @{'Cache-Control'='no-cache';'Pragma'='no-cache'} | Out-Null
    if ((Get-Item -LiteralPath $file).Length -lt 100) {throw 'Downloaded script is empty or incomplete.'}
    $tokens=$null; $parseErrors=$null
    [void][Management.Automation.Language.Parser]::ParseFile($file,[ref]$tokens,[ref]$parseErrors)
    if ($parseErrors.Count) {throw ('Downloaded script failed syntax validation: '+$parseErrors[0].Message)}
    if ($env:STEREO_BOOTSTRAP_SCRIPT -eq 'Discord_voice_node_patcher.ps1') {
        $body = [IO.File]::ReadAllText($file)
        $version = [regex]::Match($body,'(?m)^\$Script:SCRIPT_VERSION\s*=\s*"([0-9.]+)"')
        if (-not $version.Success -or [version]$version.Groups[1].Value -lt [version]'24.3') {throw 'Publish patcher v24.3 or newer to GitHub before using this launcher.'}
    }
    exit 0
} catch {
    Write-Host ('ERROR: '+$_) -ForegroundColor Red
    exit 1
}
