[CmdletBinding()]
param(
    [ValidateRange(1, 10)][int]$AudioGainMultiplier = 1,
    [switch]$SkipBackup,
    [switch]$Restore,
    [switch]$ListBackups,
    [switch]$FixAll,
    [string]$FixClient,
    [switch]$PatchLocalOnly,
    [switch]$SkipUpdateCheck
)

$ErrorActionPreference = "Stop"
$ProgressPreference = 'SilentlyContinue'

Add-Type -AssemblyName System.Windows.Forms, System.Drawing -ErrorAction SilentlyContinue

# TLS 1.2 for GitHub/HTTPS on older hosts.
try {
    if ([Net.ServicePointManager]::SecurityProtocol -band [Net.SecurityProtocolType]::Tls12 -eq 0) {
        [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    }
} catch { }

# Self-update URL (raw script on GitHub).
$Script:UPDATE_URL_BASE = "https://raw.githubusercontent.com/ProdHallow/Discord-Stereo-Windows-MacOS-Linux/main/Updates/Windows/Discord_voice_node_patcher.ps1"
$Script:SCRIPT_VERSION = "8"

# region Offsets

$Script:OffsetsMeta = @{
    FinderVersion = "discord_voice_node_offset_finder.py v5.1.3"
    DiscordAppBuild   = "1.0.9234"
    MD5               = "e4bdf195be0190f210786483cb9373fb"
}

$Script:Offsets = @{
    CreateAudioFrameStereo             = 0x115BB1
    AudioEncoderOpusConfigSetChannels  = 0x3A6174
    MonoDownmixer                      = 0xD533E
    EmulateStereoSuccess1              = 0x531CCB
    EmulateStereoSuccess2              = 0x531CD7
    EmulateBitrateModified             = 0x53212A
    SetsBitrateBitrateValue            = 0x533F51
    SetsBitrateBitwiseOr               = 0x533F59
    Emulate48Khz                       = 0x531E33
    HighPassFilter                     = 0x53DF40
    HighpassCutoffFilter               = 0x8D2C50
    DcReject                           = 0x8D2E30
    DownmixFunc                        = 0x8CEFC0
    AudioEncoderOpusConfigIsOk         = 0x3A6410
    ThrowError                         = 0x2BC7A0
    EncoderConfigInit1                 = 0x3A617E
    EncoderConfigInit2                 = 0x3A5A87
    OpusPacketLossCvtt1                = 0x53333A
    OpusPacketLossCvtt2                = 0x5334A7
    NetEqDelayMgr_MsPerLossPercent     = 0xA9A94D
    Pacer_BlockAudio_Disable           = 0x6D7462
    Discord_SetAutomaticGainControl_1  = 0x6EF60
    Discord_SetAutomaticGainControl_2  = 0x6F270
    Discord_SetNoiseSuppression_1      = 0x6E8B0
    Discord_SetNoiseSuppression_2      = 0x6EBB0
    Discord_SetEchoCancellation_1      = 0x6E290
    Discord_SetEchoCancellation_2      = 0x6E8A0
    Discord_SetEchoCancellationPre     = 0x6E590
    Discord_EnableBuiltInAEC           = 0x6DF90
    Discord_SetNoiseCancellation       = 0x6F280
    Discord_SetNoiseCancellationAfter  = 0x70120
    Discord_SetNoiseCancellationDuring = 0x6FE10
    Discord_SetNoiseCancellationStats  = 0x6FB00
    Discord_SetSidechainCompression    = 0x87900
    Discord_SetHasFullbandPerformance  = 0x89DD0
    Discord_SetDuckingPreference       = 0x7FAE0
    Discord_SetIdleJitterBufferFlush   = 0x6DC80
    Discord_SetAudioInputEnabled       = 0x87600
    Discord_SetAecDump                 = 0x84EA0
}

# endregion Offsets

# Offsets required before C++ codegen / copy block (order = PATCHER_OFFSET_NAMES in offset finder)
$Script:RequiredOffsetNames = @(
    "CreateAudioFrameStereo", "AudioEncoderOpusConfigSetChannels", "MonoDownmixer",
    "EmulateStereoSuccess1", "EmulateStereoSuccess2", "EmulateBitrateModified",
    "SetsBitrateBitrateValue", "SetsBitrateBitwiseOr", "Emulate48Khz",
    "HighPassFilter", "HighpassCutoffFilter", "DcReject", "DownmixFunc",
    "AudioEncoderOpusConfigIsOk", "ThrowError",
    "EncoderConfigInit1", "EncoderConfigInit2",
    "OpusPacketLossCvtt1", "OpusPacketLossCvtt2",
    "NetEqDelayMgr_MsPerLossPercent", "Pacer_BlockAudio_Disable",
    "Discord_SetAutomaticGainControl_1", "Discord_SetAutomaticGainControl_2",
    "Discord_SetNoiseSuppression_1", "Discord_SetNoiseSuppression_2",
    "Discord_SetEchoCancellation_1", "Discord_SetEchoCancellation_2",
    "Discord_SetEchoCancellationPre",
    "Discord_EnableBuiltInAEC",
    "Discord_SetNoiseCancellation", "Discord_SetNoiseCancellationAfter",
    "Discord_SetNoiseCancellationDuring", "Discord_SetNoiseCancellationStats",
    "Discord_SetSidechainCompression", "Discord_SetHasFullbandPerformance",
    "Discord_SetDuckingPreference", "Discord_SetIdleJitterBufferFlush",
    "Discord_SetAudioInputEnabled", "Discord_SetAecDump"
)

# region Patch Definitions

$Script:PatchGroups = [ordered]@{
    STEREO = [ordered]@{
        EmulateStereoSuccess1 = @{ Name = "EmulateStereoSuccess1 (channels=2)"; Hex = "02" }
        EmulateStereoSuccess2 = @{ Name = "EmulateStereoSuccess2 (jne->jmp)"; Hex = "EB" }
        CreateAudioFrameStereo = @{ Name = "CreateAudioFrameStereo"; Hex = "49 89 C5 90" }
        AudioEncoderOpusConfigSetChannels = @{ Name = "AudioEncoderConfigSetChannels (ch=2)"; Hex = "02" }
        MonoDownmixer = @{ Name = "MonoDownmixer (NOP sled + JMP)"; Hex = "90 90 90 90 90 90 90 90 90 90 90 90 E9" }
    }
    BITRATE = [ordered]@{
        EmulateBitrateModified = @{ Name = "EmulateBitrateModified (384kbps)"; Hex = "00 DC 05" }
        SetsBitrateBitrateValue = @{ Name = "SetsBitrateBitrateValue (384kbps)"; Hex = "00 DC 05 00 00" }
        SetsBitrateBitwiseOr = @{ Name = "SetsBitrateBitwiseOr (NOP)"; Hex = "90 90 90" }
    }
    SAMPLERATE = [ordered]@{
        Emulate48Khz = @{ Name = "Emulate48Khz (NOP cmovb)"; Hex = "90 90 90" }
    }
    FILTER = [ordered]@{
        HighPassFilter = @{ Name = "HighPassFilter (RET stub)"; Hex = "mov rax, imm64; ret" }
        HighpassCutoffFilter = @{ Name = "HighpassCutoffFilter (inject hp_cutoff)"; Hex = "shellcode" }
        DcReject = @{ Name = "DcReject (inject dc_reject)"; Hex = "shellcode" }
        DownmixFunc = @{ Name = "DownmixFunc (RET)"; Hex = "C3" }
        AudioEncoderOpusConfigIsOk = @{ Name = "AudioEncoderConfigIsOk (RET true)"; Hex = "48 C7 C0 01 ... C3" }
        ThrowError = @{ Name = "ThrowError (RET)"; Hex = "C3" }
    }
    ENCODER = [ordered]@{
        EncoderConfigInit1 = @{ Name = "EncoderConfigInit1 (32000->384000)"; Hex = "00 DC 05 00" }
        EncoderConfigInit2 = @{ Name = "EncoderConfigInit2 (32000->384000)"; Hex = "00 DC 05 00" }
    }
    PACKETLOSS = [ordered]@{
        OpusPacketLossCvtt1 = @{ Name = "Opus packet loss rate -> 0 (site 1)"; Hex = "31 D2 90 90" }
        OpusPacketLossCvtt2 = @{ Name = "Opus packet loss rate -> 0 (site 2)"; Hex = "31 D2 90 90" }
    }
    NETEQ = [ordered]@{
        NetEqDelayMgr_MsPerLossPercent = @{ Name = "NetEq delay inflation -> 0 (ms_per_loss_percent)"; Hex = "48 B8 00 00 00 00 00 00 00 00" }
    }
    PACING = [ordered]@{
        Pacer_BlockAudio_Disable = @{ Name = "Pacer BlockAudio -> false"; Hex = "30 DB 90" }
    }
    DISCORD_API_LOCK = [ordered]@{
        Discord_SetAutomaticGainControl_1 = @{ Name = "Discord::SetAutomaticGainControl (variant 1)"; Hex = "C3" }
        Discord_SetAutomaticGainControl_2 = @{ Name = "Discord::SetAutomaticGainControl (variant 2)"; Hex = "C3" }
        Discord_SetNoiseSuppression_1     = @{ Name = "Discord::SetNoiseSuppression (variant 1)"; Hex = "C3" }
        Discord_SetNoiseSuppression_2     = @{ Name = "Discord::SetNoiseSuppression (variant 2)"; Hex = "C3" }
        Discord_SetEchoCancellation_1     = @{ Name = "Discord::SetEchoCancellation (variant 1)"; Hex = "C3" }
        Discord_SetEchoCancellation_2     = @{ Name = "Discord::SetEchoCancellation (variant 2)"; Hex = "C3" }
        Discord_SetEchoCancellationPre    = @{ Name = "Discord::SetEchoCancellationPreEcho"; Hex = "C3" }
        Discord_SetNoiseCancellation      = @{ Name = "Discord::SetNoiseCancellation"; Hex = "C3" }
        Discord_SetNoiseCancellationAfter = @{ Name = "Discord::SetNoiseCancellationAfterProcessing"; Hex = "C3" }
        Discord_SetNoiseCancellationDuring= @{ Name = "Discord::SetNoiseCancellationDuringProcessing"; Hex = "C3" }
        Discord_SetNoiseCancellationStats = @{ Name = "Discord::SetNoiseCancellationEnableStats"; Hex = "C3" }
        Discord_SetSidechainCompression   = @{ Name = "Discord::SetSidechainCompression"; Hex = "C3" }
        Discord_SetHasFullbandPerformance = @{ Name = "Discord::SetHasFullbandPerformance"; Hex = "C3" }
        Discord_EnableBuiltInAEC          = @{ Name = "Discord::EnableBuiltInAEC"; Hex = "C3" }
        Discord_SetDuckingPreference      = @{ Name = "Discord::SetDuckingPreference"; Hex = "C3" }
        Discord_SetIdleJitterBufferFlush  = @{ Name = "Discord::SetIdleJitterBufferFlush"; Hex = "C3" }
        Discord_SetAudioInputEnabled      = @{ Name = "Discord::SetAudioInputEnabled"; Hex = "C3" }
        Discord_SetAecDump                = @{ Name = "Discord::SetAecDump"; Hex = "C3" }
    }
}

$Script:AllPatchKeys = [System.Collections.Generic.List[string]]::new()
foreach ($grp in $Script:PatchGroups.Values) {
    foreach ($k in $grp.Keys) { $Script:AllPatchKeys.Add($k) }
}

$Script:SelectedPatches = @{}
foreach ($k in $Script:AllPatchKeys) { $Script:SelectedPatches[$k] = $true }

# Discord can fail to launch if DISCORD_API_LOCK offsets drift. Keep it opt-in.
foreach ($k in $Script:PatchGroups.DISCORD_API_LOCK.Keys) { $Script:SelectedPatches[$k] = $false }

# endregion Patch Definitions

# region Console
function Wait-EnterOrTimeout {
    param([int]$Seconds = 60)
    $msg = "Press Enter to exit (auto-close in ${Seconds}s)..."
    try {
        Write-Host $msg
        $end = [DateTime]::UtcNow.AddSeconds($Seconds)
        while ([DateTime]::UtcNow -lt $end) {
            if ([Console]::KeyAvailable) {
                $k = [Console]::ReadKey($true)
                if ($k.Key -eq 'Enter') { return }
            }
            Start-Sleep -Milliseconds 300
        }
    } catch {
        Start-Sleep -Seconds $Seconds
    }
}

# endregion Console

# region Auto-Elevation

$currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "Requesting administrator privileges..." -ForegroundColor Yellow
    try {
        $arguments = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$PSCommandPath`"")
        if ($PSBoundParameters.ContainsKey('AudioGainMultiplier')) { $arguments += "-AudioGainMultiplier", $AudioGainMultiplier }
        if ($SkipBackup) { $arguments += "-SkipBackup" }
        if ($Restore) { $arguments += "-Restore" }
        if ($ListBackups) { $arguments += "-ListBackups" }
        if ($FixAll) { $arguments += "-FixAll" }
        if ($FixClient) { $arguments += "-FixClient", $FixClient }
        if ($PatchLocalOnly) { $arguments += "-PatchLocalOnly" }
        if ($SkipUpdateCheck) { $arguments += "-SkipUpdateCheck" }
        Start-Process powershell.exe -ArgumentList $arguments -Verb RunAs
        exit 0
    } catch {
        Write-Host "ERROR: Failed to elevate. Please run as Administrator manually." -ForegroundColor Red
        Wait-EnterOrTimeout; exit 1
    }
}

# endregion Auto-Elevation

# region Configuration

$Script:GainExplicitlySet = $PSBoundParameters.ContainsKey('AudioGainMultiplier')
$Script:Config = @{
    SampleRate = 48000; Bitrate = 384; Channels = "Stereo"
    AudioGainMultiplier = $AudioGainMultiplier; SkipBackup = $SkipBackup.IsPresent; AutoRelaunch = $true
    ModuleName = "discord_voice.node"
    TempDir = "$env:TEMP\DiscordVoicePatcher"; BackupDir = "$env:TEMP\DiscordVoicePatcher\Backups"
    LogFile = "$env:TEMP\DiscordVoicePatcher\patcher.log"; ConfigFile = "$env:TEMP\DiscordVoicePatcher\config.json"
    # Backups can be large; keep only a few per client and prune old ones.
    MaxBackupsPerClient = 3
    MaxBackupAgeDays      = 45
    VoiceBackupAPI = "https://api.github.com/repos/ProdHallow/Discord-Stereo-Windows-MacOS-Linux/contents/Updates%2FNodes%2FUnpatched%20Nodes%20%28For%20Patcher%29%2FWindows"
    OffsetsMeta = $Script:OffsetsMeta
    Offsets     = $Script:Offsets
}
$Script:DoFixAll = $false

$Script:DiscordClients = [ordered]@{
    0 = @{Name="Discord - Stable         [Official]"; Path="$env:LOCALAPPDATA\Discord";            Processes=@("Discord","Update");            Exe="Discord.exe";            Shortcut="Discord"}
    1 = @{Name="Discord - Canary         [Official]"; Path="$env:LOCALAPPDATA\DiscordCanary";      Processes=@("DiscordCanary","Update");      Exe="DiscordCanary.exe";      Shortcut="Discord Canary"}
    2 = @{Name="Discord - PTB            [Official]"; Path="$env:LOCALAPPDATA\DiscordPTB";         Processes=@("DiscordPTB","Update");         Exe="DiscordPTB.exe";         Shortcut="Discord PTB"}
    3 = @{Name="Discord - Development    [Official]"; Path="$env:LOCALAPPDATA\DiscordDevelopment"; Processes=@("DiscordDevelopment","Update"); Exe="DiscordDevelopment.exe"; Shortcut="Discord Development"}
    4 = @{Name="Lightcord                [Mod]";      Path="$env:LOCALAPPDATA\Lightcord";          Processes=@("Lightcord","Update");          Exe="Lightcord.exe";          Shortcut="Lightcord"}
    5 = @{Name="BetterDiscord            [Mod]";      Path="$env:LOCALAPPDATA\Discord";            Processes=@("Discord","Update");            Exe="Discord.exe";            Shortcut="Discord";          DetectPath="$env:APPDATA\BetterDiscord"}
    6 = @{Name="Vencord                  [Mod]";      Path="$env:LOCALAPPDATA\Vencord";            FallbackPath="$env:LOCALAPPDATA\Discord"; Processes=@("Vencord","Discord","Update");       Exe="Discord.exe"; Shortcut="Vencord";       DetectPath="$env:APPDATA\Vencord"}
    7 = @{Name="Equicord                 [Mod]";      Path="$env:LOCALAPPDATA\Equicord";           FallbackPath="$env:LOCALAPPDATA\Discord"; Processes=@("Equicord","Discord","Update");      Exe="Discord.exe"; Shortcut="Equicord";      DetectPath="$env:APPDATA\Equicord"}
    8 = @{Name="BetterVencord            [Mod]";      Path="$env:LOCALAPPDATA\BetterVencord";      FallbackPath="$env:LOCALAPPDATA\Discord"; Processes=@("BetterVencord","Discord","Update"); Exe="Discord.exe"; Shortcut="BetterVencord"; DetectPath="$env:APPDATA\BetterVencord"}
}

# endregion Configuration

# region Voice Node Helpers
function Get-FileMd5Hex {
    param([Parameter(Mandatory)][string]$Path)
    try {
        if (Get-Command Get-FileHash -ErrorAction SilentlyContinue) {
            return (Get-FileHash -Path $Path -Algorithm MD5).Hash.ToLowerInvariant()
        }
    } catch { }
    $md5 = [System.Security.Cryptography.MD5]::Create()
    try {
        $fs = [System.IO.File]::OpenRead($Path)
        try {
            $hashBytes = $md5.ComputeHash($fs)
            return ([System.BitConverter]::ToString($hashBytes) -replace '-','').ToLowerInvariant()
        } finally { $fs.Dispose() }
    } finally { $md5.Dispose() }
}

function Get-PeFileOffsetAdjustment {
    <#
    RVA -> file offset uses: fileOffset = rva - (sectionVirtualAddress - sectionRawPointer).
    Must match the offset-finder logic (PE .text vaddr - raw_offset).
    #>
    param([Parameter(Mandatory)][string]$Path)
    try {
        $bytes = [System.IO.File]::ReadAllBytes($Path)
    } catch {
        return $null
    }
    if ($bytes.Length -lt 0x200) { return $null }
    if ($bytes[0] -ne 0x4D -or $bytes[1] -ne 0x5A) { return $null }
    $peOff = [BitConverter]::ToInt32($bytes, 0x3C)
    if ($peOff -lt 0 -or ($peOff + 24) -gt $bytes.Length) { return $null }
    if ($bytes[$peOff] -ne 0x50 -or $bytes[$peOff + 1] -ne 0x45) { return $null }
    $coff = $peOff + 4
    $numSections = [BitConverter]::ToUInt16($bytes, $coff + 2)
    $optHeaderSize = [BitConverter]::ToUInt16($bytes, $coff + 16)
    $opt = $coff + 20
    $secOffset = $opt + $optHeaderSize
    if ($secOffset -lt 0 -or ($secOffset + [int]$numSections * 40) -gt $bytes.Length) { return $null }

    for ($i = 0; $i -lt $numSections; $i++) {
        $s = $secOffset + $i * 40
        $name = ([System.Text.Encoding]::ASCII.GetString($bytes, $s, 8)).TrimEnd([char]0)
        $vaddr = [BitConverter]::ToUInt32($bytes, $s + 12)
        $rawOffset = [BitConverter]::ToUInt32($bytes, $s + 20)
        if ($name -eq '.text' -and $vaddr -gt 0) {
            $adj = [int64]$vaddr - [int64]$rawOffset
            if ($adj -ge 0 -and $adj -le 0x7FFFFFFF) { return [int]$adj }
            return $null
        }
    }
    for ($i = 0; $i -lt $numSections; $i++) {
        $s = $secOffset + $i * 40
        $vaddr = [BitConverter]::ToUInt32($bytes, $s + 12)
        $rawOffset = [BitConverter]::ToUInt32($bytes, $s + 20)
        if ($vaddr -gt 0 -and $rawOffset -gt 0) {
            $adj = [int64]$vaddr - [int64]$rawOffset
            if ($adj -ge 0 -and $adj -le 0x7FFFFFFF) { return [int]$adj }
            break
        }
    }
    return 0xC00
}

function Test-DiscordVoiceNodeOffsetAnchors {
    <#
    Same gate as the native patcher CheckBytes for Emulate48Khz / ConfigIsOk / DownmixFunc.
    Catches stale $Script:Offsets vs on-disk node (e.g. MD5 meta updated but RVA block not).
    #>
    param(
        [Parameter(Mandatory)][string]$NodePath,
        [Parameter(Mandatory)][hashtable]$Offsets,
        [int]$FileOffsetAdjustment
    )
    try {
        $bytes = [System.IO.File]::ReadAllBytes($NodePath)
    } catch {
        Write-Log "Anchor check: could not read node: $_" -Level Error
        return $false
    }
    $sz = $bytes.Length
    $slice = {
        param([int]$Rva, [int]$Len)
        $fo = $Rva - $FileOffsetAdjustment
        if ($fo -lt 0 -or ($fo + $Len) -gt $sz) { return $null }
        $out = New-Object byte[] $Len
        [Array]::Copy($bytes, $fo, $out, 0, $Len)
        return ,$out
    }
    $hex = {
        param([byte[]]$B, [int]$Len)
        (($B[0..([Math]::Min($Len, $B.Length) - 1)] | ForEach-Object { $_.ToString('X2') }) -join ' ')
    }

    $r48 = [int]$Offsets.Emulate48Khz
    $rCfg = [int]$Offsets.AudioEncoderOpusConfigIsOk
    $rDm = [int]$Offsets.DownmixFunc
    $b48 = & $slice $r48 3
    $bCfg = & $slice $rCfg 4
    $bDm = & $slice $rDm 4

    $rOp1 = $null; $bOp1 = $null
    if ($Offsets.ContainsKey('OpusPacketLossCvtt1') -and $Offsets.OpusPacketLossCvtt1) {
        $rOp1 = [int]$Offsets.OpusPacketLossCvtt1
        $bOp1 = & $slice $rOp1 4
    }
    $rOp2 = $null; $bOp2 = $null
    if ($Offsets.ContainsKey('OpusPacketLossCvtt2') -and $Offsets.OpusPacketLossCvtt2) {
        $rOp2 = [int]$Offsets.OpusPacketLossCvtt2
        $bOp2 = & $slice $rOp2 4
    }
    $rNe = $null; $bNe = $null
    if ($Offsets.ContainsKey('NetEqDelayMgr_MsPerLossPercent') -and $Offsets.NetEqDelayMgr_MsPerLossPercent) {
        $rNe = [int]$Offsets.NetEqDelayMgr_MsPerLossPercent
        $bNe = & $slice $rNe 10
    }
    $rPace = $null; $bPace = $null
    if ($Offsets.ContainsKey('Pacer_BlockAudio_Disable') -and $Offsets.Pacer_BlockAudio_Disable) {
        $rPace = [int]$Offsets.Pacer_BlockAudio_Disable
        $bPace = & $slice $rPace 3
    }
    if (-not $b48 -or -not $bCfg -or -not $bDm -or ($rOp1 -and -not $bOp1) -or ($rOp2 -and -not $bOp2) -or ($rNe -and -not $bNe) -or ($rPace -and -not $bPace)) {
        Write-Log "Anchor check: RVA->file offset out of range (FILE_OFFSET_ADJUSTMENT=0x$('{0:X}' -f $FileOffsetAdjustment))." -Level Error
        return $false
    }

    $ok48 = (
        ($b48[0] -eq 0x0F -and $b48[1] -eq 0x42 -and $b48[2] -eq 0xC1) -or
        ($b48[0] -eq 0x90 -and $b48[1] -eq 0x90 -and $b48[2] -eq 0x90)
    )
    $okCfg = (
        ($bCfg[0] -eq 0x8B -and $bCfg[1] -eq 0x11 -and $bCfg[2] -eq 0x31 -and $bCfg[3] -eq 0xC0) -or
        ($bCfg[0] -eq 0x48 -and $bCfg[1] -eq 0xC7 -and $bCfg[2] -eq 0xC0 -and $bCfg[3] -eq 0x01)
    )
    $okDm = (
        ($bDm[0] -eq 0x41 -and $bDm[1] -eq 0x57 -and $bDm[2] -eq 0x41 -and $bDm[3] -eq 0x56) -or
        ($bDm[0] -eq 0xC3)
    )

    $okNe = $true
    if ($rNe) {
        # Accept original imm64 (0xC800000014) or patched imm64 (0)
        $okNe = (
            ($bNe[0] -eq 0x48 -and $bNe[1] -eq 0xB8 -and $bNe[2] -eq 0x14 -and $bNe[6] -eq 0xC8 -and ($bNe[3..5] | Where-Object { $_ -ne 0 }).Count -eq 0 -and ($bNe[7..9] | Where-Object { $_ -ne 0 }).Count -eq 0) -or
            ($bNe[0] -eq 0x48 -and $bNe[1] -eq 0xB8 -and ($bNe[2..9] | Where-Object { $_ -ne 0 }).Count -eq 0)
        )
    }

    $okOp1 = $true
    if ($rOp1) {
        # cvttss2si edx,xmm0 (F2 0F 2C D0) or patched xor edx,edx; nop nop
        $okOp1 = (
            ($bOp1[0] -eq 0xF2 -and $bOp1[1] -eq 0x0F -and $bOp1[2] -eq 0x2C -and $bOp1[3] -eq 0xD0) -or
            ($bOp1[0] -eq 0x31 -and $bOp1[1] -eq 0xD2 -and $bOp1[2] -eq 0x90 -and $bOp1[3] -eq 0x90)
        )
    }
    $okOp2 = $true
    if ($rOp2) {
        $okOp2 = (
            ($bOp2[0] -eq 0xF2 -and $bOp2[1] -eq 0x0F -and $bOp2[2] -eq 0x2C -and $bOp2[3] -eq 0xD0) -or
            ($bOp2[0] -eq 0x31 -and $bOp2[1] -eq 0xD2 -and $bOp2[2] -eq 0x90 -and $bOp2[3] -eq 0x90)
        )
    }

    $okPace = $true
    if ($rPace) {
        # Accept original setz bl or patched xor bl,bl; nop
        $okPace = (
            ($bPace[0] -eq 0x0F -and $bPace[1] -eq 0x94 -and $bPace[2] -eq 0xC3) -or
            ($bPace[0] -eq 0x30 -and $bPace[1] -eq 0xDB -and $bPace[2] -eq 0x90)
        )
    }

    if ($ok48 -and $okCfg -and $okDm -and $okNe -and $okOp1 -and $okOp2 -and $okPace) { return $true }

    Write-Log "Pre-patch anchor check failed (offsets do not match this discord_voice.node file)." -Level Error
    Write-Log ("  FILE_OFFSET_ADJUSTMENT=0x{0:X} (from PE .text); update # region Offsets in this script (offset finder)." -f $FileOffsetAdjustment) -Level Error
    Write-Log ("  Emulate48Khz @0x{0:X} file 0x{1:X}: {2} (expected 0F 42 C1 or 90 90 90)" -f $r48, ($r48 - $FileOffsetAdjustment), (& $hex $b48 3)) -Level Error
    Write-Log ("  ConfigIsOk   @0x{0:X} file 0x{1:X}: {2} (expected 8B 11 31 C0 or 48 C7 C0 01)" -f $rCfg, ($rCfg - $FileOffsetAdjustment), (& $hex $bCfg 4)) -Level Error
    Write-Log ("  DownmixFunc  @0x{0:X} file 0x{1:X}: {2} (expected 41 57 41 56 or C3)" -f $rDm, ($rDm - $FileOffsetAdjustment), (& $hex $bDm 4)) -Level Error
    if ($rOp1) { Write-Log ("  OpusPacketLossCvtt1 @0x{0:X} file 0x{1:X}: {2} (expected F2 0F 2C D0 or 31 D2 90 90)" -f $rOp1, ($rOp1 - $FileOffsetAdjustment), (& $hex $bOp1 4)) -Level Error }
    if ($rOp2) { Write-Log ("  OpusPacketLossCvtt2 @0x{0:X} file 0x{1:X}: {2} (expected F2 0F 2C D0 or 31 D2 90 90)" -f $rOp2, ($rOp2 - $FileOffsetAdjustment), (& $hex $bOp2 4)) -Level Error }
    if ($rNe) { Write-Log ("  NetEq(ms/loss) @0x{0:X} file 0x{1:X}: {2} (expected 48 B8 14 00 00 00 C8 00 00 00 or 48 B8 00..00)" -f $rNe, ($rNe - $FileOffsetAdjustment), (& $hex $bNe 10)) -Level Error }
    if ($rPace) { Write-Log ("  Pacer(BlockAudio) @0x{0:X} file 0x{1:X}: {2} (expected 0F 94 C3 or 30 DB 90)" -f $rPace, ($rPace - $FileOffsetAdjustment), (& $hex $bPace 3)) -Level Error }
    return $false
}
# endregion Voice Node Helpers

# region Logging

function Write-Log {
    param([Parameter(Mandatory)][AllowEmptyString()][AllowNull()][string]$Message, [ValidateSet('Info','Success','Warning','Error')][string]$Level = 'Info')
    if ([string]::IsNullOrEmpty($Message)) { Write-Host ""; return }
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $Script:Config.LogFile -Value "[$timestamp] [$Level] $Message" -ErrorAction SilentlyContinue
    $colors = @{ Success = 'Green'; Warning = 'Yellow'; Error = 'Red'; Info = 'White' }
    $prefixes = @{ Success = '[OK]'; Warning = '[!!]'; Error = '[XX]'; Info = '[--]' }
    Write-Host "$($prefixes[$Level]) $Message" -ForegroundColor $colors[$Level]
}

function Write-Banner {
    Write-Host "`n===== Discord Voice Quality Patcher v$Script:SCRIPT_VERSION =====" -ForegroundColor Cyan
    Write-Host "      48kHz | 384kbps | Stereo | Gain Config" -ForegroundColor Cyan
    Write-Host "         Multi-Client Detection Enabled" -ForegroundColor Cyan
    Write-Host " Requires C++ build tools (VS workload or MinGW/Clang)" -ForegroundColor Yellow
    Write-Host "===============================================`n" -ForegroundColor Cyan
}

function Show-Settings {
    $gainColor = if ($Script:Config.AudioGainMultiplier -le 2) { 'Green' } elseif ($Script:Config.AudioGainMultiplier -le 5) { 'Yellow' } else { 'Red' }
    Write-Host "Config: $($Script:Config.SampleRate)Hz, $($Script:Config.Bitrate)kbps, $($Script:Config.Channels), " -NoNewline
    Write-Host "$($Script:Config.AudioGainMultiplier)x gain" -ForegroundColor $gainColor
    Write-Host ""
}

# endregion Logging

# region User Config Persistence

function Save-UserConfig {
    try {
        EnsureDir (Split-Path $Script:Config.ConfigFile -Parent)
        @{
            LastGainMultiplier = $Script:Config.AudioGainMultiplier
            LastBackupEnabled  = -not $Script:Config.SkipBackup
            AutoRelaunch       = $Script:Config.AutoRelaunch
            LastPatchDate      = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        } | ConvertTo-Json | Out-File $Script:Config.ConfigFile -Force
    } catch { Write-Log "Failed to save config: $_" -Level Warning }
}

function Get-UserConfig {
    try {
        if (Test-Path $Script:Config.ConfigFile) {
            $content = Get-Content $Script:Config.ConfigFile -Raw
            if ([string]::IsNullOrWhiteSpace($content)) { throw "Empty" }
            $cfg = $content | ConvertFrom-Json
            if (-not $cfg.PSObject.Properties['LastGainMultiplier']) { throw "Invalid" }
            if ($null -eq $cfg.LastGainMultiplier -or ($cfg.LastGainMultiplier -is [string] -and [string]::IsNullOrWhiteSpace($cfg.LastGainMultiplier))) { throw "Invalid" }
            $num = $cfg.LastGainMultiplier
            if ($num -lt 1 -or $num -gt 10) { throw "OutOfRange" }
            return $cfg
        }
    } catch { Remove-Item $Script:Config.ConfigFile -Force -ErrorAction SilentlyContinue }
    return $null
}

function EnsureDir($p) { if ($p -and -not (Test-Path $p)) { try { [void](New-Item $p -ItemType Directory -Force) } catch { } } }

function Clear-DirectoryContentsSafe {
    param([Parameter(Mandatory)][string]$Path)
    try { $full = (Get-Item -LiteralPath $Path -ErrorAction Stop).FullName } catch { return $false }
    if ([string]::IsNullOrWhiteSpace($full)) { return $false }
    $full = $full.TrimEnd('\')
    if ($full.Length -lt 4 -or $full -match '^[A-Za-z]:$') { return $false } # avoid drive root / nonsense
    try {
        $children = @(Get-ChildItem -LiteralPath $full -Force -ErrorAction SilentlyContinue)
        foreach ($c in $children) {
            Remove-Item -LiteralPath $c.FullName -Force -Recurse -ErrorAction SilentlyContinue
        }
        return $true
    } catch {
        return $false
    }
}

function Get-EmbeddedOffsetsTargetAppId {
    param($Meta)
    if (-not $Meta) { return $null }
    $b = $Meta.DiscordAppBuild
    if ($b -and [string]$b -ne 'unspecified') { return [string]$b }
    if ($Meta -is [hashtable] -and $Meta.ContainsKey('DiscordAppVersion')) {
        $s = $Meta['DiscordAppVersion']
        if ($s -and [string]$s -ne 'unspecified') { return [string]$s }
    } elseif ($null -ne $Meta.DiscordAppVersion) {
        $s = $Meta.DiscordAppVersion
        if ($s -and [string]$s -ne 'unspecified') { return [string]$s }
    }
    $legacy = if ($Meta -is [hashtable] -and $Meta.ContainsKey('Build')) { $Meta['Build'] } else { $Meta.Build }
    if ($legacy) { return [string]$legacy }
    return $null
}

function Get-OffsetsCopyBlock {
    $meta = $Script:OffsetsMeta
    $offs = $Script:Offsets
    if (-not $meta -or -not $offs) { throw "Offsets not loaded" }
    $offsetOrder = $Script:RequiredOffsetNames
    $maxLen = ($offsetOrder | ForEach-Object { $_.Length } | Measure-Object -Maximum).Maximum
    $dab = if ($null -ne $meta.DiscordAppBuild) { $meta.DiscordAppBuild } else { 'unspecified' }
    $md5 = if ($meta.MD5) { ($meta.MD5.ToString()).ToLowerInvariant() } else { '' }
    $lines = @(
        "# region Offsets",
        "",
        "`$Script:OffsetsMeta = @{",
        "    FinderVersion = `"$($meta.FinderVersion)`"",
        "    DiscordAppBuild     = `"$dab`"",
        "    MD5                 = `"$md5`"",
        "}",
        "",
        "`$Script:Offsets = @{"
    )
    foreach ($k in $offsetOrder) {
        $val = $offs[$k]
        if ($null -eq $val) { continue }
        $pad = " " * ($maxLen - $k.Length)
        $lines += "    $k$pad = 0x$($val.ToString('X').ToUpperInvariant())"
    }
    $lines += "}"
    $lines += ""
    $lines += "# endregion Offsets"
    $lines -join "`n"
}

# endregion User Config Persistence

# region Auto-Update

function Compare-PatcherScriptVersion {
    param([string]$Left, [string]$Right)
    if ([string]::IsNullOrWhiteSpace($Left)) { $Left = '0' } else { $Left = $Left.Trim() }
    if ([string]::IsNullOrWhiteSpace($Right)) { $Right = '0' } else { $Right = $Right.Trim() }
    if ($Left -match '^\d+$' -and $Right -match '^\d+$') { return [int]$Left - [int]$Right }
    try {
        $lNorm = if ($Left -match '^\d+$') { "$Left.0.0" } else { $Left }
        $rNorm = if ($Right -match '^\d+$') { "$Right.0.0" } else { $Right }
        return ([version]$lNorm).CompareTo([version]$rNorm)
    } catch {
        return [string]::CompareOrdinal($Left, $Right)
    }
}

function Get-PatcherRestartHelperScriptContent {
    param([Parameter(Mandatory)][string]$TargetScriptPath)
    $parts = [System.Collections.Generic.List[string]]::new()
    $parts.Add('-NoProfile')
    $parts.Add('-ExecutionPolicy')
    $parts.Add('Bypass')
    $parts.Add('-File')
    $parts.Add($TargetScriptPath)
    # Read script-scope param() values (nested function does not see script $PSBoundParameters)
    $parts.Add('-AudioGainMultiplier')
    $parts.Add([string]$script:AudioGainMultiplier)
    if ($script:SkipBackup) { $parts.Add('-SkipBackup') }
    if ($script:Restore) { $parts.Add('-Restore') }
    if ($script:ListBackups) { $parts.Add('-ListBackups') }
    if ($script:FixAll) { $parts.Add('-FixAll') }
    if (-not [string]::IsNullOrWhiteSpace([string]$script:FixClient)) {
        $parts.Add('-FixClient')
        $parts.Add([string]$script:FixClient)
    }
    $sb = New-Object System.Text.StringBuilder
    [void]$sb.AppendLine('$ErrorActionPreference = "Stop"')
    [void]$sb.Append('$p = @(')
    for ($i = 0; $i -lt $parts.Count; $i++) {
        if ($i -gt 0) { [void]$sb.Append(',') }
        $esc = $parts[$i] -replace "'", "''"
        [void]$sb.Append("'$esc'")
    }
    [void]$sb.AppendLine(')')
    [void]$sb.AppendLine('Start-Process -FilePath "powershell.exe" -ArgumentList $p -WindowStyle Normal')
    return $sb.ToString()
}

function Test-ScriptUpdateAvailable {
    try {
        Write-Log "Checking for script updates from GitHub (no-cache)..." -Level Info
        if ([string]::IsNullOrEmpty($PSCommandPath)) {
            Write-Log "Running from memory / web; skip self-update check" -Level Success
            return @{ UpdateAvailable = $false; Reason = "WebExecution" }
        }
        $tempFile = Join-Path $env:TEMP "DiscordVoicePatcher_Update_$(Get-Random).ps1"
        try {
            $ts = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
            $updateUri = "$($Script:UPDATE_URL_BASE)$([char]0x3F)t=$ts&r=$(Get-Random)"
            $headers = @{
                'Cache-Control' = 'no-cache'
                'Pragma'        = 'no-cache'
            }
            Invoke-WebRequest -Uri $updateUri -OutFile $tempFile -UseBasicParsing -TimeoutSec 30 -Headers $headers | Out-Null
        } catch {
            Write-Log "Could not check for updates: $($_.Exception.Message)" -Level Warning
            return @{ UpdateAvailable = $false; Reason = "NetworkError"; Error = $_.Exception.Message }
        }
        if (-not (Test-Path $tempFile)) { return @{ UpdateAvailable = $false; Reason = "DownloadFailed" } }
        $remoteContent = (Get-Content $tempFile -Raw) -replace "`r`n", "`n" -replace "`r", "`n"
        $localContent = (Get-Content $PSCommandPath -Raw) -replace "`r`n", "`n" -replace "`r", "`n"
        $remoteContent = $remoteContent.Trim()
        $localContent = $localContent.Trim()
        if ($remoteContent -eq $localContent) {
            Remove-Item $tempFile -Force -ErrorAction SilentlyContinue
            Write-Log "Script matches GitHub (byte-for-byte)." -Level Success
            return @{ UpdateAvailable = $false; Reason = "UpToDate" }
        }
        $remoteVersion = "Unknown"
        if ($remoteContent -match '\$Script:SCRIPT_VERSION\s*=\s*"([^"]+)"') { $remoteVersion = $matches[1] }
        $localVersion = $Script:SCRIPT_VERSION
        if ($remoteVersion -eq "Unknown") {
            Remove-Item $tempFile -Force -ErrorAction SilentlyContinue
            Write-Log "Could not read remote `$Script:SCRIPT_VERSION; skipping auto-update (avoid wrong overwrite)." -Level Warning
            return @{ UpdateAvailable = $false; Reason = "RemoteVersionUnknown" }
        }
        $verCmp = Compare-PatcherScriptVersion -Left $remoteVersion -Right $localVersion
        if ($verCmp -lt 0) {
            Remove-Item $tempFile -Force -ErrorAction SilentlyContinue
            Write-Log "Local script is newer (v$localVersion) than GitHub (v$remoteVersion); not downgrading." -Level Success
            return @{ UpdateAvailable = $false; Reason = "LocalNewer" }
        }
        if ($verCmp -eq 0) {
            Remove-Item $tempFile -Force -ErrorAction SilentlyContinue
            Write-Log "Same version (v$localVersion) as GitHub but file differs; keeping local copy." -Level Info
            return @{ UpdateAvailable = $false; Reason = "SameVersionDiff" }
        }
        Write-Log "Update available: v$localVersion -> v$remoteVersion (GitHub)." -Level Warning
        return @{ UpdateAvailable = $true; TempFile = $tempFile; RemoteVersion = $remoteVersion; LocalVersion = $localVersion }
    } catch {
        Write-Log "Update check failed: $($_.Exception.Message)" -Level Warning
        if ($tempFile -and (Test-Path $tempFile)) { Remove-Item $tempFile -Force -ErrorAction SilentlyContinue }
        return @{ UpdateAvailable = $false; Reason = "Error"; Error = $_.Exception.Message }
    }
}

function Update-ScriptPatch {
    param([string]$UpdatedScriptPath, [string]$CurrentScriptPath, [switch]$RestartAfter)
    if (-not (Test-Path $UpdatedScriptPath)) { Write-Log "Update file not found: $UpdatedScriptPath" -Level Error; return $false }
    $batchFile = Join-Path $env:TEMP "DiscordVoicePatcher_Update.bat"
    # Build .bat with single-quoted lines only: "..." would parse >nul, 2>&1, & as PowerShell redirection/operators.
    $bl = [System.Collections.Generic.List[string]]::new()
    [void]$bl.Add('@echo off')
    [void]$bl.Add('echo Applying update...')
    [void]$bl.Add('timeout /t 2 /nobreak >nul')
    [void]$bl.Add(('copy /Y "{0}" "{1}" >nul' -f $UpdatedScriptPath, $CurrentScriptPath))
    [void]$bl.Add('if errorlevel 1 (')
    [void]$bl.Add('    echo Failed to copy update file!')
    [void]$bl.Add('    pause')
    [void]$bl.Add('    exit /b 1')
    [void]$bl.Add(')')
    [void]$bl.Add('echo Update applied successfully!')
    [void]$bl.Add('timeout /t 1 /nobreak >nul')
    if ($RestartAfter) {
        $restartPs1 = Join-Path $env:TEMP "DiscordVoicePatcher_Restart_$([Guid]::NewGuid().ToString('N')).ps1"
        $restartBody = Get-PatcherRestartHelperScriptContent -TargetScriptPath $CurrentScriptPath
        try {
            Set-Content -LiteralPath $restartPs1 -Value $restartBody -Encoding UTF8 -Force
            [void]$bl.Add('echo Restarting script...')
            [void]$bl.Add(('powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "{0}"' -f $restartPs1))
            [void]$bl.Add(('del "{0}" >nul 2>&1' -f $restartPs1))
        } catch {
            Write-Log "Could not write restart helper; launching script without extra args." -Level Warning
            [void]$bl.Add('echo Restarting script...')
            [void]$bl.Add(('powershell.exe -NoProfile -ExecutionPolicy Bypass -File "{0}"' -f $CurrentScriptPath))
        }
    }
    [void]$bl.Add(('del "{0}" >nul 2>&1' -f $UpdatedScriptPath))
    [void]$bl.Add('(goto) 2>nul & del "%~f0"')
    $batchContent = $bl -join "`r`n"
    $batchContent | Out-File $batchFile -Encoding ASCII -Force
    Write-Log "Update will be applied after script closes..." -Level Info
    Start-Process "cmd.exe" -ArgumentList "/c", "`"$batchFile`"" -WindowStyle Hidden
    return $true
}

# endregion Auto-Update

# region Voice Backup Download

function Save-VoiceBackupFiles {
    param([string]$DestinationPath)
    Write-Log "Downloading voice backup files from GitHub..." -Level Info
    try {
        if (Test-Path $DestinationPath) {
            Write-Log "  Clearing existing backup folder..." -Level Info
            [void](Clear-DirectoryContentsSafe -Path $DestinationPath)
        }
        EnsureDir $DestinationPath
        Write-Log "  Fetching file list from GitHub API..." -Level Info
        try {
            $headers = @{
                'User-Agent' = 'DiscordVoicePatcher'
                'Accept'     = 'application/vnd.github+json'
            }
            $response = Invoke-RestMethod -Uri $Script:Config.VoiceBackupAPI -UseBasicParsing -TimeoutSec 30 -Headers $headers
        } catch {
            try {
                $resp = $_.Exception.Response
                if ($resp -and $resp.StatusCode -eq [System.Net.HttpStatusCode]::Forbidden) {
                    throw "GitHub API rate limit exceeded. Please try again later."
                }
            } catch { }
            throw $_
        }
        $response = @($response)
        if ($response.Count -eq 0) { throw "GitHub repository response is empty." }
        $fileCount = 0
        $failedFiles = @()
        foreach ($file in $response) {
            if ($file.type -eq "file") {
                $filePath = Join-Path $DestinationPath $file.name
                Write-Log "  Downloading: $($file.name)" -Level Info
                try {
                    Invoke-WebRequest -Uri $file.download_url -OutFile $filePath -UseBasicParsing -TimeoutSec 30 | Out-Null
                    if (-not (Test-Path $filePath)) { throw "File was not created" }
                    $fileInfo = Get-Item $filePath
                    if ($fileInfo.Length -eq 0) { throw "Downloaded file is empty" }
                    $ext = [System.IO.Path]::GetExtension($file.name).ToLower()
                    if (($ext -eq ".node" -or $ext -eq ".dll") -and $fileInfo.Length -lt 1024) {
                        Write-Log "  [!] Warning: $($file.name) seems too small $($fileInfo.Length) bytes" -Level Warning
                    }
                    $fileCount++
                } catch {
                    Write-Log "  [!] Failed to download $($file.name): $($_.Exception.Message)" -Level Warning
                    $failedFiles += $file.name
                }
            }
        }
        if ($fileCount -eq 0) { throw "No valid files were downloaded." }
        if ($failedFiles.Count -gt 0) { Write-Log "  [!] Warning: $($failedFiles.Count) file(s) failed to download" -Level Warning }
        Write-Log "Downloaded $fileCount voice backup files" -Level Success
        return $true
    } catch {
        Write-Log "Failed to download voice backup files: $($_.Exception.Message)" -Level Error
        return $false
    }
}

# endregion Voice Backup Download

# region Multi-Client Detection

function Get-PathFromProcess {
    param([string]$ProcessName)
    if ([string]::IsNullOrWhiteSpace($ProcessName)) { return $null }
    try {
        $p = Get-Process -Name $ProcessName -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($p -and $p.MainModule -and $p.MainModule.FileName) { return (Split-Path (Split-Path $p.MainModule.FileName -Parent) -Parent) }
    } catch { }
    return $null
}

function Get-PathFromShortcuts {
    param([string]$ShortcutName)
    if (-not $ShortcutName) { return $null }
    $sm = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs"
    if (!(Test-Path $sm)) { return $null }
    $scs = @(Get-ChildItem $sm -Filter "$ShortcutName.lnk" -Recurse -ErrorAction SilentlyContinue)
    if ($scs.Count -eq 0) { return $null }
    $ws = $null
    try {
        $ws = New-Object -ComObject WScript.Shell
        foreach ($lf in $scs) {
            try {
                $sc = $ws.CreateShortcut($lf.FullName)
                try {
                    if ($sc.TargetPath -and (Test-Path $sc.TargetPath)) { return (Split-Path $sc.TargetPath -Parent) }
                } finally {
                    if ($sc) { try { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($sc) | Out-Null } catch { } }
                }
            } catch { }
        }
    } catch { } finally {
        if ($ws) { try { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($ws) | Out-Null } catch { } }
    }
    return $null
}

function Find-DiscordAppPath {
    param([string]$BasePath, [switch]$ReturnDiagnostics)
    if (-not $BasePath -or -not (Test-Path $BasePath)) {
        if ($ReturnDiagnostics) { return @{ Error = "InvalidBasePath" } }
        return $null
    }
    $af = @(Get-ChildItem $BasePath -Filter "app-*" -Directory -ErrorAction SilentlyContinue |
        Sort-Object { try { if ($_.Name -match "app-\s*([\d\.]+)") { [Version]$matches[1].Trim() } else { [Version]"0.0.0" } } catch { [Version]"0.0.0" } } -Descending)
    $diag = @{
        BasePath = $BasePath; AppFoldersFound = @(); ModulesFolderExists = $false; VoiceModuleExists = $false
        LatestAppFolder = $null; LatestAppVersion = $null; ModulesPath = $null; VoiceModulePath = $null; Error = $null
    }
    if ($af.Count -eq 0) { $diag.Error = "NoAppFolders"; if ($ReturnDiagnostics) { return $diag }; return $null }
    $diag.AppFoldersFound = @($af | ForEach-Object { $_.Name })
    $diag.LatestAppFolder = $af[0].FullName
    if ($af[0].Name -match "app-\s*([\d\.]+)") { $diag.LatestAppVersion = $matches[1].Trim() } else { $diag.LatestAppVersion = $af[0].Name }
    foreach ($f in $af) {
        $mp = Join-Path $f.FullName "modules"
        if (Test-Path $mp) {
            $diag.ModulesFolderExists = $true
            $diag.ModulesPath = $mp
            $vm = @(Get-ChildItem $mp -Filter "discord_voice*" -Directory -ErrorAction SilentlyContinue)
            if ($vm.Count -gt 0) {
                $diag.VoiceModuleExists = $true
                $diag.VoiceModulePath = $vm[0].FullName
                if ($ReturnDiagnostics) { return $diag }
                return $f.FullName
            }
        }
    }
    if (-not $diag.ModulesFolderExists) { $diag.Error = "NoModulesFolder" }
    elseif (-not $diag.VoiceModuleExists) { $diag.Error = "NoVoiceModule" }
    if ($ReturnDiagnostics) { return $diag }
    return $null
}

function Get-DiscordAppVersion {
    param([string]$AppPath)
    if ([string]::IsNullOrWhiteSpace($AppPath)) { return "Unknown" }
    if ($AppPath -match "app-\s*([\d\.]+)") { return $matches[1].Trim() }
    try {
        $exe = Get-ChildItem $AppPath -Filter "*.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($exe) { return (Get-Item $exe.FullName).VersionInfo.ProductVersion }
    } catch { }
    return "Unknown"
}

function Get-InstalledClients {
    $inst = [System.Collections.ArrayList]::new()
    $foundPaths = New-Object 'System.Collections.Generic.HashSet[string]'
    foreach ($k in $Script:DiscordClients.Keys) {
        $c = $Script:DiscordClients[$k]
        $isMod = $c.Name -match '\[Mod\]'
        if ($isMod -and $c.DetectPath -and -not (Test-Path $c.DetectPath)) { continue }
        $fp = $null
        if ($c.Path -and (Test-Path $c.Path)) { $fp = $c.Path }
        elseif ($c.FallbackPath -and (Test-Path $c.FallbackPath)) { $fp = $c.FallbackPath }
        else {
            foreach ($pn in $c.Processes) {
                if ($pn -eq "Update") { continue }
                $dp = Get-PathFromProcess $pn
                if ($dp -and (Test-Path $dp)) { $fp = $dp; break }
            }
        }
        if (-not $fp -and $c.Shortcut) {
            $sp = Get-PathFromShortcuts $c.Shortcut
            if ($sp -and (Test-Path $sp)) { $fp = $sp }
        }
        if ($fp) {
            try { $fp = (Get-Item $fp).FullName } catch { continue }
            if ($foundPaths.Contains($fp) -and -not $isMod) { continue }
            $ap = Find-DiscordAppPath $fp
            if ($ap) {
                [void]$inst.Add(@{Index=$k; Name=$c.Name; Path=$fp; AppPath=$ap; Client=$c})
                [void]$foundPaths.Add($fp)
            }
        }
    }
    return $inst
}

# endregion Multi-Client Detection

# region Process Management

function Stop-DiscordProcesses {
    param([string[]]$ProcessNames, [string]$InstallPath)
    if (-not $ProcessNames -or $ProcessNames.Count -eq 0) { return $true }
    $p = Get-Process -Name $ProcessNames -ErrorAction SilentlyContinue
    if (-not $p) { return $true }
    if ($PSBoundParameters.ContainsKey('InstallPath')) {
        if (-not $InstallPath -or -not (Test-Path $InstallPath)) { $p = @() } else {
            try {
                $installFull = (Get-Item $InstallPath).FullName.TrimEnd('\') + '\'
                $toKill = @()
                foreach ($proc in $p) {
                    $exePath = $null
                    try {
                        $cim = Get-CimInstance Win32_Process -Filter "ProcessId=$($proc.Id)" -ErrorAction SilentlyContinue
                        if ($cim -and $cim.ExecutablePath) { $exePath = $cim.ExecutablePath }
                    } catch { }
                    if (-not $exePath) { continue }
                    try { $exePath = (Get-Item $exePath).FullName.TrimEnd('\') } catch { continue }
                    if ($exePath.StartsWith($installFull, [StringComparison]::OrdinalIgnoreCase)) { $toKill += $proc }
                }
                $p = $toKill
            } catch { $p = @() }
        }
    }
    if ($p -and @($p).Count -gt 0) {
        $p | Stop-Process -Force -ErrorAction SilentlyContinue
        for ($i = 0; $i -lt 20; $i++) {
            $remaining = Get-Process -Name $ProcessNames -ErrorAction SilentlyContinue
            if (-not $remaining) { return $true }
            if ($PSBoundParameters.ContainsKey('InstallPath') -and $InstallPath -and (Test-Path $InstallPath)) {
                $installFull = (Get-Item $InstallPath).FullName.TrimEnd('\') + '\'
                $remaining = @($remaining | Where-Object {
                    $exePath = $null
                    try {
                        $cim = Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)" -ErrorAction SilentlyContinue
                        if ($cim -and $cim.ExecutablePath) { $exePath = (Get-Item $cim.ExecutablePath).FullName.TrimEnd('\') }
                    } catch { }
                    $exePath -and $exePath.StartsWith($installFull, [StringComparison]::OrdinalIgnoreCase)
                })
                if (@($remaining).Count -eq 0) { return $true }
            }
            Start-Sleep -Milliseconds 250
        }
        return $false
    }
    return $true
}

function Stop-AllDiscordProcesses {
    $allProcs = @("Discord","DiscordCanary","DiscordPTB","DiscordDevelopment","Lightcord","BetterVencord","Equicord","Vencord","Update")
    return Stop-DiscordProcesses $allProcs
}

# endregion Process Management

# region Backup Management

function Get-BackupList {
    if (-not (Test-Path $Script:Config.BackupDir)) { return @() }
    $backups = @(Get-ChildItem $Script:Config.BackupDir -Filter "discord_voice.node.*.backup" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending)
    if ($backups.Count -eq 0) { return @() }
    return @($backups | ForEach-Object { @{ Path = $_.FullName; Date = $_.LastWriteTime; Size = $_.Length; Name = $_.Name } })
}

function Invoke-BackupRetention {
    if (-not $Script:Config.BackupDir) { return }
    EnsureDir $Script:Config.BackupDir
    if (-not (Test-Path -LiteralPath $Script:Config.BackupDir)) { return }
    $maxAge = [int]$Script:Config.MaxBackupAgeDays
    if ($maxAge -lt 1) { $maxAge = 45 }
    $perClient = [int]$Script:Config.MaxBackupsPerClient
    if ($perClient -lt 1) { $perClient = 3 }
    $cutoff = (Get-Date).AddDays(-$maxAge)
    $re = New-Object System.Text.RegularExpressions.Regex(
        '^discord_voice\.node\.(.+)\.(\d{8}_\d{6})\.backup$',
        [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
    )
    $removed = 0

    $files = @(Get-ChildItem -LiteralPath $Script:Config.BackupDir -File -ErrorAction SilentlyContinue | Where-Object { $_.Name -like 'discord_voice.node.*.backup' })
    foreach ($f in $files) {
        if ($f.LastWriteTime -lt $cutoff) {
            Remove-Item -LiteralPath $f.FullName -Force -ErrorAction SilentlyContinue
            $removed++
        }
    }

    $files = @(Get-ChildItem -LiteralPath $Script:Config.BackupDir -File -ErrorAction SilentlyContinue | Where-Object { $_.Name -like 'discord_voice.node.*.backup' })
    $groups = @{}
    foreach ($f in $files) {
        $m = $re.Match($f.Name)
        $key = if ($m.Success) { $m.Groups[1].Value } else { '__other__' }
        if (-not $groups.ContainsKey($key)) {
            $groups[$key] = [System.Collections.ArrayList]::new()
        }
        [void]$groups[$key].Add($f)
    }
    foreach ($clientKey in $groups.Keys) {
        $list = @($groups[$clientKey] | Sort-Object LastWriteTime -Descending)
        if ($list.Count -le $perClient) { continue }
        foreach ($excess in ($list | Select-Object -Skip $perClient)) {
            Remove-Item -LiteralPath $excess.FullName -Force -ErrorAction SilentlyContinue
            $removed++
        }
    }

    if ($removed -gt 0) {
        Write-Log "Pruned old voice backups: removed $removed file(s) (max $perClient per client, max age ${maxAge}d)." -Level Info
    }
}

function Show-BackupList {
    Invoke-BackupRetention
    $backups = Get-BackupList
    if ($backups.Count -eq 0) { Write-Host "No backups found" -ForegroundColor Yellow; return }
    Write-Host "`n=== Available Backups ===" -ForegroundColor Cyan
    for ($i = 0; $i -lt $backups.Count; $i++) {
        Write-Host "  [$($i+1)] $($backups[$i].Date.ToString('yyyy-MM-dd HH:mm:ss')) - $([Math]::Round($backups[$i].Size / 1MB, 2)) MB - $($backups[$i].Name)"
    }
    Write-Host ""
}

function Get-VoiceModulePaths {
    param([Parameter(Mandatory)][string]$AppPath)

    $modulesPath = Join-Path $AppPath "modules"
    $voiceModules = @(
        Get-ChildItem $modulesPath -Filter "discord_voice*" -Directory -ErrorAction SilentlyContinue
    )
    if ($voiceModules.Count -eq 0) {
        return $null
    }

    $voiceModule = $voiceModules[0]
    $nestedVoiceFolder = Join-Path $voiceModule.FullName "discord_voice"
    $voiceFolderPath = if (Test-Path $nestedVoiceFolder) { $nestedVoiceFolder } else { $voiceModule.FullName }
    $voiceNodePath = Join-Path $voiceFolderPath "discord_voice.node"

    return @{
        ModulesPath = $modulesPath
        VoiceModule = $voiceModule
        VoiceFolderPath = $voiceFolderPath
        VoiceNodePath = $voiceNodePath
    }
}

function Restore-FromBackup {
    param([string]$BackupPath = $null)

    Write-Banner
    Write-Log "Starting restore..." -Level Info
    Invoke-BackupRetention

    if (-not $BackupPath) {
        $backups = Get-BackupList
        if ($backups.Count -eq 0) {
            Write-Log "No backups found" -Level Error
            return $false
        }

        Show-BackupList
        $sel = Read-Host "Select backup (1-$($backups.Count)) or Enter for most recent"
        if ([string]::IsNullOrWhiteSpace($sel)) {
            $BackupPath = $backups[0].Path
        } else {
            $idx = 0
            if (-not [int]::TryParse($sel, [ref]$idx) -or $idx -lt 1 -or $idx -gt $backups.Count) {
                Write-Log "Invalid selection" -Level Error
                return $false
            }
            $BackupPath = $backups[$idx - 1].Path
        }
    }

    $installedClients = Get-InstalledClients
    if ($installedClients.Count -eq 0) {
        Write-Log "No Discord clients found to restore to" -Level Error
        return $false
    }

    Write-Log "Found $($installedClients.Count) client(s) to restore:" -Level Info
    for ($i = 0; $i -lt $installedClients.Count; $i++) {
        Write-Log "  [$($i+1)] $($installedClients[$i].Name.Trim())" -Level Info
    }

    $sel = Read-Host "Select client to restore (1-$($installedClients.Count)) or Enter for first"
    $targetIdx = 0
    if (-not [string]::IsNullOrWhiteSpace($sel)) {
        if (-not [int]::TryParse($sel, [ref]$targetIdx) -or $targetIdx -lt 1 -or $targetIdx -gt $installedClients.Count) {
            Write-Log "Invalid selection" -Level Error
            return $false
        }
        $targetIdx--
    }

    $targetClient = $installedClients[$targetIdx]
    if (-not $targetClient -or -not $targetClient.AppPath) {
        Write-Log "Invalid target client" -Level Error
        return $false
    }

    $voiceInfo = Get-VoiceModulePaths -AppPath $targetClient.AppPath
    if (-not $voiceInfo) {
        Write-Log "No voice module found in target client" -Level Error
        return $false
    }

    $targetPath = $voiceInfo.VoiceNodePath
    Write-Log "Target: $targetPath" -Level Info

    if ((Read-Host "Replace current file with backup? (y/N)") -notin @('y', 'Y')) {
        return $false
    }

    try {
        Write-Log "Closing Discord processes..." -Level Info
        Stop-AllDiscordProcesses | Out-Null
        Start-Sleep -Seconds 2
        EnsureDir (Split-Path $targetPath -Parent)
        Copy-Item -Path $BackupPath -Destination $targetPath -Force
        Write-Log "Restore complete! Restart Discord." -Level Success
        return $true
    } catch {
        Write-Log "Restore failed: $_" -Level Error
        return $false
    }
}

function Backup-VoiceNode {
    param([string]$SourcePath, [string]$ClientName = "Discord")
    if ($Script:Config.SkipBackup) { Write-Log "Skipping backup" -Level Warning; return $true }
    if (-not $SourcePath -or -not (Test-Path $SourcePath)) { Write-Log "Backup source not found: $SourcePath" -Level Error; return $false }
    try {
        EnsureDir $Script:Config.BackupDir
        $sanitizedName = $ClientName -replace '\s+','_' -replace '\[|\]','' -replace '-','_'
        $backupPath = Join-Path $Script:Config.BackupDir "discord_voice.node.$sanitizedName.$(Get-Date -Format 'yyyyMMdd_HHmmss').backup"
        Copy-Item -Path $SourcePath -Destination $backupPath -Force
        Write-Log "Backup created: $([System.IO.Path]::GetFileName($backupPath))" -Level Success
        Invoke-BackupRetention
        return $true
    } catch { Write-Log "Backup failed: $_" -Level Error; return $false }
}

# endregion Backup Management

# region GUI

function Show-ConfigurationGUI {
    Add-Type -AssemblyName System.Windows.Forms, System.Drawing
    $prevCfg = Get-UserConfig
    $installedClients = Get-InstalledClients
    $initGain = if ($prevCfg -and -not $Script:GainExplicitlySet) { [Math]::Max(1, [Math]::Min(10, $prevCfg.LastGainMultiplier)) } else { $Script:Config.AudioGainMultiplier }

    $Script:GuiInstalledIndices = @{}
    foreach ($ic in $installedClients) { $Script:GuiInstalledIndices[$ic.Index] = $ic }
    $Script:GuiInstalledClients = $installedClients

    $normalHeight = 570
    $debugPanelHeight = 550
    $debugExpandedHeight = $normalHeight + $debugPanelHeight
    $formWidth = 520

    $form = New-Object Windows.Forms.Form -Property @{
        Text = "Discord Voice Patcher v$Script:SCRIPT_VERSION"; StartPosition = "CenterScreen"
        FormBorderStyle = "FixedDialog"; MaximizeBox = $false; MinimizeBox = $false
        BackColor = [Drawing.Color]::FromArgb(44,47,51); ForeColor = [Drawing.Color]::White
    }
    $form.ClientSize = New-Object Drawing.Size($formWidth, $normalHeight)

    $newLabel = { param($x, $y, $w, $h, $text, $font, $color)
        $l = New-Object Windows.Forms.Label -Property @{ Location = "$x,$y"; Size = "$w,$h"; Text = $text }
        if ($font) { $l.Font = $font }
        if ($color) { $l.ForeColor = $color }
        $form.Controls.Add($l); $l
    }

    & $newLabel 20 20 400 30 "Discord Voice Quality Patcher" (New-Object Drawing.Font("Segoe UI", 16, [Drawing.FontStyle]::Bold)) ([Drawing.Color]::FromArgb(88,101,242))
    & $newLabel 420 28 80 20 "v$Script:SCRIPT_VERSION" (New-Object Drawing.Font("Segoe UI", 9)) ([Drawing.Color]::FromArgb(150,152,157))
    & $newLabel 20 55 480 20 "48kHz | 384kbps | Stereo | Multi-Client Support" (New-Object Drawing.Font("Segoe UI", 9)) ([Drawing.Color]::FromArgb(185,187,190))
    & $newLabel 20 85 480 25 "Discord Client" (New-Object Drawing.Font("Segoe UI", 11, [Drawing.FontStyle]::Bold)) $null

    $clientCombo = New-Object Windows.Forms.ComboBox -Property @{
        Location = "20,112"; Size = "480,28"; DropDownStyle = "DropDownList"
        BackColor = [Drawing.Color]::FromArgb(47,49,54); ForeColor = [Drawing.Color]::White
        Font = New-Object Drawing.Font("Consolas", 9)
    }
    $firstInstalledIndex = -1
    foreach ($k in $Script:DiscordClients.Keys) {
        $c = $Script:DiscordClients[$k]
        $isInstalled = $Script:GuiInstalledIndices.ContainsKey($k)
        $prefix = if ($isInstalled) { "[*] " } else { "[ ] " }
        [void]$clientCombo.Items.Add("$prefix$($c.Name)")
        if ($isInstalled -and $firstInstalledIndex -eq -1) { $firstInstalledIndex = $k }
    }
    if ($firstInstalledIndex -ge 0) { $clientCombo.SelectedIndex = $firstInstalledIndex } else { $clientCombo.SelectedIndex = 0 }
    $form.Controls.Add($clientCombo)

    $detectedLabel = & $newLabel 20 145 480 20 "" (New-Object Drawing.Font("Segoe UI", 9)) ([Drawing.Color]::FromArgb(87,242,135))
    if ($installedClients.Count -gt 0) { $detectedLabel.Text = "Detected: $($installedClients.Count) client(s) installed  |  [*] = Installed" }
    else { $detectedLabel.Text = "No Discord clients detected - please install Discord first"; $detectedLabel.ForeColor = [Drawing.Color]::FromArgb(237,66,69) }

    & $newLabel 20 175 480 25 "Audio Gain Multiplier" (New-Object Drawing.Font("Segoe UI", 12, [Drawing.FontStyle]::Bold)) $null
    $valueLabel = & $newLabel 20 205 480 30 "" (New-Object Drawing.Font("Segoe UI", 14, [Drawing.FontStyle]::Bold)) $null
    $valueLabel.TextAlign = [Drawing.ContentAlignment]::MiddleCenter

    $updateLabel = { param([int]$m)
        $valueLabel.Text = if ($m -eq 1) { "1x (No Boost - Original Volume)" } else { "${m}x Volume Boost" }
        $valueLabel.ForeColor = if ($m -le 2) { [Drawing.Color]::FromArgb(87,242,135) } elseif ($m -le 5) { [Drawing.Color]::FromArgb(254,231,92) } else { [Drawing.Color]::FromArgb(237,66,69) }
    }

    $slider = New-Object Windows.Forms.TrackBar
    $slider.Location = New-Object Drawing.Point(30, 245)
    $slider.Size = New-Object Drawing.Size(460, 45)
    $slider.Minimum = 1; $slider.Maximum = 10; $slider.TickFrequency = 1; $slider.LargeChange = 1; $slider.SmallChange = 1
    $slider.TickStyle = [Windows.Forms.TickStyle]::BottomRight
    $slider.BackColor = [Drawing.Color]::FromArgb(44,47,51)
    $slider.Add_ValueChanged({ & $updateLabel $slider.Value })
    $slider.Value = $initGain
    $form.Controls.Add($slider)
    & $updateLabel $initGain

    & $newLabel 30 290 460 20 "1x      2x      3x      4x      5x      6x      7x      8x      9x     10x" (New-Object Drawing.Font("Consolas", 8)) ([Drawing.Color]::FromArgb(150,152,157))
    & $newLabel 20 315 480 30 "1x = Original volume (no boost). Recommended: 2-3x. Values >5x may distort." (New-Object Drawing.Font("Segoe UI", 9)) ([Drawing.Color]::FromArgb(185,187,190))

    $chk = New-Object Windows.Forms.CheckBox -Property @{
        Location = "20,350"; Size = "480,25"; Text = "Create backup before patching (Recommended)"
        Checked = $(if ($prevCfg -and $null -ne $prevCfg.LastBackupEnabled) { $prevCfg.LastBackupEnabled } else { -not $Script:Config.SkipBackup })
        ForeColor = [Drawing.Color]::White; Font = New-Object Drawing.Font("Segoe UI", 9)
    }
    $form.Controls.Add($chk)

    $autoRelaunchChk = New-Object Windows.Forms.CheckBox -Property @{
        Location = "20,375"; Size = "480,25"; Text = "Auto-relaunch Discord after patching"
        Checked = $(if ($prevCfg -and $null -ne $prevCfg.AutoRelaunch) { $prevCfg.AutoRelaunch } else { $true })
        ForeColor = [Drawing.Color]::White; Font = New-Object Drawing.Font("Segoe UI", 9)
    }
    $form.Controls.Add($autoRelaunchChk)

    if ($prevCfg -and $prevCfg.LastPatchDate) {
        & $newLabel 20 405 480 20 "Last: $($prevCfg.LastPatchDate) @ $($prevCfg.LastGainMultiplier)x" (New-Object Drawing.Font("Segoe UI", 8)) ([Drawing.Color]::FromArgb(150,152,157))
    }

    $statusLabel = & $newLabel 20 430 480 25 "" (New-Object Drawing.Font("Segoe UI", 9)) ([Drawing.Color]::FromArgb(237,66,69))
    if (-not $Script:GuiInstalledIndices.ContainsKey($clientCombo.SelectedIndex)) { $statusLabel.Text = "This client is not installed" }

    $patchCheckboxes = @{}
    $groupCheckboxes = @{}
    $totalPatches = $Script:AllPatchKeys.Count
    $Script:SuppressGroupToggle = $false
    $Script:DebugPatchCheckboxes = $patchCheckboxes
    $Script:DebugGroupCheckboxes = $groupCheckboxes
    $Script:DebugTotalPatches = $totalPatches

    $debugBadge = New-Object Windows.Forms.Label -Property @{
        Location = "20,515"; Size = "90,24"; Text = "DEBUG MODE"
        Font = New-Object Drawing.Font("Segoe UI", 8, [Drawing.FontStyle]::Bold)
        ForeColor = [Drawing.Color]::FromArgb(44,47,51)
        BackColor = [Drawing.Color]::FromArgb(254,231,92)
        TextAlign = [Drawing.ContentAlignment]::MiddleCenter
        Visible = $false
    }
    $form.Controls.Add($debugBadge)

    $debugPanel = New-Object Windows.Forms.Panel -Property @{
        Location = New-Object Drawing.Point(0, 545)
        Size = New-Object Drawing.Size($formWidth, $debugPanelHeight)
        AutoScroll = $true; Visible = $false
        BackColor = [Drawing.Color]::FromArgb(47,49,54)
    }
    $form.Controls.Add($debugPanel)

    $counterLabel = New-Object Windows.Forms.Label -Property @{
        Location = "340,8"; Size = "160,20"; TextAlign = [Drawing.ContentAlignment]::MiddleRight
        Font = New-Object Drawing.Font("Segoe UI", 9); ForeColor = [Drawing.Color]::FromArgb(185,187,190)
    }
    $debugPanel.Controls.Add($counterLabel)
    $Script:DebugCounterLabel = $counterLabel

    $updateCounter = {
        $pb = $Script:DebugPatchCheckboxes
        $lbl = $Script:DebugCounterLabel
        $tot = $Script:DebugTotalPatches
        if ($null -eq $pb -or $null -eq $lbl) { return }
        $enabled = @($pb.Values | Where-Object { $_.Checked }).Count
        $lbl.Text = "$enabled / $tot patches enabled"
    }

    $selectAllBtn = New-Object Windows.Forms.Button -Property @{
        Location = "20,5"; Size = "85,25"; Text = "Select All"; FlatStyle = "Flat"
        BackColor = [Drawing.Color]::FromArgb(54,57,63); ForeColor = [Drawing.Color]::White
        Font = New-Object Drawing.Font("Segoe UI", 8); Cursor = [Windows.Forms.Cursors]::Hand
    }
    $selectAllBtn.FlatAppearance.BorderColor = [Drawing.Color]::FromArgb(64,68,75)
    $selectAllBtn.Add_Click({
        $Script:SuppressGroupToggle = $true
        $pb = $Script:DebugPatchCheckboxes; $gb = $Script:DebugGroupCheckboxes
        if ($pb) { foreach ($cb in $pb.Values) { $cb.Checked = $true } }
        if ($gb) { foreach ($gcb in $gb.Values) { $gcb.Checked = $true } }
        $Script:SuppressGroupToggle = $false
        & $updateCounter
    })
    $debugPanel.Controls.Add($selectAllBtn)

    $deselectAllBtn = New-Object Windows.Forms.Button -Property @{
        Location = "112,5"; Size = "95,25"; Text = "Deselect All"; FlatStyle = "Flat"
        BackColor = [Drawing.Color]::FromArgb(54,57,63); ForeColor = [Drawing.Color]::White
        Font = New-Object Drawing.Font("Segoe UI", 8); Cursor = [Windows.Forms.Cursors]::Hand
    }
    $deselectAllBtn.FlatAppearance.BorderColor = [Drawing.Color]::FromArgb(64,68,75)
    $deselectAllBtn.Add_Click({
        $Script:SuppressGroupToggle = $true
        $pb = $Script:DebugPatchCheckboxes; $gb = $Script:DebugGroupCheckboxes
        if ($pb) { foreach ($cb in $pb.Values) { $cb.Checked = $false } }
        if ($gb) { foreach ($gcb in $gb.Values) { $gcb.Checked = $false } }
        $Script:SuppressGroupToggle = $false
        & $updateCounter
    })
    $debugPanel.Controls.Add($deselectAllBtn)

    $copyOffsetsBtn = New-Object Windows.Forms.Button -Property @{
        Location = "212,5"; Size = "95,25"; Text = "Copy Offsets"; FlatStyle = "Flat"
        BackColor = [Drawing.Color]::FromArgb(54,57,63); ForeColor = [Drawing.Color]::White
        Font = New-Object Drawing.Font("Segoe UI", 8); Cursor = [Windows.Forms.Cursors]::Hand
    }
    $copyOffsetsBtn.FlatAppearance.BorderColor = [Drawing.Color]::FromArgb(64,68,75)
    $copyOffsetsBtn.Add_Click({
        try {
            $block = Get-OffsetsCopyBlock
            [System.Windows.Forms.Clipboard]::SetText($block)
            $Script:StatusLabelCopyOffsets.Text = "Offsets copied"
        } catch {
            $Script:StatusLabelCopyOffsets.Text = "Copy failed"
        }
    })
    $debugPanel.Controls.Add($copyOffsetsBtn)
    $copyOffsetsStatus = New-Object Windows.Forms.Label -Property @{
        Location = "312,8"; Size = "90,20"; Text = ""
        Font = New-Object Drawing.Font("Segoe UI", 8); ForeColor = [Drawing.Color]::FromArgb(87,242,135)
    }
    $debugPanel.Controls.Add($copyOffsetsStatus)
    $Script:StatusLabelCopyOffsets = $copyOffsetsStatus

    $patchLocalBtn = New-Object Windows.Forms.Button -Property @{
        Location = "20,35"; Size = "180,28"; Text = "Patch local (no download)"; FlatStyle = "Flat"
        BackColor = [Drawing.Color]::FromArgb(87,242,135); ForeColor = [Drawing.Color]::FromArgb(30,30,30)
        Font = New-Object Drawing.Font("Segoe UI", 9); Cursor = [Windows.Forms.Cursors]::Hand
    }
    $patchLocalBtn.FlatAppearance.BorderColor = [Drawing.Color]::FromArgb(64,68,75)
    $patchLocalBtn.Add_Click({
        $selectedIdx = $clientCombo.SelectedIndex
        if (-not $Script:GuiInstalledIndices.ContainsKey($selectedIdx)) {
            [System.Windows.Forms.MessageBox]::Show("Select an installed client first.", "Debug", "OK", "Warning")
            return
        }
        $patchSel = @{}
        $pb = $Script:DebugPatchCheckboxes
        if ($pb) { foreach ($pk in $pb.Keys) { $patchSel[$pk] = $pb[$pk].Checked } }
        $form.Tag = @{
            Action = 'Patch'; Multiplier = $slider.Value
            SkipBackup = -not $chk.Checked; AutoRelaunch = $autoRelaunchChk.Checked
            ClientIndex = $selectedIdx; DebugMode = $true
            SelectedPatches = $patchSel; PatchLocalOnly = $true
        }
        $form.DialogResult = "OK"; $form.Close()
    })
    $debugPanel.Controls.Add($patchLocalBtn)

    $yPos = 70
    $groupColors = @{
        STEREO     = [Drawing.Color]::FromArgb(254,231,92)
        BITRATE    = [Drawing.Color]::FromArgb(254,231,92)
        SAMPLERATE = [Drawing.Color]::FromArgb(87,242,135)
        FILTER     = [Drawing.Color]::FromArgb(254,231,92)
        ENCODER    = [Drawing.Color]::FromArgb(254,231,92)
        PACKETLOSS = [Drawing.Color]::FromArgb(87,242,135)
        DISCORD_API_LOCK = [Drawing.Color]::FromArgb(240,71,71)
    }

    foreach ($groupName in $Script:PatchGroups.Keys) {
        $patches = $Script:PatchGroups[$groupName]
        $groupColor = $groupColors[$groupName]
        if (-not $groupColor) { $groupColor = [Drawing.Color]::FromArgb(254,231,92) }

        $grpChecked = ($patches.Keys | ForEach-Object { $Script:SelectedPatches[$_] } | Where-Object { $_ }).Count -eq $patches.Count
        $grpChk = New-Object Windows.Forms.CheckBox -Property @{
            Location = New-Object Drawing.Point(20, $yPos)
            Size = New-Object Drawing.Size(460, 22)
            Text = $groupName; Checked = $grpChecked
            ForeColor = $groupColor
            Font = New-Object Drawing.Font("Segoe UI", 10, [Drawing.FontStyle]::Bold)
        }
        $grpChk.Add_CheckedChanged({
            param($snd, $e)
            if ($Script:SuppressGroupToggle) { return }
            $Script:SuppressGroupToggle = $true
            $gn = $snd.Text
            $pb = $Script:DebugPatchCheckboxes
            $grp = $Script:PatchGroups[$gn]
            if ($pb -and $grp) {
                foreach ($pk in $grp.Keys) {
                    if ($pb.ContainsKey($pk)) { $pb[$pk].Checked = $snd.Checked }
                }
            }
            $Script:SuppressGroupToggle = $false
            & $updateCounter
        })
        $groupCheckboxes[$groupName] = $grpChk
        $debugPanel.Controls.Add($grpChk)
        $yPos += 24

        foreach ($patchKey in $patches.Keys) {
            $patchInfo = $patches[$patchKey]
            $offset = $Script:Config.Offsets[$patchKey]
            $offsetHex = if ($offset) { "0x{0:X}" -f $offset } else { "???" }

            $pChk = New-Object Windows.Forms.CheckBox -Property @{
                Location = New-Object Drawing.Point(45, $yPos)
                Size = New-Object Drawing.Size(440, 20)
                Text = $patchKey; Checked = ($Script:SelectedPatches[$patchKey] -eq $true)
                ForeColor = [Drawing.Color]::White
                Font = New-Object Drawing.Font("Segoe UI", 9)
            }
            $pChk.Add_CheckedChanged({
                param($snd, $e)
                if ($Script:SuppressGroupToggle) { return }
                $Script:SuppressGroupToggle = $true
                & $updateCounter
                $pb = $Script:DebugPatchCheckboxes
                $gb = $Script:DebugGroupCheckboxes
                if ($pb -and $gb) {
                    foreach ($gn in $Script:PatchGroups.Keys) {
                        $allChecked = $true
                        $grp = $Script:PatchGroups[$gn]
                        if ($grp) {
                            foreach ($pk in $grp.Keys) {
                                if ($pb.ContainsKey($pk) -and -not $pb[$pk].Checked) { $allChecked = $false; break }
                            }
                        }
                        if ($gb.ContainsKey($gn)) { $gb[$gn].Checked = $allChecked }
                    }
                }
                $Script:SuppressGroupToggle = $false
            })
            $patchCheckboxes[$patchKey] = $pChk
            $debugPanel.Controls.Add($pChk)

            $infoLabel = New-Object Windows.Forms.Label -Property @{
                Location = New-Object Drawing.Point(65, ($yPos + 20))
                Size = New-Object Drawing.Size(420, 16)
                Text = "$offsetHex  ->  $($patchInfo.Hex)"
                Font = New-Object Drawing.Font("Consolas", 7.5)
                ForeColor = [Drawing.Color]::FromArgb(120,124,128)
            }
            $debugPanel.Controls.Add($infoLabel)
            $yPos += 40
        }
        $yPos += 8
    }

    & $updateCounter

    $btnStyle = { param($x, $text, $bgR, $bgG, $bgB, $bold, $action)
        $b = New-Object Windows.Forms.Button -Property @{
            Location = "$x,470"; Size = "90,40"; Text = $text; FlatStyle = "Flat"
            BackColor = [Drawing.Color]::FromArgb($bgR, $bgG, $bgB); ForeColor = [Drawing.Color]::White
            Font = New-Object Drawing.Font("Segoe UI", 10, $(if ($bold) { [Drawing.FontStyle]::Bold } else { [Drawing.FontStyle]::Regular }))
            Cursor = [Windows.Forms.Cursors]::Hand
        }
        $b.Add_Click($action); $form.Controls.Add($b); $b
    }

    & $btnStyle 20 "Restore" 79 84 92 $false { $form.Tag = @{ Action = 'Restore' }; $form.DialogResult = "Abort"; $form.Close() }

    & $btnStyle 115 "Patch" 88 101 242 $true {
        $selectedIdx = $clientCombo.SelectedIndex
        if (-not $Script:GuiInstalledIndices.ContainsKey($selectedIdx)) { $statusLabel.Text = "Selected client is not installed!"; return }
        $patchSel = @{}
        $isDbg = $debugPanel.Visible
        $pb = if ($isDbg) { $Script:DebugPatchCheckboxes } else { $patchCheckboxes }
        if ($pb) {
            foreach ($pk in $pb.Keys) {
                $patchSel[$pk] = if ($isDbg) { $pb[$pk].Checked } else { $true }
            }
        }
        $form.Tag = @{
            Action = 'Patch'; Multiplier = $slider.Value
            SkipBackup = -not $chk.Checked; AutoRelaunch = $autoRelaunchChk.Checked
            ClientIndex = $selectedIdx; DebugMode = $isDbg; SelectedPatches = $patchSel
        }
        $form.DialogResult = "OK"; $form.Close()
    }

    & $btnStyle 210 "Patch All" 87 158 87 $true {
        if ($Script:GuiInstalledClients.Count -eq 0) { $statusLabel.Text = "No Discord clients detected to patch!"; return }
        $patchSel = @{}
        $isDbg = $debugPanel.Visible
        $pb = if ($isDbg) { $Script:DebugPatchCheckboxes } else { $patchCheckboxes }
        if ($pb) {
            foreach ($pk in $pb.Keys) {
                $patchSel[$pk] = if ($isDbg) { $pb[$pk].Checked } else { $true }
            }
        }
        $form.Tag = @{
            Action = 'PatchAll'; Multiplier = $slider.Value
            SkipBackup = -not $chk.Checked; AutoRelaunch = $autoRelaunchChk.Checked
            DebugMode = $isDbg; SelectedPatches = $patchSel
        }
        $form.DialogResult = "OK"; $form.Close()
    }

    $debugBtn = New-Object Windows.Forms.Button -Property @{
        Location = "305,470"; Size = "90,40"; Text = "Debug"; FlatStyle = "Flat"
        BackColor = [Drawing.Color]::FromArgb(79,84,92); ForeColor = [Drawing.Color]::White
        Font = New-Object Drawing.Font("Segoe UI", 10)
        Cursor = [Windows.Forms.Cursors]::Hand
    }
    $debugBtn.Add_Click({
        if ($debugPanel.Visible) {
            $debugPanel.Visible = $false
            $debugBadge.Visible = $false
            $form.ClientSize = New-Object Drawing.Size($formWidth, $normalHeight)
        } else {
            $debugPanel.Visible = $true
            $debugBadge.Visible = $true
            $form.ClientSize = New-Object Drawing.Size($formWidth, $debugExpandedHeight)
        }
    }.GetNewClosure())
    $form.Controls.Add($debugBtn)

    $cancelBtn = & $btnStyle 400 "Cancel" 79 84 92 $false { $form.DialogResult = "Cancel"; $form.Close() }

    $clientCombo.Add_SelectedIndexChanged({
        $selectedIdx = $clientCombo.SelectedIndex
        if ($Script:GuiInstalledIndices.ContainsKey($selectedIdx)) { $statusLabel.Text = ""; $statusLabel.ForeColor = [Drawing.Color]::FromArgb(87,242,135) }
        else { $statusLabel.Text = "This client is not installed"; $statusLabel.ForeColor = [Drawing.Color]::FromArgb(237,66,69) }
    })

    $form.CancelButton = $cancelBtn
    try { $null = $form.ShowDialog(); return $form.Tag } finally { $form.Dispose() }
}

# endregion GUI

# region Environment & Compiler

function Initialize-Environment {
    @($Script:Config.TempDir, $Script:Config.BackupDir) | ForEach-Object {
        if ($_ -and -not (Test-Path $_)) { New-Item -ItemType Directory -Path $_ -Force | Out-Null }
    }
    Remove-PatcherTempFiles
    "=== Discord Voice Patcher Log ===`nStarted: $(Get-Date)`nGain: $($Script:Config.AudioGainMultiplier)x`n" | Out-File $Script:Config.LogFile -Force -ErrorAction SilentlyContinue
    Invoke-BackupRetention
}

function Show-CompilerMissingDialog {
    param(
        [ValidateSet('MissingCompiler', 'VisualStudioMissingCpp', 'MsvcBuildFailure', 'GppBuildFailure', 'ClangBuildFailure')]
        [string]$Reason = 'MissingCompiler'
    )

    $title = "Something is missing - easy fix"
    $nl = [Environment]::NewLine
    $body = "This patcher needs a free tool from Microsoft to run. You do not have it (or it is not set up right)." + $nl + $nl +
        "VS Code and Cursor are just editors. They do not include this tool. You need the installer from the button below." + $nl + $nl

    switch ($Reason) {
        'VisualStudioMissingCpp' {
            $body += "You have Visual Studio but the C++ part is not installed. In the installer, click Modify, then tick Desktop development with C++ and install."
        }
        'MsvcBuildFailure' {
            $body += "The build failed. Usually that means the C++ part of Visual Studio is missing or broken. Run the installer and add Desktop development with C++."
        }
        'GppBuildFailure' {
            $body += "Another compiler (MinGW) was used but it failed. Easiest fix: install the Microsoft tool below."
        }
        'ClangBuildFailure' {
            $body += "Another compiler (Clang) was used but it failed. Easiest fix: install the Microsoft tool below."
        }
        default {
            $body += "No compatible build tool was found. Click the button below, download and run the installer, then when it asks what to install, choose Desktop development with C++. After it finishes, run this patcher again."
        }
    }

    $body += $nl + $nl + "Then run this patcher again."

    try {
        Add-Type -AssemblyName System.Windows.Forms, System.Drawing -ErrorAction Stop

        $form = New-Object System.Windows.Forms.Form
        $form.Text = $title
        $form.Size = New-Object System.Drawing.Size(500, 300)
        $form.StartPosition = "CenterScreen"
        $form.FormBorderStyle = "FixedDialog"
        $form.MaximizeBox = $false
        $form.MinimizeBox = $false

        $lbl = New-Object System.Windows.Forms.Label
        $lbl.Location = New-Object System.Drawing.Point(14, 14)
        $lbl.Size = New-Object System.Drawing.Size(460, 200)
        $lbl.AutoSize = $false
        $lbl.Text = $body
        $lbl.Font = New-Object System.Drawing.Font("Segoe UI", 9.5)
        $form.Controls.Add($lbl)

        $btnOpen = New-Object System.Windows.Forms.Button
        $btnOpen.Text = "Download the tool (free)"
        $btnOpen.Location = New-Object System.Drawing.Point(14, 222)
        $btnOpen.Size = New-Object System.Drawing.Size(240, 32)
        $btnOpen.Font = New-Object System.Drawing.Font("Segoe UI", 9.5)
        $btnOpen.Add_Click({ Start-Process "https://visualstudio.microsoft.com/visual-cpp-build-tools/" })
        $form.Controls.Add($btnOpen)

        $btnOk = New-Object System.Windows.Forms.Button
        $btnOk.Text = "OK"
        $btnOk.Location = New-Object System.Drawing.Point(268, 222)
        $btnOk.Size = New-Object System.Drawing.Size(100, 32)
        $btnOk.Add_Click({ $form.Close() })
        $form.Controls.Add($btnOk)

        $form.Topmost = $true
        [void]$form.ShowDialog()
        $form.Dispose()
    }
    catch {
        try {
            [System.Windows.Forms.MessageBox]::Show($body, $title, [System.Windows.Forms.MessageBoxButtons]::OK) | Out-Null
        }
        catch { }
    }
}

function Write-CompilerSetupHelp {
    param(
        [ValidateSet('MissingCompiler', 'VisualStudioMissingCpp', 'MsvcBuildFailure', 'GppBuildFailure', 'ClangBuildFailure')]
        [string]$Reason = 'MissingCompiler'
    )

    Write-Host ""
    Write-Host "=== C++ Build Tools Required ===" -ForegroundColor Yellow
    Write-Log "This patcher compiles native C++ code at runtime." -Level Warning

    if (Get-Command "code" -ErrorAction SilentlyContinue) {
        Write-Log "VS Code is an editor only. It does NOT include a C++ compiler." -Level Warning
    }

    switch ($Reason) {
        'VisualStudioMissingCpp' {
            Write-Log "Visual Studio was found, but required C++ components are missing." -Level Error
            Write-Log "Open Visual Studio Installer, Modify, Workloads, then Desktop development with C++." -Level Warning
            Write-Log "Install MSVC v143 x64/x86 build tools and Windows 10/11 SDK." -Level Warning
        }
        'MsvcBuildFailure' {
            Write-Log "MSVC build failed. Usually missing Visual Studio C++ components." -Level Error
            Write-Log "Open Visual Studio Installer, Modify, add Desktop development with C++." -Level Warning
            Write-Log "Install MSVC v143 x64/x86 build tools and Windows 10/11 SDK." -Level Warning
        }
        'GppBuildFailure' {
            Write-Log "MinGW g++ build failed. Verify g++ is installed and in PATH." -Level Error
        }
        'ClangBuildFailure' {
            Write-Log "Clang build failed. Verify clang++ is installed and in PATH." -Level Error
        }
        default {
            Write-Log "No C++ compiler was found." -Level Error
            Write-Log "Install one of: Visual Studio (Desktop development with C++), MinGW-w64, or LLVM/Clang." -Level Warning
            Write-Log "Visual Studio Code alone is not enough." -Level Warning
        }
    }

    Write-Log "After installing tools, rerun the patcher." -Level Info
    Write-Host ""

    try {
        Show-CompilerMissingDialog -Reason $Reason
    }
    catch { }
}

function Find-Compiler {
    Write-Log "Searching for C++ compiler..." -Level Info

    $vsWhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
    $vsDetectedPath = $null
    $vsWithCppPath = $null
    $vcvarsMissing = $false

    if (Test-Path $vsWhere) {
        try {
            $vsWithCppPath = & $vsWhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath 2>$null
            if ($vsWithCppPath) {
                $vcvars = Join-Path $vsWithCppPath "VC\Auxiliary\Build\vcvars64.bat"
                if (Test-Path $vcvars) {
                    Write-Log "Found Visual Studio C++ Build Tools" -Level Success
                    return @{ Type = 'MSVC'; Path = $vcvars }
                }
                $vcvarsMissing = $true
                Write-Log "Visual Studio C++ workload detected but vcvars64.bat was not found: $vcvars" -Level Warning
            }
            $vsDetectedPath = & $vsWhere -latest -products * -property installationPath 2>$null
        }
        catch {
            Write-Log "Could not query Visual Studio installer: $($_.Exception.Message)" -Level Warning
        }
    }

    $gpp = Get-Command "g++" -ErrorAction SilentlyContinue
    if ($gpp) {
        Write-Log "Found MinGW g++" -Level Success
        return @{ Type = 'MinGW'; Path = $gpp.Source }
    }

    $clang = Get-Command "clang++" -ErrorAction SilentlyContinue
    if ($clang) {
        Write-Log "Found Clang" -Level Success
        return @{ Type = 'Clang'; Path = $clang.Source }
    }

    if ($vsDetectedPath -and (-not $vsWithCppPath -or $vcvarsMissing)) {
        Write-Log "Visual Studio detected at: $vsDetectedPath" -Level Warning
        Write-CompilerSetupHelp -Reason VisualStudioMissingCpp
        return $null
    }

    Write-CompilerSetupHelp -Reason MissingCompiler
    return $null
}

function Remove-PatcherTempFiles {
    $tempDir = $Script:Config.TempDir
    if (-not $tempDir -or -not (Test-Path $tempDir)) { return }
    @("patcher.cpp", "amplifier.cpp", "DiscordVoicePatcher.exe", "build.bat", "build.log", "patcher.obj", "amplifier.obj", "patcher_stdout.txt", "patcher_stderr.txt") | ForEach-Object {
        $file = Join-Path $tempDir $_
        if (Test-Path $file) { Remove-Item $file -Force -ErrorAction SilentlyContinue }
    }
    Get-ChildItem $tempDir -Filter "DiscordVoicePatcher_*.exe" -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
}

# endregion Environment & Compiler

# region Source Code Generation

function Get-AmplifierSourceCode {
    $gain = [int]$Script:Config.AudioGainMultiplier
    if ($gain -gt 3) {
        return @"
#include <cstring>

typedef signed char        int8_t;
typedef short              int16_t;
typedef int                int32_t;
typedef long long          int64_t;
typedef unsigned char      uint8_t;
typedef unsigned short     uint16_t;
typedef unsigned int       uint32_t;
typedef unsigned long long uint64_t;

static void zero_out_floats(float* p, int len, int channels) {
    if (len < 0 || channels < 0) return;
    if (!p) return;
    const size_t n = (size_t)len * (size_t)channels;
    if (n) std::memset(p, 0, n * sizeof(float));
}

extern "C" void __cdecl hp_cutoff(const float* in, int cutoff_Hz, float* out, int* hp_mem, int len, int channels, int Fs, int arch)
{
    (void)in; (void)cutoff_Hz; (void)hp_mem; (void)Fs; (void)arch;
    zero_out_floats(out, len, channels);
}

extern "C" void __cdecl dc_reject(const float* in, float* out, int* hp_mem, int len, int channels, int Fs)
{
    (void)in; (void)hp_mem; (void)Fs;
    zero_out_floats(out, len, channels);
}
"@
    }
    if ($gain -ge 3) {
        Write-Log "Generating amplifier: 3x+ ONLY -> Multiplier = $($gain - 2) (GUI $gain x)" -Level Info
        $multiplier = $gain - 2
        return @"
#define Multiplier $multiplier

typedef signed char        int8_t;
typedef short              int16_t;
typedef int                int32_t;
typedef long long          int64_t;
typedef unsigned char      uint8_t;
typedef unsigned short     uint16_t;
typedef unsigned int       uint32_t;
typedef unsigned long long uint64_t;

extern "C" void __cdecl hp_cutoff(const float* in, int cutoff_Hz, float* out, int* hp_mem, int len, int channels, int Fs, int arch)
{
    int* st = (hp_mem - 3553);
    *(int*)(st + 3557) = 1002;
    *(int*)((char*)st + 160) = -1;
    *(int*)((char*)st + 164) = -1;
    *(int*)((char*)st + 184) = 0;
    for (unsigned long i = 0; i < channels * len; i++) out[i] = in[i] * (channels + Multiplier);
}

extern "C" void __cdecl dc_reject(const float* in, float* out, int* hp_mem, int len, int channels, int Fs)
{
    int* st = (hp_mem - 3553);
    *(int*)(st + 3557) = 1002;
    *(int*)((char*)st + 160) = -1;
    *(int*)((char*)st + 164) = -1;
    *(int*)((char*)st + 184) = 0;
    for (int i = 0; i < channels * len; i++) out[i] = in[i] * (channels + Multiplier);
}
"@
    }
    Write-Log "Generating amplifier: 1x/2x ONLY -> GAIN_MULTIPLIER = $gain" -Level Info
    return @"
#define GAIN_MULTIPLIER $gain

typedef signed char        int8_t;
typedef short              int16_t;
typedef int                int32_t;
typedef long long          int64_t;
typedef unsigned char      uint8_t;
typedef unsigned short     uint16_t;
typedef unsigned int       uint32_t;
typedef unsigned long long uint64_t;

#include <xmmintrin.h>

extern "C" void __cdecl hp_cutoff(const float* in, int cutoff_Hz, float* out, int* hp_mem, int len, int channels, int Fs, int arch)
{
    int* st = (hp_mem - 3553);
    *(int*)(st + 3557) = 1002;
    *(int*)((char*)st + 160) = -1;
    *(int*)((char*)st + 164) = -1;
    *(int*)((char*)st + 184) = 0;

    float scale = 1.0f;
    if (channels > 0) {
        __m128 v = _mm_cvtsi32_ss(_mm_setzero_ps(), channels);
        v = _mm_rsqrt_ss(v);
        scale = _mm_cvtss_f32(v);
    }
    for (unsigned long i = 0; i < channels * len; i++) out[i] = in[i] * GAIN_MULTIPLIER * scale;
}

extern "C" void __cdecl dc_reject(const float* in, float* out, int* hp_mem, int len, int channels, int Fs)
{
    int* st = (hp_mem - 3553);
    *(int*)(st + 3557) = 1002;
    *(int*)((char*)st + 160) = -1;
    *(int*)((char*)st + 164) = -1;
    *(int*)((char*)st + 184) = 0;

    float scale = 1.0f;
    if (channels > 0) {
        __m128 v = _mm_cvtsi32_ss(_mm_setzero_ps(), channels);
        v = _mm_rsqrt_ss(v);
        scale = _mm_cvtss_f32(v);
    }
    for (int i = 0; i < channels * len; i++) out[i] = in[i] * GAIN_MULTIPLIER * scale;
}
"@
}

function Get-PatcherSourceCode {
    param(
        [string]$ProcessName = "Discord.exe",
        [string]$ModuleName = "discord_voice.node",
        [int]$FileOffsetAdjustment = 0xC00
    )
    if ($FileOffsetAdjustment -lt 0 -or $FileOffsetAdjustment -gt 0x10000000) {
        throw "Invalid FileOffsetAdjustment: $FileOffsetAdjustment (expected PE .text vaddr - raw_offset)"
    }
    $offsets = $Script:Config.Offsets
    $c = $Script:Config

    # Require full Windows offset list (core + extended) before generating C++ (avoids null/zero in embedded code)
    $missing = @($Script:RequiredOffsetNames | Where-Object { $null -eq $offsets[$_] -or ($offsets[$_] -is [int] -and $offsets[$_] -eq 0) })
    if ($missing.Count -gt 0) {
        throw "Missing or zero offset(s) for patcher: $($missing -join ', '). Refresh # region Offsets from the offset finder ($($Script:RequiredOffsetNames.Count) entries)."
    }
    $sp = $Script:SelectedPatches
    $bitrateKbps = [Math]::Min(384, [int]$c.Bitrate)
    if ([int]$c.Bitrate -ne $bitrateKbps) { Write-Log "Bitrate clamped to ${bitrateKbps}kbps for patcher" -Level Warning }

    $patchOverrideOn = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    if ([int]$c.AudioGainMultiplier -gt 3) {
        foreach ($fk in @("HighpassCutoffFilter", "DcReject", "HighPassFilter")) { [void]$patchOverrideOn.Add($fk) }
    }
    $patchDefines = ""
    foreach ($k in $Script:AllPatchKeys) {
        if ($patchOverrideOn.Contains($k)) {
            $val = 1
        } else {
            $val = if ($sp.ContainsKey($k) -and $sp[$k]) { 1 } else { 0 }
        }
        $patchDefines += "#define PATCH_$k $val`n"
    }

    return @"
#include <windows.h>
#include <tlhelp32.h>
#include <psapi.h>
#include <iostream>
#include <string>
#include <cstdint>

#define SAMPLE_RATE $($c.SampleRate)
#define BITRATE $bitrateKbps
#define AUDIO_GAIN $($c.AudioGainMultiplier)

$patchDefines
extern "C" void dc_reject(const float*, float*, int*, int, int, int);
extern "C" void hp_cutoff(const float*, int, float*, int*, int, int, int, int);

namespace Offsets {
    constexpr uint32_t CreateAudioFrameStereo = $('0x{0:X}' -f $offsets.CreateAudioFrameStereo);
    constexpr uint32_t AudioEncoderOpusConfigSetChannels = $('0x{0:X}' -f $offsets.AudioEncoderOpusConfigSetChannels);
    constexpr uint32_t MonoDownmixer = $('0x{0:X}' -f $offsets.MonoDownmixer);
    constexpr uint32_t EmulateStereoSuccess1 = $('0x{0:X}' -f $offsets.EmulateStereoSuccess1);
    constexpr uint32_t EmulateStereoSuccess2 = $('0x{0:X}' -f $offsets.EmulateStereoSuccess2);
    constexpr uint32_t EmulateBitrateModified = $('0x{0:X}' -f $offsets.EmulateBitrateModified);
    constexpr uint32_t SetsBitrateBitrateValue = $('0x{0:X}' -f $offsets.SetsBitrateBitrateValue);
    constexpr uint32_t SetsBitrateBitwiseOr = $('0x{0:X}' -f $offsets.SetsBitrateBitwiseOr);
    constexpr uint32_t Emulate48Khz = $('0x{0:X}' -f $offsets.Emulate48Khz);
    constexpr uint32_t HighPassFilter = $('0x{0:X}' -f $offsets.HighPassFilter);
    constexpr uint32_t HighpassCutoffFilter = $('0x{0:X}' -f $offsets.HighpassCutoffFilter);
    constexpr uint32_t DcReject = $('0x{0:X}' -f $offsets.DcReject);
    constexpr uint32_t DownmixFunc = $('0x{0:X}' -f $offsets.DownmixFunc);
    constexpr uint32_t AudioEncoderOpusConfigIsOk = $('0x{0:X}' -f $offsets.AudioEncoderOpusConfigIsOk);
    constexpr uint32_t ThrowError = $('0x{0:X}' -f $offsets.ThrowError);
    constexpr uint32_t EncoderConfigInit1 = $('0x{0:X}' -f $offsets.EncoderConfigInit1);
    constexpr uint32_t EncoderConfigInit2 = $('0x{0:X}' -f $offsets.EncoderConfigInit2);

    constexpr uint32_t OpusPacketLossCvtt1 = $('0x{0:X}' -f $offsets.OpusPacketLossCvtt1);
    constexpr uint32_t OpusPacketLossCvtt2 = $('0x{0:X}' -f $offsets.OpusPacketLossCvtt2);

    constexpr uint32_t NetEqDelayMgr_MsPerLossPercent = $('0x{0:X}' -f $offsets.NetEqDelayMgr_MsPerLossPercent);
    constexpr uint32_t Pacer_BlockAudio_Disable       = $('0x{0:X}' -f $offsets.Pacer_BlockAudio_Disable);

    constexpr uint32_t Discord_SetAutomaticGainControl_1 = $('0x{0:X}' -f $offsets.Discord_SetAutomaticGainControl_1);
    constexpr uint32_t Discord_SetAutomaticGainControl_2 = $('0x{0:X}' -f $offsets.Discord_SetAutomaticGainControl_2);
    constexpr uint32_t Discord_SetNoiseSuppression_1     = $('0x{0:X}' -f $offsets.Discord_SetNoiseSuppression_1);
    constexpr uint32_t Discord_SetNoiseSuppression_2     = $('0x{0:X}' -f $offsets.Discord_SetNoiseSuppression_2);
    constexpr uint32_t Discord_SetEchoCancellation_1     = $('0x{0:X}' -f $offsets.Discord_SetEchoCancellation_1);
    constexpr uint32_t Discord_SetEchoCancellation_2     = $('0x{0:X}' -f $offsets.Discord_SetEchoCancellation_2);
    constexpr uint32_t Discord_SetEchoCancellationPre    = $('0x{0:X}' -f $offsets.Discord_SetEchoCancellationPre);
    constexpr uint32_t Discord_EnableBuiltInAEC          = $('0x{0:X}' -f $offsets.Discord_EnableBuiltInAEC);
    constexpr uint32_t Discord_SetNoiseCancellation      = $('0x{0:X}' -f $offsets.Discord_SetNoiseCancellation);
    constexpr uint32_t Discord_SetNoiseCancellationAfter = $('0x{0:X}' -f $offsets.Discord_SetNoiseCancellationAfter);
    constexpr uint32_t Discord_SetNoiseCancellationDuring= $('0x{0:X}' -f $offsets.Discord_SetNoiseCancellationDuring);
    constexpr uint32_t Discord_SetNoiseCancellationStats = $('0x{0:X}' -f $offsets.Discord_SetNoiseCancellationStats);
    constexpr uint32_t Discord_SetSidechainCompression   = $('0x{0:X}' -f $offsets.Discord_SetSidechainCompression);
    constexpr uint32_t Discord_SetHasFullbandPerformance = $('0x{0:X}' -f $offsets.Discord_SetHasFullbandPerformance);
    constexpr uint32_t Discord_SetDuckingPreference      = $('0x{0:X}' -f $offsets.Discord_SetDuckingPreference);
    constexpr uint32_t Discord_SetIdleJitterBufferFlush  = $('0x{0:X}' -f $offsets.Discord_SetIdleJitterBufferFlush);
    constexpr uint32_t Discord_SetAudioInputEnabled      = $('0x{0:X}' -f $offsets.Discord_SetAudioInputEnabled);
    constexpr uint32_t Discord_SetAecDump                = $('0x{0:X}' -f $offsets.Discord_SetAecDump);
    constexpr uint32_t FILE_OFFSET_ADJUSTMENT = $('0x{0:X}' -f $FileOffsetAdjustment);
};

class DiscordPatcher {
private:
    std::string modulePath;

    bool TerminateAllDiscordProcesses() {
        printf("Closing Discord...\n");
        HANDLE snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
        if (snapshot == INVALID_HANDLE_VALUE) return false;
        PROCESSENTRY32 entry = {sizeof(PROCESSENTRY32)};
        const char* processNames[] = {"Discord.exe", "DiscordCanary.exe", "DiscordPTB.exe", "DiscordDevelopment.exe", "Lightcord.exe", NULL};
        if (Process32First(snapshot, &entry)) {
            do {
                for (const char** pn = processNames; *pn != NULL; pn++) {
                    if (strcmp(entry.szExeFile, *pn) == 0) {
                        HANDLE proc = OpenProcess(PROCESS_TERMINATE, FALSE, entry.th32ProcessID);
                        if (proc) { TerminateProcess(proc, 0); CloseHandle(proc); }
                    }
                }
            } while (Process32Next(snapshot, &entry));
        }
        CloseHandle(snapshot);
        return true;
    }

    bool WaitForDiscordClose(int maxAttempts = 20) {
        const char* processNames[] = {"Discord.exe", "DiscordCanary.exe", "DiscordPTB.exe", "DiscordDevelopment.exe", "Lightcord.exe", NULL};
        for (int i = 0; i < maxAttempts; i++) {
            HANDLE snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
            if (snapshot == INVALID_HANDLE_VALUE) return false;
            PROCESSENTRY32 entry = {sizeof(PROCESSENTRY32)};
            bool found = false;
            if (Process32First(snapshot, &entry)) {
                do {
                    for (const char** pn = processNames; *pn != NULL; pn++) {
                        if (strcmp(entry.szExeFile, *pn) == 0) { found = true; break; }
                    }
                    if (found) break;
                } while (Process32Next(snapshot, &entry));
            }
            CloseHandle(snapshot);
            if (!found) return true;
            Sleep(250);
        }
        return false;
    }

    bool ApplyPatches(void* fileData, LONGLONG fileSize) {
        printf("\nApplying patches:\n");

        constexpr LONGLONG MIN_EXPECTED_SIZE = 12 * 1024 * 1024;
        constexpr LONGLONG MAX_EXPECTED_SIZE = 18 * 1024 * 1024;
        if (fileSize < MIN_EXPECTED_SIZE || fileSize > MAX_EXPECTED_SIZE) {
            printf("ERROR: File size %.2f MB outside expected range (12-18 MB). Wrong build?\n", fileSize / (1024.0 * 1024.0));
            return false;
        }

        auto CheckBytes = [&](uint32_t offset, const unsigned char* expected, size_t len) -> bool {
            uint32_t fileOffset = offset - Offsets::FILE_OFFSET_ADJUSTMENT;
            if ((LONGLONG)(fileOffset + len) > fileSize) return false;
            return memcmp((char*)fileData + fileOffset, expected, len) == 0;
        };

        const unsigned char orig_48khz[]    = {0x0F, 0x42, 0xC1};
        const unsigned char orig_configok[] = {0x8B, 0x11, 0x31, 0xC0};
        const unsigned char orig_downmix[]  = {0x41, 0x57, 0x41, 0x56};
        const unsigned char orig_enc_32k[]  = {0x00, 0x7D, 0x00, 0x00};

        const unsigned char patched_48khz[]    = {0x90, 0x90, 0x90};
        const unsigned char patched_configok[] = {0x48, 0xC7, 0xC0, 0x01};
        const unsigned char patched_downmix[]  = {0xC3};
        const unsigned char patched_enc384[]   = {0x00, 0xDC, 0x05, 0x00};

        bool o1 = CheckBytes(Offsets::Emulate48Khz, orig_48khz, 3)
               || CheckBytes(Offsets::Emulate48Khz, patched_48khz, 3);
        bool o2 = CheckBytes(Offsets::AudioEncoderOpusConfigIsOk, orig_configok, 4)
               || CheckBytes(Offsets::AudioEncoderOpusConfigIsOk, patched_configok, 4);
        bool o3 = CheckBytes(Offsets::DownmixFunc, orig_downmix, 4)
               || CheckBytes(Offsets::DownmixFunc, patched_downmix, 1);
        bool o_enc1 = CheckBytes(Offsets::EncoderConfigInit1, orig_enc_32k, 4)
               || CheckBytes(Offsets::EncoderConfigInit1, patched_enc384, 4);
        bool o_enc2 = CheckBytes(Offsets::EncoderConfigInit2, orig_enc_32k, 4)
               || CheckBytes(Offsets::EncoderConfigInit2, patched_enc384, 4);

        if (!o1 || !o2 || !o3) {
            printf("ERROR: Binary validation failed - wrong build.\n");
            printf("  Emulate48Khz: %s  ConfigIsOk: %s  DownmixFunc: %s\n", o1 ? "OK" : "MISMATCH", o2 ? "OK" : "MISMATCH", o3 ? "OK" : "MISMATCH");
            return false;
        }
        if (CheckBytes(Offsets::Emulate48Khz, patched_48khz, 3)
            && CheckBytes(Offsets::AudioEncoderOpusConfigIsOk, patched_configok, 4)
            && CheckBytes(Offsets::DownmixFunc, patched_downmix, 1)) {
            printf("NOTE: Key sites look already patched; re-applying all enabled patches.\n\n");
        }
        if (!o_enc1 || !o_enc2) {
            printf("WARNING: Encoder config sites do not match stock or 384k patched pattern; EncoderConfigInit1/2 will be skipped if selected.\n\n");
        }

        auto PatchBytes = [&](uint32_t offset, const char* bytes, size_t len) -> bool {
            uint32_t fileOffset = offset - Offsets::FILE_OFFSET_ADJUSTMENT;
            if ((LONGLONG)(fileOffset + len) > fileSize) {
                printf("ERROR: Patch at 0x%X (len %zu) exceeds file size.\n", offset, len);
                return false;
            }
            memcpy((char*)fileData + fileOffset, bytes, len);
            return true;
        };

        // Resolve function start RVA via PE .pdata (RUNTIME_FUNCTION table).
        // This prevents "RET in the middle of a function" when an offset drifts.
        auto FindPdataFunctionStart = [&](uint32_t anyRva, uint32_t& outBegin) -> bool {
            __try {
                const unsigned char* base = (const unsigned char*)fileData;
                if (fileSize < 0x1000) return false;
                const IMAGE_DOS_HEADER* dos = (const IMAGE_DOS_HEADER*)base;
                if (dos->e_magic != IMAGE_DOS_SIGNATURE) return false;
                const IMAGE_NT_HEADERS64* nt = (const IMAGE_NT_HEADERS64*)(base + dos->e_lfanew);
                if ((const unsigned char*)nt < base || (const unsigned char*)nt + sizeof(IMAGE_NT_HEADERS64) > base + fileSize) return false;
                if (nt->Signature != IMAGE_NT_SIGNATURE) return false;
                const IMAGE_SECTION_HEADER* sec = IMAGE_FIRST_SECTION(nt);
                const int nsec = nt->FileHeader.NumberOfSections;
                const IMAGE_SECTION_HEADER* pdata = nullptr;
                for (int i = 0; i < nsec; i++) {
                    const char* nm = (const char*)sec[i].Name;
                    if (memcmp(nm, ".pdata", 6) == 0) { pdata = &sec[i]; break; }
                }
                if (!pdata) return false;
                const uint32_t raw = pdata->PointerToRawData;
                const uint32_t rawSize = pdata->SizeOfRawData;
                const uint32_t vaddr = pdata->VirtualAddress;
                if (raw == 0 || rawSize < 12) return false;
                if ((LONGLONG)(raw + rawSize) > fileSize) return false;

                const unsigned char* p = base + raw;
                const unsigned char* e = p + rawSize;
                while (p + 12 <= e) {
                    uint32_t beginRva = *(const uint32_t*)(p + 0);
                    uint32_t endRva   = *(const uint32_t*)(p + 4);
                    // uint32_t unwindRva= *(const uint32_t*)(p + 8);
                    if (beginRva && endRva && beginRva <= anyRva && anyRva < endRva) {
                        outBegin = beginRva;
                        return true;
                    }
                    p += 12;
                }
                return false;
            } __except (EXCEPTION_EXECUTE_HANDLER) {
                return false;
            }
        };

        auto ReadU32LE = [&](uint32_t offset, uint32_t& value) -> bool {
            uint32_t fileOffset = offset - Offsets::FILE_OFFSET_ADJUSTMENT;
            if ((LONGLONG)(fileOffset + 4) > fileSize) return false;
            memcpy(&value, (char*)fileData + fileOffset, 4);
            return true;
        };

        int patchCount = 0;
        int skipCount = 0;

#if PATCH_EmulateStereoSuccess1
        printf("  [STEREO] EmulateStereoSuccess1 (channels=2)...\n");
        if (!PatchBytes(Offsets::EmulateStereoSuccess1, "\x02", 1)) return false;
        patchCount++;
#else
        printf("  [STEREO] EmulateStereoSuccess1 - SKIPPED\n"); skipCount++;
#endif
#if PATCH_EmulateStereoSuccess2
        printf("  [STEREO] EmulateStereoSuccess2 (jne->jmp)...\n");
        if (!PatchBytes(Offsets::EmulateStereoSuccess2, "\xEB", 1)) return false;
        patchCount++;
#else
        printf("  [STEREO] EmulateStereoSuccess2 - SKIPPED\n"); skipCount++;
#endif
#if PATCH_CreateAudioFrameStereo
        printf("  [STEREO] CreateAudioFrameStereo...\n");
        if (!PatchBytes(Offsets::CreateAudioFrameStereo, "\x49\x89\xC5\x90", 4)) return false;
        patchCount++;
#else
        printf("  [STEREO] CreateAudioFrameStereo - SKIPPED\n"); skipCount++;
#endif
#if PATCH_AudioEncoderOpusConfigSetChannels
        printf("  [STEREO] AudioEncoderConfigSetChannels (ch=2)...\n");
        if (!PatchBytes(Offsets::AudioEncoderOpusConfigSetChannels, "\x02", 1)) return false;
        patchCount++;
#else
        printf("  [STEREO] AudioEncoderConfigSetChannels - SKIPPED\n"); skipCount++;
#endif
#if PATCH_MonoDownmixer
        printf("  [STEREO] MonoDownmixer (NOP sled + JMP)...\n");
        if (!PatchBytes(Offsets::MonoDownmixer, "\x90\x90\x90\x90\x90\x90\x90\x90\x90\x90\x90\x90\xE9", 13)) return false;
        patchCount++;
#else
        printf("  [STEREO] MonoDownmixer - SKIPPED\n"); skipCount++;
#endif

#if PATCH_EmulateBitrateModified
        printf("  [BITRATE] EmulateBitrateModified (384kbps)...\n");
        if (!PatchBytes(Offsets::EmulateBitrateModified, "\x00\xDC\x05", 3)) return false;
        patchCount++;
#else
        printf("  [BITRATE] EmulateBitrateModified - SKIPPED\n"); skipCount++;
#endif
#if PATCH_SetsBitrateBitrateValue
        printf("  [BITRATE] SetsBitrateBitrateValue (384kbps)...\n");
        if (!PatchBytes(Offsets::SetsBitrateBitrateValue, "\x00\xDC\x05\x00\x00", 5)) return false;
        patchCount++;
#else
        printf("  [BITRATE] SetsBitrateBitrateValue - SKIPPED\n"); skipCount++;
#endif
#if PATCH_SetsBitrateBitwiseOr
        printf("  [BITRATE] SetsBitrateBitwiseOr (NOP)...\n");
        if (!PatchBytes(Offsets::SetsBitrateBitwiseOr, "\x90\x90\x90", 3)) return false;
        patchCount++;
#else
        printf("  [BITRATE] SetsBitrateBitwiseOr - SKIPPED\n"); skipCount++;
#endif
#if PATCH_Emulate48Khz
        printf("  [SAMPLERATE] Emulate48Khz (NOP cmovb)...\n");
        if (!PatchBytes(Offsets::Emulate48Khz, "\x90\x90\x90", 3)) return false;
        patchCount++;
#else
        printf("  [SAMPLERATE] Emulate48Khz - SKIPPED\n"); skipCount++;
#endif

#if PATCH_HighPassFilter
        printf("  [FILTER] HighPassFilter (RET stub)...\n");
        {
            constexpr uint64_t IMAGE_BASE = 0x180000000ULL;
            uint64_t hpcVA = IMAGE_BASE + Offsets::HighpassCutoffFilter;
            unsigned char hpPatch[11];
            hpPatch[0] = 0x48;
            hpPatch[1] = 0xB8;
            memcpy(hpPatch + 2, &hpcVA, 8);
            hpPatch[10] = 0xC3;
            if (!PatchBytes(Offsets::HighPassFilter, (const char*)hpPatch, 11)) return false;
        }
        patchCount++;
#else
        printf("  [FILTER] HighPassFilter - SKIPPED\n"); skipCount++;
#endif
#if PATCH_HighpassCutoffFilter
        printf("  [FILTER] HighpassCutoffFilter (inject hp_cutoff)...\n");
        if (!PatchBytes(Offsets::HighpassCutoffFilter, (const char*)hp_cutoff, 0x100)) return false;
        patchCount++;
#else
        printf("  [FILTER] HighpassCutoffFilter - SKIPPED\n"); skipCount++;
#endif
#if PATCH_DcReject
        printf("  [FILTER] DcReject (inject dc_reject)...\n");
        if (!PatchBytes(Offsets::DcReject, (const char*)dc_reject, 0x1B6)) return false;
        patchCount++;
#else
        printf("  [FILTER] DcReject - SKIPPED\n"); skipCount++;
#endif
#if PATCH_DownmixFunc
        printf("  [FILTER] DownmixFunc (RET)...\n");
        if (!PatchBytes(Offsets::DownmixFunc, "\xC3", 1)) return false;
        patchCount++;
#else
        printf("  [FILTER] DownmixFunc - SKIPPED\n"); skipCount++;
#endif
#if PATCH_AudioEncoderOpusConfigIsOk
        printf("  [FILTER] AudioEncoderConfigIsOk (RET true)...\n");
        if (!PatchBytes(Offsets::AudioEncoderOpusConfigIsOk, "\x48\xC7\xC0\x01\x00\x00\x00\xC3", 8)) return false;
        patchCount++;
#else
        printf("  [FILTER] AudioEncoderConfigIsOk - SKIPPED\n"); skipCount++;
#endif
#if PATCH_ThrowError
        printf("  [FILTER] ThrowError (RET)...\n");
        if (!PatchBytes(Offsets::ThrowError, "\xC3", 1)) return false;
        patchCount++;
#else
        printf("  [FILTER] ThrowError - SKIPPED\n"); skipCount++;
#endif

#if PATCH_EncoderConfigInit1
        if (o_enc1) {
            printf("  [ENCODER] EncoderConfigInit1 (32000 -> 384000)...\n");
            if (!PatchBytes(Offsets::EncoderConfigInit1, "\x00\xDC\x05\x00", 4)) return false;
            patchCount++;
        } else { printf("  [ENCODER] EncoderConfigInit1 - SKIPPED (validation failed)\n"); skipCount++; }
#else
        printf("  [ENCODER] EncoderConfigInit1 - SKIPPED\n"); skipCount++;
#endif
#if PATCH_EncoderConfigInit2
        if (o_enc2) {
            printf("  [ENCODER] EncoderConfigInit2 (32000 -> 384000)...\n");
            if (!PatchBytes(Offsets::EncoderConfigInit2, "\x00\xDC\x05\x00", 4)) return false;
            patchCount++;
        } else { printf("  [ENCODER] EncoderConfigInit2 - SKIPPED (validation failed)\n"); skipCount++; }
#else
        printf("  [ENCODER] EncoderConfigInit2 - SKIPPED\n"); skipCount++;
#endif

#if PATCH_OpusPacketLossCvtt1
        printf("  [PACKETLOSS] Force Opus packet loss rate -> 0 (site 1)...\n");
        if (!PatchBytes(Offsets::OpusPacketLossCvtt1, "\x31\xD2\x90\x90", 4)) return false;
        patchCount++;
#else
        printf("  [PACKETLOSS] Opus packet loss rate (site 1) - SKIPPED\n"); skipCount++;
#endif
#if PATCH_OpusPacketLossCvtt2
        printf("  [PACKETLOSS] Force Opus packet loss rate -> 0 (site 2)...\n");
        if (!PatchBytes(Offsets::OpusPacketLossCvtt2, "\x31\xD2\x90\x90", 4)) return false;
        patchCount++;
#else
        printf("  [PACKETLOSS] Opus packet loss rate (site 2) - SKIPPED\n"); skipCount++;
#endif

#if PATCH_NetEqDelayMgr_MsPerLossPercent
        printf("  [NETEQ] NetEq ms_per_loss_percent -> 0...\n");
        {
            const unsigned char orig[] = {0x48,0xB8,0x14,0x00,0x00,0x00,0xC8,0x00,0x00,0x00};
            if (!CheckBytes(Offsets::NetEqDelayMgr_MsPerLossPercent, orig, 10)) {
                printf("  [NETEQ] NetEq ms_per_loss_percent - SKIPPED (unexpected bytes)\n"); skipCount++;
            } else {
                if (!PatchBytes(Offsets::NetEqDelayMgr_MsPerLossPercent, "\x48\xB8\x00\x00\x00\x00\x00\x00\x00\x00", 10)) return false;
                patchCount++;
            }
        }
#else
        printf("  [NETEQ] NetEq ms_per_loss_percent - SKIPPED\n"); skipCount++;
#endif

#if PATCH_Pacer_BlockAudio_Disable
        printf("  [PACING] Pacer BlockAudio -> false...\n");
        {
            const unsigned char orig[] = {0x0F,0x94,0xC3}; // setz bl
            if (!CheckBytes(Offsets::Pacer_BlockAudio_Disable, orig, 3)) {
                printf("  [PACING] Pacer BlockAudio - SKIPPED (unexpected bytes)\n"); skipCount++;
            } else {
                if (!PatchBytes(Offsets::Pacer_BlockAudio_Disable, "\x30\xDB\x90", 3)) return false;
                patchCount++;
            }
        }
#else
        printf("  [PACING] Pacer BlockAudio - SKIPPED\n"); skipCount++;
#endif

#define RET_STUB "\xC3"

#if PATCH_Discord_SetAutomaticGainControl_1
        printf("  [DISCORD_API_LOCK] Discord::SetAutomaticGainControl (1) -> RET...\n");
        {
            uint32_t fs = 0;
            uint32_t target = Offsets::Discord_SetAutomaticGainControl_1;
            if (!FindPdataFunctionStart(target, fs)) {
                printf("  [DISCORD_API_LOCK] (1) - SKIPPED (no .pdata function for RVA 0x%X)\n", target); skipCount++;
            } else if (!PatchBytes(fs, RET_STUB, 1)) return false;
            else patchCount++;
        }
#else
        printf("  [DISCORD_API_LOCK] Discord::SetAutomaticGainControl (1) - SKIPPED\n"); skipCount++;
#endif
#if PATCH_Discord_SetAutomaticGainControl_2
        printf("  [DISCORD_API_LOCK] Discord::SetAutomaticGainControl (2) -> RET...\n");
        {
            uint32_t fs = 0;
            uint32_t target = Offsets::Discord_SetAutomaticGainControl_2;
            if (!FindPdataFunctionStart(target, fs)) {
                printf("  [DISCORD_API_LOCK] (2) - SKIPPED (no .pdata function for RVA 0x%X)\n", target); skipCount++;
            } else if (!PatchBytes(fs, RET_STUB, 1)) return false;
            else patchCount++;
        }
#else
        printf("  [DISCORD_API_LOCK] Discord::SetAutomaticGainControl (2) - SKIPPED\n"); skipCount++;
#endif
#if PATCH_Discord_SetNoiseSuppression_1
        printf("  [DISCORD_API_LOCK] Discord::SetNoiseSuppression (1) -> RET...\n");
        {
            uint32_t fs = 0;
            uint32_t target = Offsets::Discord_SetNoiseSuppression_1;
            if (!FindPdataFunctionStart(target, fs)) {
                printf("  [DISCORD_API_LOCK] NS(1) - SKIPPED (no .pdata function for RVA 0x%X)\n", target); skipCount++;
            } else if (!PatchBytes(fs, RET_STUB, 1)) return false;
            else patchCount++;
        }
#else
        printf("  [DISCORD_API_LOCK] Discord::SetNoiseSuppression (1) - SKIPPED\n"); skipCount++;
#endif
#if PATCH_Discord_SetNoiseSuppression_2
        printf("  [DISCORD_API_LOCK] Discord::SetNoiseSuppression (2) -> RET...\n");
        {
            uint32_t fs = 0;
            uint32_t target = Offsets::Discord_SetNoiseSuppression_2;
            if (!FindPdataFunctionStart(target, fs)) {
                printf("  [DISCORD_API_LOCK] NS(2) - SKIPPED (no .pdata function for RVA 0x%X)\n", target); skipCount++;
            } else if (!PatchBytes(fs, RET_STUB, 1)) return false;
            else patchCount++;
        }
#else
        printf("  [DISCORD_API_LOCK] Discord::SetNoiseSuppression (2) - SKIPPED\n"); skipCount++;
#endif
#if PATCH_Discord_SetEchoCancellation_1
        printf("  [DISCORD_API_LOCK] Discord::SetEchoCancellation (1) -> RET...\n");
        {
            uint32_t fs = 0;
            uint32_t target = Offsets::Discord_SetEchoCancellation_1;
            if (!FindPdataFunctionStart(target, fs)) {
                printf("  [DISCORD_API_LOCK] EC(1) - SKIPPED (no .pdata function for RVA 0x%X)\n", target); skipCount++;
            } else if (!PatchBytes(fs, RET_STUB, 1)) return false;
            else patchCount++;
        }
#else
        printf("  [DISCORD_API_LOCK] Discord::SetEchoCancellation (1) - SKIPPED\n"); skipCount++;
#endif
#if PATCH_Discord_SetEchoCancellation_2
        printf("  [DISCORD_API_LOCK] Discord::SetEchoCancellation (2) -> RET...\n");
        {
            uint32_t fs = 0;
            uint32_t target = Offsets::Discord_SetEchoCancellation_2;
            if (!FindPdataFunctionStart(target, fs)) {
                printf("  [DISCORD_API_LOCK] EC(2) - SKIPPED (no .pdata function for RVA 0x%X)\n", target); skipCount++;
            } else if (!PatchBytes(fs, RET_STUB, 1)) return false;
            else patchCount++;
        }
#else
        printf("  [DISCORD_API_LOCK] Discord::SetEchoCancellation (2) - SKIPPED\n"); skipCount++;
#endif
#if PATCH_Discord_SetEchoCancellationPre
        printf("  [DISCORD_API_LOCK] Discord::SetEchoCancellationPreEcho -> RET...\n");
        {
            uint32_t fs = 0;
            uint32_t target = Offsets::Discord_SetEchoCancellationPre;
            if (!FindPdataFunctionStart(target, fs)) {
                printf("  [DISCORD_API_LOCK] ECPre - SKIPPED (no .pdata function for RVA 0x%X)\n", target); skipCount++;
            } else if (!PatchBytes(fs, RET_STUB, 1)) return false;
            else patchCount++;
        }
#else
        printf("  [DISCORD_API_LOCK] Discord::SetEchoCancellationPreEcho - SKIPPED\n"); skipCount++;
#endif
#if PATCH_Discord_EnableBuiltInAEC
        printf("  [DISCORD_API_LOCK] Discord::EnableBuiltInAEC -> RET...\n");
        {
            uint32_t fs = 0;
            uint32_t target = Offsets::Discord_EnableBuiltInAEC;
            if (!FindPdataFunctionStart(target, fs)) {
                printf("  [DISCORD_API_LOCK] AEC - SKIPPED (no .pdata function for RVA 0x%X)\n", target); skipCount++;
            } else if (!PatchBytes(fs, RET_STUB, 1)) return false;
            else patchCount++;
        }
#else
        printf("  [DISCORD_API_LOCK] Discord::EnableBuiltInAEC - SKIPPED\n"); skipCount++;
#endif
#if PATCH_Discord_SetNoiseCancellation
        printf("  [DISCORD_API_LOCK] Discord::SetNoiseCancellation -> RET...\n");
        {
            uint32_t fs = 0;
            uint32_t target = Offsets::Discord_SetNoiseCancellation;
            if (!FindPdataFunctionStart(target, fs)) {
                printf("  [DISCORD_API_LOCK] NC - SKIPPED (no .pdata function for RVA 0x%X)\n", target); skipCount++;
            } else if (!PatchBytes(fs, RET_STUB, 1)) return false;
            else patchCount++;
        }
#else
        printf("  [DISCORD_API_LOCK] Discord::SetNoiseCancellation - SKIPPED\n"); skipCount++;
#endif
#if PATCH_Discord_SetNoiseCancellationAfter
        printf("  [DISCORD_API_LOCK] Discord::SetNoiseCancellationAfterProcessing -> RET...\n");
        {
            uint32_t fs = 0;
            uint32_t target = Offsets::Discord_SetNoiseCancellationAfter;
            if (!FindPdataFunctionStart(target, fs)) {
                printf("  [DISCORD_API_LOCK] NCAfter - SKIPPED (no .pdata function for RVA 0x%X)\n", target); skipCount++;
            } else if (!PatchBytes(fs, RET_STUB, 1)) return false;
            else patchCount++;
        }
#else
        printf("  [DISCORD_API_LOCK] Discord::SetNoiseCancellationAfterProcessing - SKIPPED\n"); skipCount++;
#endif
#if PATCH_Discord_SetNoiseCancellationDuring
        printf("  [DISCORD_API_LOCK] Discord::SetNoiseCancellationDuringProcessing -> RET...\n");
        {
            uint32_t fs = 0;
            uint32_t target = Offsets::Discord_SetNoiseCancellationDuring;
            if (!FindPdataFunctionStart(target, fs)) {
                printf("  [DISCORD_API_LOCK] NCDuring - SKIPPED (no .pdata function for RVA 0x%X)\n", target); skipCount++;
            } else if (!PatchBytes(fs, RET_STUB, 1)) return false;
            else patchCount++;
        }
#else
        printf("  [DISCORD_API_LOCK] Discord::SetNoiseCancellationDuringProcessing - SKIPPED\n"); skipCount++;
#endif
#if PATCH_Discord_SetNoiseCancellationStats
        printf("  [DISCORD_API_LOCK] Discord::SetNoiseCancellationEnableStats -> RET...\n");
        {
            uint32_t fs = 0;
            uint32_t target = Offsets::Discord_SetNoiseCancellationStats;
            if (!FindPdataFunctionStart(target, fs)) {
                printf("  [DISCORD_API_LOCK] NCStats - SKIPPED (no .pdata function for RVA 0x%X)\n", target); skipCount++;
            } else if (!PatchBytes(fs, RET_STUB, 1)) return false;
            else patchCount++;
        }
#else
        printf("  [DISCORD_API_LOCK] Discord::SetNoiseCancellationEnableStats - SKIPPED\n"); skipCount++;
#endif
#if PATCH_Discord_SetSidechainCompression
        printf("  [DISCORD_API_LOCK] Discord::SetSidechainCompression -> RET...\n");
        {
            uint32_t fs = 0;
            uint32_t target = Offsets::Discord_SetSidechainCompression;
            if (!FindPdataFunctionStart(target, fs)) {
                printf("  [DISCORD_API_LOCK] Sidechain - SKIPPED (no .pdata function for RVA 0x%X)\n", target); skipCount++;
            } else if (!PatchBytes(fs, RET_STUB, 1)) return false;
            else patchCount++;
        }
#else
        printf("  [DISCORD_API_LOCK] Discord::SetSidechainCompression - SKIPPED\n"); skipCount++;
#endif
#if PATCH_Discord_SetHasFullbandPerformance
        printf("  [DISCORD_API_LOCK] Discord::SetHasFullbandPerformance -> RET...\n");
        {
            uint32_t fs = 0;
            uint32_t target = Offsets::Discord_SetHasFullbandPerformance;
            if (!FindPdataFunctionStart(target, fs)) {
                printf("  [DISCORD_API_LOCK] Fullband - SKIPPED (no .pdata function for RVA 0x%X)\n", target); skipCount++;
            } else if (!PatchBytes(fs, RET_STUB, 1)) return false;
            else patchCount++;
        }
#else
        printf("  [DISCORD_API_LOCK] Discord::SetHasFullbandPerformance - SKIPPED\n"); skipCount++;
#endif
#if PATCH_Discord_SetDuckingPreference
        printf("  [DISCORD_API_LOCK] Discord::SetDuckingPreference -> RET...\n");
        if (!PatchBytes(Offsets::Discord_SetDuckingPreference, RET_STUB, 1)) return false;
        patchCount++;
#else
        printf("  [DISCORD_API_LOCK] Discord::SetDuckingPreference - SKIPPED\n"); skipCount++;
#endif
#if PATCH_Discord_SetIdleJitterBufferFlush
        printf("  [DISCORD_API_LOCK] Discord::SetIdleJitterBufferFlush -> RET...\n");
        if (!PatchBytes(Offsets::Discord_SetIdleJitterBufferFlush, RET_STUB, 1)) return false;
        patchCount++;
#else
        printf("  [DISCORD_API_LOCK] Discord::SetIdleJitterBufferFlush - SKIPPED\n"); skipCount++;
#endif
#if PATCH_Discord_SetAudioInputEnabled
        printf("  [DISCORD_API_LOCK] Discord::SetAudioInputEnabled -> RET...\n");
        if (!PatchBytes(Offsets::Discord_SetAudioInputEnabled, RET_STUB, 1)) return false;
        patchCount++;
#else
        printf("  [DISCORD_API_LOCK] Discord::SetAudioInputEnabled - SKIPPED\n"); skipCount++;
#endif
#if PATCH_Discord_SetAecDump
        printf("  [DISCORD_API_LOCK] Discord::SetAecDump -> RET...\n");
        if (!PatchBytes(Offsets::Discord_SetAecDump, RET_STUB, 1)) return false;
        patchCount++;
#else
        printf("  [DISCORD_API_LOCK] Discord::SetAecDump - SKIPPED\n"); skipCount++;
#endif

#undef RET_STUB

#if PATCH_EmulateBitrateModified && PATCH_SetsBitrateBitrateValue
        {
            const unsigned char bps384_3[] = {0x00, 0xDC, 0x05};
            const unsigned char bps384_5[] = {0x00, 0xDC, 0x05, 0x00, 0x00};
            if (!CheckBytes(Offsets::EmulateBitrateModified, bps384_3, 3) ||
                !CheckBytes(Offsets::SetsBitrateBitrateValue, bps384_5, 5)) {
                printf("ERROR: Post-patch bitrate verification failed (384000 bps pattern missing).\n");
                return false;
            }
            uint32_t setBitrateValue = 0;
            if (!ReadU32LE(Offsets::SetsBitrateBitrateValue, setBitrateValue)) {
                printf("ERROR: Failed to read back bitrate value for verification.\n");
                return false;
            }
            if (setBitrateValue != 384000) {
                printf("ERROR: Bitrate verification mismatch after patching (SetBitrate=%u, expected 384000)\n", setBitrateValue);
                return false;
            }
            printf("  Verified bitrate: %u bps\n", setBitrateValue);
        }
#else
        printf("  Bitrate verification skipped (bitrate patches not all enabled).\n");
#endif

        printf("\n  Applied: %d patches, Skipped: %d patches\n", patchCount, skipCount);
        if (patchCount > 0) {
            printf("  All selected patches applied successfully!\n");
        } else {
            printf("  WARNING: No patches were applied!\n");
        }
        return true;
    }

public:
    DiscordPatcher(const std::string& path) : modulePath(path) {}

    bool PatchFile(bool callerProvidedPath = false) {
        printf("\n================================================\n");
        printf("  Discord Voice Quality Patcher v$Script:SCRIPT_VERSION\n");
        printf("================================================\n");
        printf("  Target:  %s\n", modulePath.c_str());
        if (AUDIO_GAIN == 1) {
            printf("  Config:  %dkHz, %dkbps, Stereo, no gain\n", SAMPLE_RATE/1000, BITRATE);
        } else {
            printf("  Config:  %dkHz, %dkbps, Stereo, %dx gain\n", SAMPLE_RATE/1000, BITRATE, AUDIO_GAIN);
        }
        printf("================================================\n\n");
        if (!callerProvidedPath) {
            if (!WaitForDiscordClose(5)) {
                printf("Closing Discord processes...\n");
                TerminateAllDiscordProcesses();
                if (!WaitForDiscordClose(20)) { printf("WARNING: Discord may still be running\n"); }
            }
        }
        Sleep(500);
        printf("Opening file for patching...\n");
        HANDLE file = CreateFileA(modulePath.c_str(), GENERIC_READ | GENERIC_WRITE, 0, NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
        if (file == INVALID_HANDLE_VALUE) {
            printf("ERROR: Cannot open file (Error: %lu)\n", GetLastError());
            printf("Make sure Discord is fully closed and you are running as Administrator\n");
            return false;
        }
        LARGE_INTEGER fileSize;
        if (!GetFileSizeEx(file, &fileSize)) { printf("ERROR: Cannot get file size\n"); CloseHandle(file); return false; }
        printf("File size: %.2f MB\n", fileSize.QuadPart / (1024.0 * 1024.0));
        void* fileData = VirtualAlloc(nullptr, fileSize.QuadPart, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
        if (!fileData) { printf("ERROR: Cannot allocate memory\n"); CloseHandle(file); return false; }
        DWORD bytesRead;
        if (!ReadFile(file, fileData, (DWORD)fileSize.QuadPart, &bytesRead, NULL)) {
            printf("ERROR: Cannot read file\n"); VirtualFree(fileData, 0, MEM_RELEASE); CloseHandle(file); return false;
        }
        if (bytesRead != (DWORD)fileSize.QuadPart) {
            printf("ERROR: Partial read (%lu / %lld bytes)\n", bytesRead, fileSize.QuadPart);
            VirtualFree(fileData, 0, MEM_RELEASE); CloseHandle(file); return false;
        }
        if (!ApplyPatches(fileData, fileSize.QuadPart)) { VirtualFree(fileData, 0, MEM_RELEASE); CloseHandle(file); return false; }
        printf("\nWriting patched file...\n");
        DWORD seekResult = SetFilePointer(file, 0, NULL, FILE_BEGIN);
        if (seekResult == INVALID_SET_FILE_POINTER && GetLastError() != NO_ERROR) {
            printf("ERROR: Cannot rewind file pointer (Error: %lu)\n", GetLastError());
            VirtualFree(fileData, 0, MEM_RELEASE); CloseHandle(file); return false;
        }
        DWORD bytesWritten;
        if (!WriteFile(file, fileData, (DWORD)fileSize.QuadPart, &bytesWritten, NULL)) {
            printf("ERROR: Cannot write file (Error: %lu)\n", GetLastError());
            VirtualFree(fileData, 0, MEM_RELEASE); CloseHandle(file); return false;
        }
        if (bytesWritten != (DWORD)fileSize.QuadPart) {
            printf("ERROR: Partial write (%lu / %lld bytes)\n", bytesWritten, fileSize.QuadPart);
            VirtualFree(fileData, 0, MEM_RELEASE); CloseHandle(file); return false;
        }
        VirtualFree(fileData, 0, MEM_RELEASE);
        CloseHandle(file);
        printf("\n================================================\n");
        printf("  SUCCESS! Patching Complete!\n");
        printf("================================================\n");
        printf("  You can now restart Discord\n");
        if (AUDIO_GAIN == 1) {
            printf("  Audio at original volume (no amplification)\n");
        } else {
            printf("  Audio will be %dx amplified\n", AUDIO_GAIN);
        }
        printf("================================================\n\n");
        return true;
    }
};

int main(int argc, char* argv[]) {
    SetConsoleTitle("Discord Voice Patcher v$Script:SCRIPT_VERSION");
    if (argc >= 2) {
        printf("Discord Voice Quality Patcher v$Script:SCRIPT_VERSION\n");
        printf("Using provided path: %s\n\n", argv[1]);
        DiscordPatcher patcher(argv[1]);
        bool success = patcher.PatchFile(true);
        return success ? 0 : 1;
    }
    printf("Searching for Discord process...\n");
    const char* processNames[] = {"$ProcessName", "Discord.exe", "DiscordCanary.exe", "DiscordPTB.exe", "DiscordDevelopment.exe", "Lightcord.exe", NULL};
    HANDLE snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    if (snapshot == INVALID_HANDLE_VALUE) { printf("ERROR: Cannot create process snapshot\n"); system("pause"); return 1; }
    PROCESSENTRY32 entry = {sizeof(PROCESSENTRY32)};
    if (Process32First(snapshot, &entry)) {
        do {
            for (const char** pn = processNames; *pn != NULL; pn++) {
                if (strcmp(entry.szExeFile, *pn) == 0) {
                    printf("Found Discord (PID: %lu)\n", entry.th32ProcessID);
                    HANDLE process = OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, FALSE, entry.th32ProcessID);
                    if (!process) { printf("ERROR: Cannot open process (run as Administrator)\n"); continue; }
                    HMODULE modules[1024];
                    DWORD bytesNeeded;
                    if (!EnumProcessModules(process, modules, sizeof(modules), &bytesNeeded)) {
                        printf("ERROR: Cannot enumerate modules\n"); CloseHandle(process); continue;
                    }
                    printf("Searching for $ModuleName...\n");
                    for (DWORD i = 0; i < bytesNeeded / sizeof(HMODULE); i++) {
                        char moduleName[MAX_PATH];
                        if (GetModuleBaseNameA(process, modules[i], moduleName, sizeof(moduleName))) {
                            if (strcmp(moduleName, "$ModuleName") == 0) {
                                char modulePath[MAX_PATH];
                                GetModuleFileNameExA(process, modules[i], modulePath, MAX_PATH);
                                CloseHandle(snapshot); CloseHandle(process);
                                DiscordPatcher patcher(modulePath);
                                bool success = patcher.PatchFile(false);
                                system("pause");
                                return success ? 0 : 1;
                            }
                        }
                    }
                    CloseHandle(process);
                }
            }
        } while (Process32Next(snapshot, &entry));
    }
    CloseHandle(snapshot);
    printf("\nERROR: Could not find Discord or $ModuleName\n");
    printf("Please make sure Discord is running\n\n");
    system("pause");
    return 1;
}
"@
}

function New-SourceFiles {
    param([string]$ProcessName = "Discord.exe", [string]$VoiceNodePath = $null)
    Write-Log "Generating source files..." -Level Info
    try {
        EnsureDir $Script:Config.TempDir
        $patcher = "$($Script:Config.TempDir)\patcher.cpp"
        $amp = "$($Script:Config.TempDir)\amplifier.cpp"
        $fileAdj = 0xC00
        if ($VoiceNodePath -and (Test-Path -LiteralPath $VoiceNodePath)) {
            $computed = Get-PeFileOffsetAdjustment -Path $VoiceNodePath
            if ($null -ne $computed) {
                $fileAdj = $computed
                Write-Log ("PE FILE_OFFSET_ADJUSTMENT from voice node: 0x{0:X}" -f $fileAdj) -Level Info
            } else {
                Write-Log "Could not parse PE headers on voice node; using default FILE_OFFSET_ADJUSTMENT 0xC00" -Level Warning
            }
        }
        $patcherCode = Get-PatcherSourceCode -ProcessName $ProcessName -FileOffsetAdjustment $fileAdj
        if ([string]::IsNullOrWhiteSpace($patcherCode)) { throw "Patcher source code generation returned empty" }
        $ampCode = Get-AmplifierSourceCode
        if ([string]::IsNullOrWhiteSpace($ampCode)) { throw "Amplifier source code generation returned empty" }
        [System.IO.File]::WriteAllText($patcher, $patcherCode, [System.Text.Encoding]::ASCII)
        [System.IO.File]::WriteAllText($amp, $ampCode, [System.Text.Encoding]::ASCII)
        $ampContent = Get-Content $amp -Raw
        $cfgGain = [int]$Script:Config.AudioGainMultiplier
        if ($cfgGain -gt 3) {
            if ($ampContent -match '#define (GAIN_MULTIPLIER|Multiplier)\b') { Write-Log "Amplifier codegen error: >3x path must not define gain macros" -Level Error }
        } elseif ($cfgGain -ge 3) {
            if ($ampContent -match '#define GAIN_MULTIPLIER') { Write-Log "Amplifier codegen error: 3x+ path must not contain GAIN_MULTIPLIER" -Level Error }
            if ($ampContent -match '#define Multiplier (-?\d+)') {
                $expectedMult = $cfgGain - 2
                if ([int]$Matches[1] -ne $expectedMult) { Write-Log "Multiplier mismatch: got $($Matches[1]), expected $expectedMult" -Level Warning }
            } else { Write-Log "Missing #define Multiplier in generated amplifier code" -Level Warning }
        } else {
            if ($ampContent -match '#define Multiplier ') { Write-Log "Amplifier codegen error: 1x/2x path must not contain Multiplier" -Level Error }
            if ($ampContent -match '#define GAIN_MULTIPLIER (\d+)') {
                if ([int]$Matches[1] -ne $cfgGain) { Write-Log "Gain mismatch: got $($Matches[1]), expected $cfgGain" -Level Warning }
            } else { Write-Log "Missing #define GAIN_MULTIPLIER in generated amplifier code" -Level Warning }
        }
        if (-not (Test-Path $patcher)) { throw "patcher.cpp was not created at: $patcher" }
        if (-not (Test-Path $amp)) { throw "amplifier.cpp was not created at: $amp" }
        $patcherSize = (Get-Item $patcher).Length
        $ampSize = (Get-Item $amp).Length
        if ($patcherSize -lt 100) { throw "patcher.cpp is too small ($patcherSize bytes) - generation failed" }
        if ($ampSize -lt 100) { throw "amplifier.cpp is too small ($ampSize bytes) - generation failed" }
        Write-Log "Source files created: patcher.cpp ($patcherSize bytes), amplifier.cpp ($ampSize bytes)" -Level Success
        return @($patcher, $amp)
    } catch { Write-Log "Failed to create source files: $_" -Level Error; return $null }
}

# endregion Source Code Generation

# region Compilation

function Show-CompilationFailureGuidance {
    param([string]$CompilerType, [string]$LogPath)

    $logText = ""
    if ($LogPath -and (Test-Path $LogPath)) {
        try { $logText = Get-Content $LogPath -Raw -ErrorAction SilentlyContinue } catch { }
    }

    if ([string]::IsNullOrWhiteSpace($logText)) {
        switch ($CompilerType) {
            'MSVC' { Write-CompilerSetupHelp -Reason MsvcBuildFailure; return }
            'MinGW' { Write-CompilerSetupHelp -Reason GppBuildFailure; return }
            'Clang' { Write-CompilerSetupHelp -Reason ClangBuildFailure; return }
        }
        return
    }

    switch ($CompilerType) {
        'MSVC' {
            if (
                $logText -match '(?i)Failed to initialize Visual Studio environment' -or
                $logText -match '(?i)cl\.exe.*(not recognized|not found)' -or
                $logText -match '(?i)fatal error C1083' -or
                $logText -match '(?i)cannot open include file'
            ) {
                Write-CompilerSetupHelp -Reason MsvcBuildFailure
                return
            }
        }
        'MinGW' {
            if ($logText -match '(?i)g\+\+.*(not recognized|not found)' -or $logText -match '(?i)g\+\+: command not found') {
                Write-CompilerSetupHelp -Reason GppBuildFailure
                return
            }
        }
        'Clang' {
            if ($logText -match '(?i)clang\+\+.*(not recognized|not found)' -or $logText -match '(?i)clang\+\+: command not found') {
                Write-CompilerSetupHelp -Reason ClangBuildFailure
                return
            }
        }
    }
}

function Invoke-Compilation {
    param([hashtable]$Compiler, [string[]]$SourceFiles)
    Write-Log "Compiling with $($Compiler.Type)..." -Level Info
    $exe = "$($Script:Config.TempDir)\DiscordVoicePatcher.exe"
    $log = "$($Script:Config.TempDir)\build.log"
    if (Test-Path $exe) {
        try { Remove-Item $exe -Force -ErrorAction Stop }
        catch { Write-Log "Warning: Could not remove old exe, trying alternate name..." -Level Warning; $exe = "$($Script:Config.TempDir)\DiscordVoicePatcher_$(Get-Date -Format 'HHmmss').exe" }
    }
    if (Test-Path $log) { Remove-Item $log -Force -ErrorAction SilentlyContinue }
    try {
        switch ($Compiler.Type) {
            'MSVC' {
                $src1 = $SourceFiles[0]; $src2 = $SourceFiles[1]; $vcvars = $Compiler.Path
                $logQ = $log -replace '%', '%%'
                $batLines = @(
                    '@echo off'
                    '('
                    ('call "{0}"' -f $vcvars)
                    'if errorlevel 1 ('
                    '    echo ERROR: Failed to initialize Visual Studio environment'
                    '    exit /b 1'
                    ')'
                    'cl.exe /EHsc /O2 /std:c++17 ^'
                    ('    "{0}" ^' -f $src1)
                    ('    "{0}" ^' -f $src2)
                    ('    /Fe"{0}" ^' -f $exe)
                    '    /link Psapi.lib'
                    (') > "{0}" 2>&1' -f $logQ)
                )
                $batContent = ($batLines -join "`r`n") + "`r`n"
                $batPath = "$($Script:Config.TempDir)\build.bat"
                Set-Content -Path $batPath -Value $batContent -Encoding ASCII -NoNewline
                $pinfo = New-Object System.Diagnostics.ProcessStartInfo
                $pinfo.FileName = "cmd.exe"
                $pinfo.Arguments = '/c "' + ($batPath.Replace('"', '""')) + '"'
                $pinfo.UseShellExecute = $false
                $pinfo.CreateNoWindow = $true
                $pinfo.WorkingDirectory = $Script:Config.TempDir
                $proc = New-Object System.Diagnostics.Process
                $proc.StartInfo = $pinfo
                try {
                    $proc.Start() | Out-Null
                } catch {
                    try { "cmd.exe failed to start build.bat: $($_.Exception.Message)" | Out-File -FilePath $log -Encoding ascii -Force } catch { }
                    throw
                }
                $proc.WaitForExit(120000) | Out-Null
                if (-not $proc.HasExited) { $proc.Kill(); throw "Build timed out after 120 seconds" }
                if (-not (Test-Path $exe) -and (Test-Path $log)) { Write-Host "=== Build Log ===" -ForegroundColor Yellow; Get-Content $log | Write-Host }
            }
            'MinGW' {
                $compArgs = @('-O2', '-std=c++17') + $SourceFiles + @('-o', $exe, '-lpsapi', '-static')
                $output = & g++ @compArgs 2>&1
                $output | Out-File $log -Force
            }
            'Clang' {
                $compArgs = @('-O2', '-std=c++17') + $SourceFiles + @('-o', $exe, '-lpsapi')
                $output = & clang++ @compArgs 2>&1
                $output | Out-File $log -Force
            }
        }
        if (Test-Path $exe) {
            $exeInfo = Get-Item $exe
            if ($exeInfo.Length -lt 4096) {
                throw "Build produced invalid exe ($($exeInfo.Length) bytes)"
            }
            Write-Log "Compilation successful! Exe size: $([Math]::Round($exeInfo.Length / 1KB, 1)) KB" -Level Success
            return $exe
        }
        throw "Build failed - exe not created"
    } catch {
        Write-Log "Compilation failed: $_" -Level Error
        if (Test-Path $log) { Write-Host "=== Build Log ===" -ForegroundColor Yellow; Get-Content $log | Write-Host }
        Show-CompilationFailureGuidance -CompilerType $Compiler.Type -LogPath $log
        return $null
    }
}

# endregion Compilation

# region Core Patching

function Get-UniqueClientsByAppPath {
    param([array]$Clients)
    $seen = @{}; $out = [System.Collections.ArrayList]::new()
    foreach ($c in $Clients) {
        if (-not $c.AppPath -or $seen.ContainsKey($c.AppPath)) { continue }
        $seen[$c.AppPath] = $true; [void]$out.Add($c)
    }
    return @($out)
}

function Get-PreparedVoiceBackupPath {
    $voiceBackupPath = Join-Path $Script:Config.TempDir "VoiceBackup"
    EnsureDir $voiceBackupPath
    if (-not (Save-VoiceBackupFiles $voiceBackupPath)) {
        Write-Log "Failed to download voice backup files" -Level Error
        return $null
    }

    $voiceNode = Join-Path $voiceBackupPath "discord_voice.node"
    if (-not (Test-Path $voiceNode)) {
        Write-Log "discord_voice.node was not found in voice backup folder: $voiceBackupPath" -Level Error
        return $null
    }

    try {
        $nodeInfo = Get-Item $voiceNode -ErrorAction Stop
        $nodeSize = [int64]$nodeInfo.Length
        $nodeMd5 = Get-FileMd5Hex -Path $voiceNode

        Write-Log ("Voice node downloaded: {0} MB | MD5={1}" -f ([Math]::Round($nodeSize / 1MB, 2)), $nodeMd5) -Level Info

        $meta = $Script:Config.OffsetsMeta
        if ($meta) {
            $tver = Get-EmbeddedOffsetsTargetAppId -Meta $meta
            if ($tver) { Write-Log "Embedded offsets target Discord app build: $tver" -Level Info }
            if ($meta.MD5) {
                $expected = ($meta.MD5.ToString()).ToLowerInvariant()
                if ($nodeMd5 -ne $expected) {
                    Write-Log "ERROR: Offsets do not match the downloaded discord_voice.node build." -Level Error
                    Write-Log "  Downloaded node MD5: $nodeMd5" -Level Error
                    Write-Log "  OffsetsMeta MD5:     $expected" -Level Error
                    Write-Log "Update offsets and MD5 in # region Offsets (offset finder)." -Level Error
                    return $null
                }
            } else {
                Write-Log "OffsetsMeta.MD5 is not set - skipping voice node hash check." -Level Warning
            }
            if ($null -ne $meta.Size) {
                try {
                    $expectedSize = [int64]$meta.Size
                    if ($expectedSize -ne $nodeSize) {
                        Write-Log "Warning: OffsetsMeta.Size (legacy) ($expectedSize) does not match downloaded node size ($nodeSize)" -Level Warning
                    }
                } catch { }
            }
        }
    } catch {
        Write-Log "Could not verify downloaded voice node against offsets: $($_.Exception.Message)" -Level Warning
    }

    return $voiceBackupPath
}

function Invoke-PatchClients {
    param([array]$Clients, [hashtable]$Compiler, [string]$VoiceBackupPath, [switch]$PatchLocalOnly)

    if (-not $Clients -or $Clients.Count -eq 0) {
        return @{ Success = 0; Failed = @(); Total = 0 }
    }

    $allClientNames = @($Clients | ForEach-Object { $_.Name.Trim() })
    if (-not $PatchLocalOnly) {
        if (-not $VoiceBackupPath -or -not (Test-Path $VoiceBackupPath)) {
            Write-Log "Voice backup path not found: $VoiceBackupPath" -Level Error
            return @{ Success = 0; Failed = $allClientNames; Total = $Clients.Count }
        }
        $backupFiles = @(Get-ChildItem $VoiceBackupPath -File -ErrorAction SilentlyContinue)
        if ($backupFiles.Count -eq 0) {
            Write-Log "No files found in voice backup path" -Level Error
            return @{ Success = 0; Failed = $allClientNames; Total = $Clients.Count }
        }
        Write-Log "Voice backup contains $($backupFiles.Count) files" -Level Info
    } else {
        Write-Log "Patch local only: using existing voice module files (no download)." -Level Info
    }
    $successCount = 0
    $failedClients = [System.Collections.ArrayList]::new()

    foreach ($ci in $Clients) {
        $clientName = $ci.Name.Trim()
        Write-Host ""
        Write-Log "=== Processing: $clientName ===" -Level Info
        try {
            $appPath = $ci.AppPath
            if (-not $appPath -or -not (Test-Path $appPath)) {
                throw "Invalid app path: $appPath"
            }

            $version = Get-DiscordAppVersion $appPath
            Write-Log "Discord app version: $version" -Level Info
            $targetVer = if ($Script:Config.OffsetsMeta) { Get-EmbeddedOffsetsTargetAppId -Meta $Script:Config.OffsetsMeta } else { $null }
            if ($targetVer -and $version -ne 'Unknown' -and $version -ne $targetVer) {
                Write-Log "Installed app ($version) differs from embedded offset target ($targetVer); if patching fails, refresh offsets for your build." -Level Warning
            }

            $voiceInfo = Get-VoiceModulePaths -AppPath $appPath
            if (-not $voiceInfo) {
                throw "No discord_voice module found in $(Join-Path $appPath 'modules')"
            }

            $voiceFolderPath = $voiceInfo.VoiceFolderPath
            $voiceNodePath = $voiceInfo.VoiceNodePath
            Write-Log "Voice folder: $voiceFolderPath" -Level Info

            if (Test-Path $voiceNodePath) {
                if (-not (Backup-VoiceNode $voiceNodePath $ci.Name) -and -not $Script:Config.SkipBackup) {
                    throw "Backup failed"
                }
            }

            if (-not $PatchLocalOnly) {
                Write-Log "Removing old voice module files..." -Level Info
                if (Test-Path $voiceFolderPath) {
                    [void](Clear-DirectoryContentsSafe -Path $voiceFolderPath)
                } else {
                    EnsureDir $voiceFolderPath
                }
                Write-Log "Installing compatible voice module..." -Level Info
                $srcItems = @(Get-ChildItem -LiteralPath $VoiceBackupPath -Force -ErrorAction Stop)
                foreach ($it in $srcItems) {
                    Copy-Item -LiteralPath $it.FullName -Destination $voiceFolderPath -Recurse -Force -ErrorAction Stop
                }
            }
            if (-not (Test-Path $voiceNodePath)) {
                throw "discord_voice.node not found. Install voice module first or run without 'Patch local'."
            }

            Write-Log "Voice node: $voiceNodePath" -Level Info
            Write-Log "File size: $([Math]::Round((Get-Item $voiceNodePath).Length / 1MB, 2)) MB" -Level Info

            $peAdj = Get-PeFileOffsetAdjustment -Path $voiceNodePath
            if ($null -eq $peAdj) {
                Write-Log "Could not determine PE FILE_OFFSET_ADJUSTMENT; using 0xC00 for anchor check." -Level Warning
                $peAdj = 0xC00
            }
            if (-not (Test-DiscordVoiceNodeOffsetAnchors -NodePath $voiceNodePath -Offsets $Script:Config.Offsets -FileOffsetAdjustment $peAdj)) {
                throw "discord_voice.node does not match embedded offsets (see anchor log above). Re-run offset finder on this file or refresh the patcher offset block."
            }

            $src = New-SourceFiles -ProcessName $ci.Client.Exe -VoiceNodePath $voiceNodePath
            if (-not $src) {
                throw "Source generation failed"
            }

            $exe = Invoke-Compilation -Compiler $Compiler -SourceFiles $src
            if (-not $exe) {
                throw "Compilation failed"
            }

            Write-Log "Applying binary patches with $($Script:Config.AudioGainMultiplier)x gain setting..." -Level Info
            $patchOut = Join-Path $Script:Config.TempDir "patcher_stdout.txt"
            $patchErr = Join-Path $Script:Config.TempDir "patcher_stderr.txt"
            $patchProc = Start-Process -FilePath $exe -ArgumentList @($voiceNodePath) -Wait -PassThru -NoNewWindow -RedirectStandardOutput $patchOut -RedirectStandardError $patchErr
            if ($patchProc.ExitCode -eq 0) {
                Write-Log "Successfully patched $clientName with $($Script:Config.AudioGainMultiplier)x gain!" -Level Success
                $successCount++
            } else {
                if (Test-Path $patchErr) { $errText = Get-Content $patchErr -Raw -ErrorAction SilentlyContinue; if ($errText) { Write-Log "Patcher stderr: $errText" -Level Error } }
                if (Test-Path $patchOut) { $outText = Get-Content $patchOut -Raw -ErrorAction SilentlyContinue; if ($outText) { Write-Log "Patcher stdout: $outText" -Level Error } }
                throw "Patcher exited with code $($patchProc.ExitCode)"
            }
        } catch {
            Write-Log "Failed to patch ${clientName}: $_" -Level Error
            [void]$failedClients.Add($clientName)
        }
    }

    Remove-PatcherTempFiles
    return @{ Success = $successCount; Failed = @($failedClients); Total = $Clients.Count }
}

# endregion Core Patching

# region Main Entry

function Start-Patching {
    Write-Banner
    if (-not $SkipUpdateCheck -and -not [string]::IsNullOrEmpty($PSCommandPath)) {
        $updateResult = Test-ScriptUpdateAvailable
        if ($updateResult.UpdateAvailable) {
            Write-Host ""
            Write-Host "Updating script from GitHub (v$($updateResult.LocalVersion) -> v$($updateResult.RemoteVersion))..." -ForegroundColor Yellow
            Write-Host ""
            Write-Log "Applying update from GitHub..." -Level Info
            if (Update-ScriptPatch -UpdatedScriptPath $updateResult.TempFile -CurrentScriptPath $PSCommandPath -RestartAfter) {
                Write-Log "Update applied; restarting with the same launch options..." -Level Success
                Start-Sleep -Seconds 2; exit 0
            } else {
                Write-Log "Failed to apply update. Continuing with current version..." -Level Warning
                if (Test-Path $updateResult.TempFile) { Remove-Item $updateResult.TempFile -Force -ErrorAction SilentlyContinue }
            }
            Write-Host ""
        }
    }

    if ($ListBackups) { Show-BackupList; return $true }
    if ($Restore) { return Restore-FromBackup }

    if ($FixAll -or $Script:DoFixAll -or $FixClient) {
        if ($null -ne $Script:PendingGainForPatchAll) {
            $Script:Config.AudioGainMultiplier = $Script:PendingGainForPatchAll
            $Script:PendingGainForPatchAll = $null
        }
        Show-Settings
        Initialize-Environment
        Write-Log "Scanning for installed Discord clients..." -Level Info
        $installedClients = @(Get-InstalledClients)
        if ($installedClients.Count -eq 0) {
            Write-Log "No Discord clients found! Make sure Discord is installed." -Level Error
            Wait-EnterOrTimeout
            return $false
        }

        if ($FixClient) {
            $installedClients = @($installedClients | Where-Object { $_.Name -like "*$FixClient*" })
            if ($installedClients.Count -eq 0) {
                Write-Log "No clients matching '$FixClient' found" -Level Error
                Wait-EnterOrTimeout
                return $false
            }
        }

        $uniqueClients = @(Get-UniqueClientsByAppPath -Clients $installedClients)
        Write-Log "Found $($uniqueClients.Count) client(s):" -Level Success
        foreach ($c in $uniqueClients) {
            $v = Get-DiscordAppVersion $c.AppPath
            Write-Log "  - $($c.Name.Trim()) (v$v)" -Level Info
        }

        $compiler = Find-Compiler
        if (-not $compiler) {
            Wait-EnterOrTimeout
            return $false
        }

        # PatchLocalOnly avoids downloading the repo "voice bundle" and patches the on-disk module in place.
        # This is the mode Stereo Hub uses when it detects a new Discord build and regenerates offsets locally.
        $voiceBackupPath = $null
        if (-not $PatchLocalOnly) {
            $voiceBackupPath = Get-PreparedVoiceBackupPath
            if (-not $voiceBackupPath) {
                Wait-EnterOrTimeout
                return $false
            }
        } else {
            Write-Log "Patch local only enabled: skipping GitHub voice module download." -Level Info
        }

        Write-Log "Closing all Discord processes..." -Level Info
        $stopped = Stop-AllDiscordProcesses
        if (-not $stopped) {
            Write-Log "Warning: Some processes may still be running" -Level Warning
            Start-Sleep -Seconds 2
        }

        Start-Sleep -Seconds 1
        if ($PatchLocalOnly) {
            $result = Invoke-PatchClients -Clients @($uniqueClients) -Compiler $compiler -VoiceBackupPath $null -PatchLocalOnly
        } else {
            $result = Invoke-PatchClients -Clients @($uniqueClients) -Compiler $compiler -VoiceBackupPath $voiceBackupPath
        }
        Write-Host ""
        Write-Log "=== PATCHING COMPLETE ===" -Level Success
        Write-Log "Success: $($result.Success) / $($result.Total)" -Level Info
        if ($result.Failed -and $result.Failed.Count -gt 0) {
            Write-Log "Failed: $($result.Failed -join ', ')" -Level Warning
        }

        if ($Script:Config.AutoRelaunch -and $uniqueClients.Count -gt 0) {
            Write-Log "Auto-relaunching Discord..." -Level Info
            Start-Sleep -Seconds 3
            $firstClient = $uniqueClients[0]
            $clientInfo = $Script:DiscordClients[$firstClient.Index]
            if ($clientInfo -and $clientInfo.Path -and (Test-Path $clientInfo.Path)) {
                $updateExe = Join-Path $clientInfo.Path "Update.exe"
                if (Test-Path $updateExe) {
                    Write-Log "Launching: $($clientInfo.Name.Trim())" -Level Info
                    $discordOut = Join-Path $env:TEMP "DiscordPatcher_discord_out.txt"
                    $discordErr = Join-Path $env:TEMP "DiscordPatcher_discord_err.txt"
                    try {
                        $p = Start-Process $updateExe -ArgumentList @("--processStart", $clientInfo.Exe) -WindowStyle Hidden -RedirectStandardOutput $discordOut -RedirectStandardError $discordErr -PassThru -ErrorAction Stop
                        Write-Log "Discord launch started (Update.exe PID=$($p.Id))." -Level Success
                    } catch {
                        Write-Log "Failed to launch via Update.exe: $($_.Exception.Message)" -Level Warning
                        try {
                            $exePath = Join-Path $firstClient.AppPath $clientInfo.Exe
                            if (Test-Path $exePath) {
                                $p2 = Start-Process $exePath -WindowStyle Hidden -RedirectStandardOutput $discordOut -RedirectStandardError $discordErr -PassThru -ErrorAction Stop
                                Write-Log "Discord launch started (direct exe PID=$($p2.Id))." -Level Success
                            } else {
                                Write-Log "Fallback exe not found: $exePath" -Level Warning
                            }
                        } catch {
                            Write-Log "Fallback launch failed: $($_.Exception.Message). See: $discordErr" -Level Warning
                        }
                    }
                }
            }
        } else {
            Write-Log "Auto-relaunch is disabled; Discord was not started automatically." -Level Info
        }
        Save-UserConfig
        Wait-EnterOrTimeout
        return ($result.Success -eq $result.Total)
    }

    Write-Log "Opening GUI..." -Level Info
    $guiResult = Show-ConfigurationGUI
    if (-not $guiResult) {
        Write-Log "Cancelled" -Level Warning
        return $false
    }
    Write-Log "GUI Action: $($guiResult.Action)" -Level Info
    if ($guiResult.Action -eq 'Restore') {
        return Restore-FromBackup
    }
    if ($guiResult.Action -notin @('Patch', 'PatchAll')) {
        Write-Log "Cancelled" -Level Warning
        return $false
    }

    $Script:Config.AudioGainMultiplier = $guiResult.Multiplier
    $Script:Config.SkipBackup = $guiResult.SkipBackup
    $Script:Config.AutoRelaunch = $guiResult.AutoRelaunch
    Write-Log "GUI Settings: Gain = $($Script:Config.AudioGainMultiplier)x, Skip Backup = $($Script:Config.SkipBackup), Auto Relaunch = $($Script:Config.AutoRelaunch)" -Level Info
    if ($guiResult.Action -eq 'PatchAll') {
        $Script:DoFixAll = $true
        $Script:PendingGainForPatchAll = $guiResult.Multiplier
        if ($guiResult.DebugMode -and $guiResult.SelectedPatches) {
            $Script:SelectedPatches = $guiResult.SelectedPatches
            Write-Log "Debug Mode: $(($guiResult.SelectedPatches.Values | Where-Object { $_ }).Count) / $($Script:AllPatchKeys.Count) patches selected" -Level Warning
        }
        return Start-Patching
    }

    Show-Settings
    Initialize-Environment
    if ($guiResult.DebugMode -and $guiResult.SelectedPatches) {
        $Script:SelectedPatches = $guiResult.SelectedPatches
        Write-Log "Debug Mode: $(($guiResult.SelectedPatches.Values | Where-Object { $_ }).Count) / $($Script:AllPatchKeys.Count) patches selected" -Level Warning
    }
    $selectedClientInfo = $Script:DiscordClients[$guiResult.ClientIndex]
    if (-not $selectedClientInfo) {
        Write-Log "Invalid client selection" -Level Error
        Wait-EnterOrTimeout
        return $false
    }

    Write-Log "Selected client: $($selectedClientInfo.Name.Trim())" -Level Info
    $installedClients = @(Get-InstalledClients)
    $targetClient = $installedClients | Where-Object { $_.Index -eq $guiResult.ClientIndex } | Select-Object -First 1
    if (-not $targetClient) {
        Write-Log "Selected client is not installed!" -Level Error
        Wait-EnterOrTimeout
        return $false
    }

    $compiler = Find-Compiler
    if (-not $compiler) {
        Wait-EnterOrTimeout
        return $false
    }

    $patchLocalOnly = $guiResult.PatchLocalOnly -eq $true
    $voiceBackupPath = $null
    if (-not $patchLocalOnly) {
        $voiceBackupPath = Get-PreparedVoiceBackupPath
        if (-not $voiceBackupPath) {
            Wait-EnterOrTimeout
            return $false
        }
    }

    Write-Log "Closing Discord processes..." -Level Info
    $installPath = $null
    if ($targetClient.AppPath -and (Test-Path $targetClient.AppPath)) {
        $installPath = (Get-Item (Split-Path $targetClient.AppPath -Parent)).FullName
    }
    if (-not $installPath -and $targetClient.Path -and (Test-Path $targetClient.Path)) {
        $installPath = (Get-Item $targetClient.Path).FullName
    }
    if (-not $installPath -and $selectedClientInfo.Path -and (Test-Path $selectedClientInfo.Path)) {
        $installPath = (Get-Item $selectedClientInfo.Path).FullName
    }
    if ($installPath) {
        $stopped = Stop-DiscordProcesses -ProcessNames $selectedClientInfo.Processes -InstallPath $installPath
    } else {
        $stopped = Stop-DiscordProcesses -ProcessNames $selectedClientInfo.Processes
    }
    if (-not $stopped) {
        Write-Log "Warning: Some processes may still be running" -Level Warning
        Start-Sleep -Seconds 2
    }

    Start-Sleep -Seconds 1
    if ($patchLocalOnly) {
        $result = Invoke-PatchClients -Clients @($targetClient) -Compiler $compiler -VoiceBackupPath $null -PatchLocalOnly
    } else {
        $result = Invoke-PatchClients -Clients @($targetClient) -Compiler $compiler -VoiceBackupPath $voiceBackupPath
    }
    Write-Host ""
    if ($result.Success -gt 0) {
        Write-Log "=== PATCHING COMPLETE ===" -Level Success
        if ($Script:Config.AutoRelaunch) {
            Write-Log "Auto-relaunching Discord..." -Level Info
            Start-Sleep -Seconds 2
            $discordPath = $targetClient.Path
            if (-not $discordPath) { $discordPath = $selectedClientInfo.Path }
            if ($discordPath -and (Test-Path $discordPath)) {
                $updateExe = Join-Path $discordPath "Update.exe"
                $discordOut = Join-Path $env:TEMP "DiscordPatcher_discord_out.txt"
                $discordErr = Join-Path $env:TEMP "DiscordPatcher_discord_err.txt"
                if (Test-Path $updateExe) {
                    Write-Log "Launching via Update.exe..." -Level Info
                    try {
                        $p = Start-Process $updateExe -ArgumentList @("--processStart", $selectedClientInfo.Exe) -WindowStyle Hidden -RedirectStandardOutput $discordOut -RedirectStandardError $discordErr -PassThru -ErrorAction Stop
                        Write-Log "Discord launch started (Update.exe PID=$($p.Id))." -Level Success
                    } catch {
                        Write-Log "Failed to launch via Update.exe: $($_.Exception.Message)" -Level Warning
                    }
                } else {
                    $appFolder = Get-ChildItem $discordPath -Directory -Filter "app-*" -ErrorAction SilentlyContinue | Sort-Object { try { if ($_.Name -match "app-\s*([\d\.]+)") { [Version]$matches[1].Trim() } else { [Version]"0.0.0" } } catch { [Version]"0.0.0" } } -Descending | Select-Object -First 1
                    if ($appFolder) {
                        $exePath = Join-Path $appFolder.FullName $selectedClientInfo.Exe
                        if (Test-Path $exePath) {
                            Write-Log "Launching: $exePath" -Level Info
                            try {
                                $p = Start-Process $exePath -WindowStyle Hidden -RedirectStandardOutput $discordOut -RedirectStandardError $discordErr -PassThru -ErrorAction Stop
                                Write-Log "Discord launch started (PID=$($p.Id))." -Level Success
                            } catch {
                                Write-Log "Failed to launch Discord: $($_.Exception.Message). See: $discordErr" -Level Warning
                            }
                        }
                    }
                }
            }
        } else {
            Write-Log "Auto-relaunch is disabled; Discord was not started automatically." -Level Info
        }
    } else {
        Write-Log "=== PATCHING FAILED ===" -Level Error
    }
    Save-UserConfig
    Wait-EnterOrTimeout
    return ($result.Success -gt 0)
}

# endregion Main Entry

# region Run

try {
    $success = Start-Patching
    Write-Host "`n$(if ($success) { 'SUCCESS!' } else { 'FAILED/CANCELLED' })" -ForegroundColor $(if ($success) { 'Green' } else { 'Red' })
    exit $(if ($success) { 0 } else { 1 })
} catch {
    Write-Host "`nFATAL ERROR: $_" -ForegroundColor Red
    Write-Host $_.ScriptStackTrace -ForegroundColor Red
    Wait-EnterOrTimeout; exit 1
}

# endregion Run
