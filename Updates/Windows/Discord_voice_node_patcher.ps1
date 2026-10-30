#Requires -Version 5.1
[CmdletBinding()]
param(
    [ValidateRange(1, 10)][int]$AudioGainMultiplier = 1,
    [switch]$SkipBackup,
    [switch]$Restore,
    [switch]$ListBackups,
    [switch]$FixAll,
    [string]$FixClient,
    [switch]$PatchLocalOnly,
    [switch]$SkipUpdateCheck,
    [string]$NodePath,
    [string]$OutputPath,
    [switch]$DryRun,
    [switch]$NonInteractive
)

$ErrorActionPreference = "Stop"
$ProgressPreference = 'SilentlyContinue'

Add-Type -AssemblyName System.Windows.Forms, System.Drawing -ErrorAction SilentlyContinue

$Script:SCRIPT_VERSION = "24.3.1"

$Script:ProfileContract = 'discord-voice-patcher-profile-v10'

# region Offsets (PASTE HERE)
# Verified build bank for patcher v24.1+. Automatic updates preserve other builds.
$Script:VoiceProfileBank = @'
{
  "schema": "discord-voice-profile-bank-v1",
  "profiles": [
    {
      "plan_sha256": "b228a262ce10cee9041bda214265332a1d4efa4f659ef3cc0d88f98866667599",
      "manifest": {
        "schema": "discord-voice-patch-manifest-v6",
        "version": "7.3.0",
        "profile": "discord-windows-x64-sha256-3326b8582f4b38be",
        "file_size": 22394296,
        "original_sha256": "3326b8582f4b38be3b63c05161476efd381062f9b0185d1d4bbf86b0baa024bb",
        "original_md5": "0ebc96a7f0dde80d1866d4cf61eb49cd",
        "target_bitrate_bps": 320000,
        "bitrate_mode": "cbr",
        "complete": true,
        "total_expected": 20,
        "missing": [],
        "source_builds": [
          {
            "app_version": "1.0.9266",
            "channel": "Stable"
          }
        ],
        "discord_app_version": "1.0.9266",
        "patches": [
          {
            "name": "CreateAudioFrame_ChannelAssign_Mov",
            "group": "STEREO",
            "rva": "0x13d670",
            "file_offset": 1297008,
            "length": 4,
            "expected_original": "4C 0F 43 E9",
            "patch": "49 89 CD 90",
            "optional": false
          },
          {
            "name": "CapturedAudioProcessor_APMBypass_NopJmp",
            "group": "FILTER",
            "rva": "0xf0ec0",
            "file_offset": 983744,
            "length": 13,
            "expected_original": "84 C0 74 0D 83 BE 80 02 00 00 09 0F 8F",
            "patch": "90 90 90 90 90 90 90 90 90 90 90 90 E9",
            "optional": false
          },
          {
            "name": "CommitAudioCodec_ChannelCount_Imm02",
            "group": "STEREO",
            "rva": "0x67b007",
            "file_offset": 6792199,
            "length": 1,
            "expected_original": "01",
            "patch": "02",
            "optional": false
          },
          {
            "name": "OpusSdp_StereoValueBypass_Jmp2",
            "group": "STEREO",
            "rva": "0x67b036",
            "file_offset": 6792246,
            "length": 2,
            "expected_original": "31 ED",
            "patch": "EB 09",
            "optional": false
          },
          {
            "name": "ApplySettings_BitrateBase_Mov248k",
            "group": "BITRATE",
            "rva": "0x67b43a",
            "file_offset": 6793274,
            "length": 6,
            "expected_original": "41 BE E0 2E 00 00",
            "patch": "41 BE 00 E2 04 00",
            "optional": false,
            "accepted_legacy": [
              "41 BE C0 C8 03 00",
              "41 BE 00 E2 04 00"
            ]
          },
          {
            "name": "ApplySettings_BitrateSelect_Nop4",
            "group": "BITRATE",
            "rva": "0x67b440",
            "file_offset": 6793280,
            "length": 4,
            "expected_original": "44 0F 43 F1",
            "patch": "90 90 90 90",
            "optional": false
          },
          {
            "name": "ApplySettings_BitrateChannels_Nop4",
            "group": "BITRATE",
            "rva": "0x67b444",
            "file_offset": 6793284,
            "length": 4,
            "expected_original": "44 0F AF F5",
            "patch": "90 90 90 90",
            "optional": false
          },
          {
            "name": "ApplySettings_MaxAvgBitrateClamp248k_Mov",
            "group": "BITRATE",
            "rva": "0x67b522",
            "file_offset": 6793506,
            "length": 5,
            "expected_original": "B8 30 C8 07 00",
            "patch": "B8 00 E2 04 00",
            "optional": false,
            "accepted_legacy": [
              "B8 C0 C8 03 00",
              "B8 00 E2 04 00"
            ]
          },
          {
            "name": "SetTargetBitrate_ClampMax248k_Mov",
            "group": "BITRATE",
            "rva": "0x67d537",
            "file_offset": 6801719,
            "length": 5,
            "expected_original": "BF 30 C8 07 00",
            "patch": "BF 00 E2 04 00",
            "optional": false,
            "accepted_legacy": [
              "BF C0 C8 03 00",
              "BF 00 E2 04 00"
            ]
          },
          {
            "name": "SetTargetBitrate_Mulss_Nop6",
            "group": "BITRATE",
            "rva": "0x67d59e",
            "file_offset": 6801822,
            "length": 6,
            "expected_original": "F3 0F 59 44 81 EC",
            "patch": "90 90 90 90 90 90",
            "optional": false
          },
          {
            "name": "OpusSdp_MaxPlaybackRate_Keep48k_Nop4",
            "group": "BANDWIDTH",
            "rva": "0x67b16e",
            "file_offset": 6792558,
            "length": 4,
            "expected_original": "44 0F 42 F0",
            "patch": "90 90 90 90",
            "optional": false
          },
          {
            "name": "HighPassFilter_Process_Entry_Ret",
            "group": "FILTER",
            "rva": "0x687680",
            "file_offset": 6843008,
            "length": 1,
            "expected_original": "41",
            "patch": "C3",
            "optional": false
          },
          {
            "name": "CELT_Force",
            "group": "CELT",
            "rva": "0xaa25e8",
            "file_offset": 11147752,
            "length": 4,
            "expected_original": "18 FC FF FF",
            "patch": "EA 03 00 00",
            "optional": false
          },
          {
            "name": "CELT_DefaultMode",
            "group": "CELT",
            "rva": "0xaa2664",
            "file_offset": 11147876,
            "length": 4,
            "expected_original": "E9 03 00 00",
            "patch": "EA 03 00 00",
            "optional": false
          },
          {
            "name": "SetTargetBitrate_ClampSelect_Nop3",
            "group": "BITRATE",
            "rva": "0x67d53c",
            "file_offset": 6801724,
            "length": 3,
            "expected_original": "0F 4C F9",
            "patch": "90 90 90",
            "optional": false
          },
          {
            "name": "ApplySettings_MaxAvgBitrateSelect_Nop4",
            "group": "BITRATE",
            "rva": "0x67b527",
            "file_offset": 6793511,
            "length": 4,
            "expected_original": "48 0F 4C C3",
            "patch": "90 90 90 90",
            "optional": false
          },
          {
            "name": "OpusEncodeNative_AnalysisGate_Jmp",
            "group": "FILTER",
            "rva": "0xaa3169",
            "file_offset": 11150697,
            "length": 1,
            "expected_original": "7C",
            "patch": "EB",
            "optional": false
          },
          {
            "name": "OpusEncodeFrame_FilterBypass_CopyGain",
            "group": "FILTER",
            "rva": "0xaa5039",
            "file_offset": 11158585,
            "length": 80,
            "expected_original": "0F 85 A1 01 00 00 98 69 C0 A7 09 00 00 49 63 D0 4C 69 C2 D3 4D 62 10 4C 89 C2 48 C1 EA 3F 49 C1 E8 20 41 C1 F8 06 41 01 D0 99 41 F7 F8 45 85 F6 0F 8E 9A 02 00 00 69 D0 29 FE FF FF 81 C2 00 00 00 10 F3 0F 2A C2 44 69 C0 AE 03 00 00 C1 FA 06",
            "patch": "45 89 C8 45 0F AF C6 45 85 C0 0F 8E C0 02 00 00 B8 00 00 80 3F 66 0F 6E C8 31 D2 F3 41 0F 10 04 97 F3 0F 59 C1 F3 0F 11 04 91 48 FF C2 4C 39 C2 72 E9 E9 99 02 00 00 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90",
            "optional": false,
            "kind": "copy_gain",
            "accepted_legacy": [
              "45 89 C8 45 0F AF C6 45 85 C0 0F 8E C0 02 00 00 B8 00 00 80 3F 66 0F 6E C8 31 D2 F3 41 0F 10 04 97 F3 0F 59 C1 F3 0F 11 04 91 48 FF C2 4C 39 C2 72 E9 E9 99 02 00 00 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90",
              "45 89 C8 45 0F AF C6 45 85 C0 0F 8E C0 02 00 00 0F 57 C9 F3 41 0F 2A C9 F3 0F 52 C9 F3 0F 58 C9 31 D2 F3 41 0F 10 04 97 F3 0F 59 C1 F3 0F 11 04 91 48 FF C2 4C 39 C2 72 E9 E9 92 02 00 00 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90",
              "45 89 C8 45 0F AF C6 45 85 C0 0F 8E C0 02 00 00 B8 01 00 00 00 44 01 C8 0F 57 C9 F3 0F 2A C8 31 D2 F3 41 0F 10 04 97 F3 0F 59 C1 F3 0F 11 04 91 48 FF C2 4C 39 C2 72 E9 E9 93 02 00 00 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90",
              "45 89 C8 45 0F AF C6 45 85 C0 0F 8E C0 02 00 00 B8 02 00 00 00 44 01 C8 0F 57 C9 F3 0F 2A C8 31 D2 F3 41 0F 10 04 97 F3 0F 59 C1 F3 0F 11 04 91 48 FF C2 4C 39 C2 72 E9 E9 93 02 00 00 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90",
              "45 89 C8 45 0F AF C6 45 85 C0 0F 8E C0 02 00 00 B8 03 00 00 00 44 01 C8 0F 57 C9 F3 0F 2A C8 31 D2 F3 41 0F 10 04 97 F3 0F 59 C1 F3 0F 11 04 91 48 FF C2 4C 39 C2 72 E9 E9 93 02 00 00 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90",
              "45 89 C8 45 0F AF C6 45 85 C0 0F 8E C0 02 00 00 B8 04 00 00 00 44 01 C8 0F 57 C9 F3 0F 2A C8 31 D2 F3 41 0F 10 04 97 F3 0F 59 C1 F3 0F 11 04 91 48 FF C2 4C 39 C2 72 E9 E9 93 02 00 00 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90",
              "45 89 C8 45 0F AF C6 45 85 C0 0F 8E C0 02 00 00 B8 05 00 00 00 44 01 C8 0F 57 C9 F3 0F 2A C8 31 D2 F3 41 0F 10 04 97 F3 0F 59 C1 F3 0F 11 04 91 48 FF C2 4C 39 C2 72 E9 E9 93 02 00 00 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90",
              "45 89 C8 45 0F AF C6 45 85 C0 0F 8E C0 02 00 00 B8 06 00 00 00 44 01 C8 0F 57 C9 F3 0F 2A C8 31 D2 F3 41 0F 10 04 97 F3 0F 59 C1 F3 0F 11 04 91 48 FF C2 4C 39 C2 72 E9 E9 93 02 00 00 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90",
              "45 89 C8 45 0F AF C6 45 85 C0 0F 8E C0 02 00 00 B8 07 00 00 00 44 01 C8 0F 57 C9 F3 0F 2A C8 31 D2 F3 41 0F 10 04 97 F3 0F 59 C1 F3 0F 11 04 91 48 FF C2 4C 39 C2 72 E9 E9 93 02 00 00 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90",
              "45 89 C8 45 0F AF C6 45 85 C0 0F 8E C0 02 00 00 B8 08 00 00 00 44 01 C8 0F 57 C9 F3 0F 2A C8 31 D2 F3 41 0F 10 04 97 F3 0F 59 C1 F3 0F 11 04 91 48 FF C2 4C 39 C2 72 E9 E9 93 02 00 00 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90"
            ],
            "gain_patches": {
              "1": "45 89 C8 45 0F AF C6 45 85 C0 0F 8E C0 02 00 00 B8 00 00 80 3F 66 0F 6E C8 31 D2 F3 41 0F 10 04 97 F3 0F 59 C1 F3 0F 11 04 91 48 FF C2 4C 39 C2 72 E9 E9 99 02 00 00 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90",
              "2": "45 89 C8 45 0F AF C6 45 85 C0 0F 8E C0 02 00 00 B8 00 00 00 40 66 0F 6E C8 31 D2 F3 41 0F 10 04 97 F3 0F 59 C1 F3 0F 11 04 91 48 FF C2 4C 39 C2 72 E9 E9 99 02 00 00 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90",
              "3": "45 89 C8 45 0F AF C6 45 85 C0 0F 8E C0 02 00 00 B8 00 00 40 40 66 0F 6E C8 31 D2 F3 41 0F 10 04 97 F3 0F 59 C1 F3 0F 11 04 91 48 FF C2 4C 39 C2 72 E9 E9 99 02 00 00 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90",
              "4": "45 89 C8 45 0F AF C6 45 85 C0 0F 8E C0 02 00 00 B8 00 00 80 40 66 0F 6E C8 31 D2 F3 41 0F 10 04 97 F3 0F 59 C1 F3 0F 11 04 91 48 FF C2 4C 39 C2 72 E9 E9 99 02 00 00 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90",
              "5": "45 89 C8 45 0F AF C6 45 85 C0 0F 8E C0 02 00 00 B8 00 00 A0 40 66 0F 6E C8 31 D2 F3 41 0F 10 04 97 F3 0F 59 C1 F3 0F 11 04 91 48 FF C2 4C 39 C2 72 E9 E9 99 02 00 00 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90",
              "6": "45 89 C8 45 0F AF C6 45 85 C0 0F 8E C0 02 00 00 B8 00 00 C0 40 66 0F 6E C8 31 D2 F3 41 0F 10 04 97 F3 0F 59 C1 F3 0F 11 04 91 48 FF C2 4C 39 C2 72 E9 E9 99 02 00 00 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90",
              "7": "45 89 C8 45 0F AF C6 45 85 C0 0F 8E C0 02 00 00 B8 00 00 E0 40 66 0F 6E C8 31 D2 F3 41 0F 10 04 97 F3 0F 59 C1 F3 0F 11 04 91 48 FF C2 4C 39 C2 72 E9 E9 99 02 00 00 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90",
              "8": "45 89 C8 45 0F AF C6 45 85 C0 0F 8E C0 02 00 00 B8 00 00 00 41 66 0F 6E C8 31 D2 F3 41 0F 10 04 97 F3 0F 59 C1 F3 0F 11 04 91 48 FF C2 4C 39 C2 72 E9 E9 99 02 00 00 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90",
              "9": "45 89 C8 45 0F AF C6 45 85 C0 0F 8E C0 02 00 00 B8 00 00 10 41 66 0F 6E C8 31 D2 F3 41 0F 10 04 97 F3 0F 59 C1 F3 0F 11 04 91 48 FF C2 4C 39 C2 72 E9 E9 99 02 00 00 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90",
              "10": "45 89 C8 45 0F AF C6 45 85 C0 0F 8E C0 02 00 00 B8 00 00 20 41 66 0F 6E C8 31 D2 F3 41 0F 10 04 97 F3 0F 59 C1 F3 0F 11 04 91 48 FF C2 4C 39 C2 72 E9 E9 99 02 00 00 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90"
            },
            "legacy_gain_patches": {
              "1": "45 89 C8 45 0F AF C6 45 85 C0 0F 8E C0 02 00 00 B8 00 00 80 3F 66 0F 6E C8 31 D2 F3 41 0F 10 04 97 F3 0F 59 C1 F3 0F 11 04 91 48 FF C2 4C 39 C2 72 E9 E9 99 02 00 00 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90",
              "2": "45 89 C8 45 0F AF C6 45 85 C0 0F 8E C0 02 00 00 0F 57 C9 F3 41 0F 2A C9 F3 0F 52 C9 F3 0F 58 C9 31 D2 F3 41 0F 10 04 97 F3 0F 59 C1 F3 0F 11 04 91 48 FF C2 4C 39 C2 72 E9 E9 92 02 00 00 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90",
              "3": "45 89 C8 45 0F AF C6 45 85 C0 0F 8E C0 02 00 00 B8 01 00 00 00 44 01 C8 0F 57 C9 F3 0F 2A C8 31 D2 F3 41 0F 10 04 97 F3 0F 59 C1 F3 0F 11 04 91 48 FF C2 4C 39 C2 72 E9 E9 93 02 00 00 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90",
              "4": "45 89 C8 45 0F AF C6 45 85 C0 0F 8E C0 02 00 00 B8 02 00 00 00 44 01 C8 0F 57 C9 F3 0F 2A C8 31 D2 F3 41 0F 10 04 97 F3 0F 59 C1 F3 0F 11 04 91 48 FF C2 4C 39 C2 72 E9 E9 93 02 00 00 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90",
              "5": "45 89 C8 45 0F AF C6 45 85 C0 0F 8E C0 02 00 00 B8 03 00 00 00 44 01 C8 0F 57 C9 F3 0F 2A C8 31 D2 F3 41 0F 10 04 97 F3 0F 59 C1 F3 0F 11 04 91 48 FF C2 4C 39 C2 72 E9 E9 93 02 00 00 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90",
              "6": "45 89 C8 45 0F AF C6 45 85 C0 0F 8E C0 02 00 00 B8 04 00 00 00 44 01 C8 0F 57 C9 F3 0F 2A C8 31 D2 F3 41 0F 10 04 97 F3 0F 59 C1 F3 0F 11 04 91 48 FF C2 4C 39 C2 72 E9 E9 93 02 00 00 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90",
              "7": "45 89 C8 45 0F AF C6 45 85 C0 0F 8E C0 02 00 00 B8 05 00 00 00 44 01 C8 0F 57 C9 F3 0F 2A C8 31 D2 F3 41 0F 10 04 97 F3 0F 59 C1 F3 0F 11 04 91 48 FF C2 4C 39 C2 72 E9 E9 93 02 00 00 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90",
              "8": "45 89 C8 45 0F AF C6 45 85 C0 0F 8E C0 02 00 00 B8 06 00 00 00 44 01 C8 0F 57 C9 F3 0F 2A C8 31 D2 F3 41 0F 10 04 97 F3 0F 59 C1 F3 0F 11 04 91 48 FF C2 4C 39 C2 72 E9 E9 93 02 00 00 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90",
              "9": "45 89 C8 45 0F AF C6 45 85 C0 0F 8E C0 02 00 00 B8 07 00 00 00 44 01 C8 0F 57 C9 F3 0F 2A C8 31 D2 F3 41 0F 10 04 97 F3 0F 59 C1 F3 0F 11 04 91 48 FF C2 4C 39 C2 72 E9 E9 93 02 00 00 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90",
              "10": "45 89 C8 45 0F AF C6 45 85 C0 0F 8E C0 02 00 00 B8 08 00 00 00 44 01 C8 0F 57 C9 F3 0F 2A C8 31 D2 F3 41 0F 10 04 97 F3 0F 59 C1 F3 0F 11 04 91 48 FF C2 4C 39 C2 72 E9 E9 93 02 00 00 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90"
            }
          },
          {
            "name": "OpusEncoder_Init_ForceCBR",
            "group": "BITRATE",
            "rva": "0xaa259f",
            "file_offset": 11147679,
            "length": 10,
            "expected_original": "48 B8 01 00 00 00 01 00 00 00",
            "patch": "48 B8 00 00 00 00 01 00 00 00",
            "optional": false
          },
          {
            "name": "OpusEncoder_SetVBR_ForceCBR",
            "group": "BITRATE",
            "rva": "0xaa7db7",
            "file_offset": 11170231,
            "length": 13,
            "expected_original": "89 86 98 00 00 00 B9 01 00 00 00 29 C1",
            "patch": "31 C0 89 86 98 00 00 00 B9 01 00 00 00",
            "optional": false
          }
        ]
      }
    }
  ]
}
'@ | ConvertFrom-Json
# endregion Offsets

# The first entry supplies common UI settings; each node selects its own profile.
$Script:VoicePatchManifest = $Script:VoiceProfileBank.profiles[0].manifest
$Script:ExpectedPatchSiteCount = [int]$Script:VoicePatchManifest.total_expected
$Script:AuditedPatchPlanHash = $Script:VoiceProfileBank.profiles[0].plan_sha256

$Script:OffsetsMeta = @{
    FinderVersion = $Script:VoicePatchManifest.version
    DiscordAppVersion = $Script:VoicePatchManifest.discord_app_version
    Size = $Script:VoicePatchManifest.file_size
    MD5 = $Script:VoicePatchManifest.original_md5
}
$Script:Offsets = @{}
$Script:PatchGroups = [ordered]@{}
foreach ($groupName in @('STEREO','BITRATE','BANDWIDTH','FILTER','CELT')) {
    $Script:PatchGroups[$groupName] = [ordered]@{}
}
$Script:RateModeLabel = if($Script:VoicePatchManifest.bitrate_mode -eq 'cbr') {'CBR'} else {'Auto'}
$Script:PatchLabels = @{
    'OpusEncoder_Init_ForceCBR' = 'Opus encoder | Initialize CBR'
    'OpusEncoder_SetVBR_ForceCBR' = 'Opus encoder | Keep CBR enabled'

    'CreateAudioFrame_ChannelAssign_Mov' = 'CreateAudioFrame | Channel assignment | RCX'
    'CapturedAudioProcessor_APMBypass_NopJmp' = 'Captured audio | Bypass APM processing (Krisp separate)'
    'CommitAudioCodec_ChannelCount_Imm02' = 'Opus SDP | Default channel count: 2'
    'OpusSdp_StereoValueBypass_Jmp2' = 'Opus SDP | Force stereo, preserve string cleanup'
    'ApplySettings_BitrateBase_Mov248k' = 'ApplySettings | Flat bitrate | 248k'
    'ApplySettings_BitrateSelect_Nop4' = 'ApplySettings | Rate tier selection | bypass'
    'ApplySettings_BitrateChannels_Nop4' = 'ApplySettings | Channel scaling | bypass'
    'ApplySettings_MaxAvgBitrateClamp248k_Mov' = 'ApplySettings | MaxAvgClamp | mov 248k'
    'SetTargetBitrate_ClampMax248k_Mov' = 'SetTargetBitrate | ClampMax | mov 248k'
    'SetTargetBitrate_Mulss_Nop6' = 'SetTargetBitrate | MulssScale | nop x6'
    'OpusSdp_MaxPlaybackRate_Keep48k_Nop4' = 'Opus SDP | Max playback rate: 48 kHz (full-band)'
    'HighPassFilter_Process_Entry_Ret' = 'HighPassFilter | Process | bypass'
    'CELT_Force' = 'opus_encoder_init | user_forced_mode -1000->1002 (CELT_ONLY)'
    'CELT_DefaultMode' = 'opus_encoder_init | default st->mode 1001->1002 (CELT_ONLY)'
    'SetTargetBitrate_ClampSelect_Nop3' = 'SetTargetBitrate | Lower-rate selection | bypass'
    'ApplySettings_MaxAvgBitrateSelect_Nop4' = 'ApplySettings | Lower-rate selection | bypass'
    'OpusEncodeNative_AnalysisGate_Jmp' = 'Opus analysis | Low-complexity path | bypass'
    'OpusEncodeFrame_FilterBypass_CopyGain' = 'Opus frame | Filter bypass + copy/gain loop'
}
foreach ($key in @($Script:PatchLabels.Keys)) {
    $Script:PatchLabels[$key]=$Script:PatchLabels[$key].Replace('248k',([string][int]($Script:VoicePatchManifest.target_bitrate_bps / 1000)+'k'))
}
$Script:AllPatchKeys = [System.Collections.Generic.List[string]]::new()
$Script:SelectedPatches = @{}
foreach ($site in $Script:VoicePatchManifest.patches) {
    $key = [string]$site.name
    $Script:Offsets[$key] = [Convert]::ToInt64($site.rva,16)
    $Script:SelectedPatches[$key] = -not $site.optional
    if (-not $Script:PatchGroups.Contains($site.group)) { $Script:PatchGroups[$site.group] = [ordered]@{} }
    $displayHex = if ($site.kind -eq 'copy_gain') { 'Copy/gain loop (80 bytes; follows gain slider)' } else { $site.patch }
    $Script:PatchGroups[$site.group][$key] = @{ Name = $(if ($Script:PatchLabels.ContainsKey($key)) { $Script:PatchLabels[$key] } else { $key -replace '_',' ' }); Hex = $displayHex }
    $Script:AllPatchKeys.Add($key)
    $Script:SelectedPatches[$key] = -not $site.optional
}
$Script:RequiredOffsetNames = @($Script:VoicePatchManifest.patches | ForEach-Object {$_.name})
$Script:DebugModeActive = $false

function Set-PatchSelection {
    param([bool]$DebugMode=$false,[hashtable]$Selection)
    $Script:DebugModeActive=$DebugMode
    foreach($site in $Script:VoicePatchManifest.patches) {
        $key=[string]$site.name
        if($DebugMode) {$Script:SelectedPatches[$key]=($null -ne $Selection -and $Selection.ContainsKey($key) -and [bool]$Selection[$key])}
        else {$Script:SelectedPatches[$key]=-not $site.optional}
    }
    if($null -ne $Script:Config) {$Script:Config.Bitrate=[int]($Script:VoicePatchManifest.target_bitrate_bps/1000)}
}

function Get-EnabledPatchCount {
    @($Script:AllPatchKeys | Where-Object {$Script:SelectedPatches[$_]}).Count
}

function Write-DebugPatchSelectionLog {
    Write-Log ("Debug: {0}/{1} active patches selected; unchecked sites use stock bytes." -f (Get-EnabledPatchCount),$Script:AllPatchKeys.Count) -Level Info
}


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



$Script:IsElevated = $false
try {
    $principal = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
    $Script:IsElevated = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
} catch { }

$Script:GainExplicitlySet = $PSBoundParameters.ContainsKey('AudioGainMultiplier')
$Script:Config = @{
    SampleRate = 48000; Bitrate = [int]($Script:VoicePatchManifest.target_bitrate_bps / 1000); Channels = "Stereo"
    AudioGainMultiplier = $AudioGainMultiplier; SkipBackup = $SkipBackup.IsPresent; AutoRelaunch = $true
    ModuleName = "discord_voice.node"
    TempDir = "$env:TEMP\DiscordVoicePatcher"; BackupDir = "$env:TEMP\DiscordVoicePatcher\Backups"
    LogFile = "$env:TEMP\DiscordVoicePatcher\patcher.log"; ConfigFile = "$env:TEMP\DiscordVoicePatcher\config.json"
    FileLockWaitSeconds = 5
    MaxBackupsPerClient = 3
    MaxBackupAgeDays      = 45
    VoiceRepository = 'ProdHallow/Discord-Stereo-Windows-MacOS-Linux'
    VoiceRepositoryRef = 'main'
    VoiceRepositoryPath = 'Updates/Nodes/Unpatched Nodes (For Patcher)/Windows'
    OffsetsMeta = $Script:OffsetsMeta
    Offsets     = $Script:Offsets
}
Set-PatchSelection
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


function Get-FileMd5Hex {
    param([Parameter(Mandatory)][string]$Path)
    try {
        if (Get-Command Get-FileHash -ErrorAction SilentlyContinue) {
            return (Get-FileHash -LiteralPath $Path -Algorithm MD5).Hash.ToLowerInvariant()
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

function Write-Log {
    param([Parameter(Mandatory)][AllowEmptyString()][AllowNull()][string]$Message, [ValidateSet('Info','Success','Warning','Error')][string]$Level = 'Info')
    if ([string]::IsNullOrEmpty($Message)) { Write-Host ""; return }
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    if ($Script:Config.LogFile) { [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($Script:Config.LogFile)); Add-Content -LiteralPath $Script:Config.LogFile -Value "[$timestamp] [$Level] $Message" -ErrorAction SilentlyContinue }
    $colors = @{ Success = 'Green'; Warning = 'Yellow'; Error = 'Red'; Info = 'White' }
    $prefixes = @{ Success = '[OK]'; Warning = '[!!]'; Error = '[XX]'; Info = '[--]' }
    Write-Host "$($prefixes[$Level]) $Message" -ForegroundColor $colors[$Level]
}

function Write-Banner {
    Write-Host "`n===== Discord Voice Quality Patcher v$Script:SCRIPT_VERSION =====" -ForegroundColor Cyan
    Write-Host "      48kHz | $($Script:Config.Bitrate)kbps $Script:RateModeLabel | Stereo | Gain Config" -ForegroundColor Cyan
    Write-Host "      Stable module from GitHub | All Discord clients" -ForegroundColor Cyan
    Write-Host " Built-in verified patch engine | No compiler required" -ForegroundColor Yellow
    Write-Host "===============================================`n" -ForegroundColor Cyan
}

function Show-Settings {
    $gainColor = if ($Script:Config.AudioGainMultiplier -le 2) { 'Green' } elseif ($Script:Config.AudioGainMultiplier -le 5) { 'Yellow' } else { 'Red' }
    Write-Host "Profile: $($Script:Config.SampleRate)Hz, $($Script:Config.Bitrate)kbps $Script:RateModeLabel, $($Script:Config.Channels), " -NoNewline
    Write-Host "level $($Script:Config.AudioGainMultiplier)" -ForegroundColor $gainColor
    Write-Host ""
}



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
        if (Test-Path -LiteralPath $Script:Config.ConfigFile) {
            $content = Get-Content -LiteralPath $Script:Config.ConfigFile -Raw
            if ([string]::IsNullOrWhiteSpace($content)) { throw "Empty" }
            $cfg = $content | ConvertFrom-Json
            if (-not $cfg.PSObject.Properties['LastGainMultiplier']) { throw "Invalid" }
            if ($null -eq $cfg.LastGainMultiplier -or ($cfg.LastGainMultiplier -is [string] -and [string]::IsNullOrWhiteSpace($cfg.LastGainMultiplier))) { throw "Invalid" }
            $num = $cfg.LastGainMultiplier
            if ($num -lt 1 -or $num -gt 10) { throw "OutOfRange" }
            return $cfg
        }
    } catch { Remove-Item -LiteralPath $Script:Config.ConfigFile -Force -ErrorAction SilentlyContinue }
    return $null
}

function EnsureDir($p) { if ($p -and -not (Test-Path -LiteralPath $p)) { try { [void](New-Item $p -ItemType Directory -Force) } catch { } } }

function Get-OffsetsCopyBlock {
    $lines = [System.Collections.Generic.List[string]]::new()
    $lines.Add('# region Offsets (PASTE HERE)')
    $lines.Add('# Verified build bank for patcher v24.1+. Automatic updates preserve other builds.')
    $lines.Add("`$Script:VoiceProfileBank = @'")
    $lines.Add(($Script:VoiceProfileBank | ConvertTo-Json -Depth 30))
    $lines.Add("'@ | ConvertFrom-Json")
    $lines.Add('# endregion Offsets')
    return $lines -join "`n"
}

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
    if (!(Test-Path -LiteralPath $sm)) { return $null }
    $scs = @(Get-ChildItem -LiteralPath $sm -Filter "$ShortcutName.lnk" -Recurse -ErrorAction SilentlyContinue)
    if ($scs.Count -eq 0) { return $null }
    $ws = $null
    try {
        $ws = New-Object -ComObject WScript.Shell
        foreach ($lf in $scs) {
            try {
                $sc = $ws.CreateShortcut($lf.FullName)
                try {
                    if ($sc.TargetPath -and (Test-Path -LiteralPath $sc.TargetPath)) { return (Split-Path $sc.TargetPath -Parent) }
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
    if (-not $BasePath -or -not (Test-Path -LiteralPath $BasePath)) {
        if ($ReturnDiagnostics) { return @{ Error = "InvalidBasePath" } }
        return $null
    }
    $af = @(Get-ChildItem -LiteralPath $BasePath -Filter "app-*" -Directory -ErrorAction SilentlyContinue |
        Sort-Object { try { if ($_.Name -match "app-\s*([\d\.]+)") { [Version]$matches[1].Trim() } else { [Version]"0.0.0" } } catch { [Version]"0.0.0" } } -Descending)
    $diag = @{
        BasePath = $BasePath; AppFoldersFound = @(); ModulesFolderExists = $false; VoiceModuleExists = $false
        LatestAppFolder = $null; LatestAppVersion = $null; ModulesPath = $null; VoiceModulePath = $null; Error = $null
    }
    if ($af.Count -eq 0) { $diag.Error = "NoAppFolders"; if ($ReturnDiagnostics) { return $diag }; return $null }
    $diag.AppFoldersFound = @($af | ForEach-Object { $_.Name })
    $diag.LatestAppFolder = $af[0].FullName
    if ($af[0].Name -match "app-\s*([\d\.]+)") { $diag.LatestAppVersion = $matches[1].Trim() } else { $diag.LatestAppVersion = $af[0].Name }
    $f = $af[0]
    $mp = Join-Path $f.FullName 'modules'
    $diag.ModulesPath = $mp
    if (Test-Path -LiteralPath $mp -PathType Container) {
        $diag.ModulesFolderExists = $true
        $voice = Get-VoiceModulePaths -AppPath $f.FullName
        if ($voice) {
            $diag.VoiceModuleExists = $true
            $diag.VoiceModulePath = $voice.VoiceModule.FullName
            if ($ReturnDiagnostics) { return $diag }
            return $f.FullName
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
        $exe = Get-ChildItem -LiteralPath $AppPath -Filter "*.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($exe) { return (Get-Item -LiteralPath $exe.FullName).VersionInfo.ProductVersion }
    } catch { }
    return "Unknown"
}

function Get-InstalledClients {
    $inst = [System.Collections.ArrayList]::new()
    $foundPaths = New-Object 'System.Collections.Generic.HashSet[string]'
    foreach ($k in $Script:DiscordClients.Keys) {
        $c = $Script:DiscordClients[$k]
        $isMod = $c.Name -match '\[Mod\]'
        if ($isMod -and $c.DetectPath -and -not (Test-Path -LiteralPath $c.DetectPath)) { continue }
        $fp = $null
        if ($c.Path -and (Test-Path -LiteralPath $c.Path)) { $fp = $c.Path }
        elseif ($c.FallbackPath -and (Test-Path -LiteralPath $c.FallbackPath)) { $fp = $c.FallbackPath }
        else {
            foreach ($pn in $c.Processes) {
                if ($pn -eq "Update") { continue }
                $dp = Get-PathFromProcess $pn
                if ($dp -and (Test-Path -LiteralPath $dp)) { $fp = $dp; break }
            }
        }
        if (-not $fp -and $c.Shortcut) {
            $sp = Get-PathFromShortcuts $c.Shortcut
            if ($sp -and (Test-Path -LiteralPath $sp)) { $fp = $sp }
        }
        if ($fp) {
            try { $fp = (Get-Item -LiteralPath $fp).FullName } catch { continue }
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



function Get-ClientInstallRoot {
    param([hashtable]$Client)
    if ($Client.Path) { return [IO.Path]::GetFullPath($Client.Path).TrimEnd('\') }
    if ($Client.AppPath) { return [IO.Path]::GetFullPath((Split-Path $Client.AppPath -Parent)).TrimEnd('\') }
    throw 'Cannot determine this Discord installation path.'
}

function Get-ScopedDiscordProcesses {
    param([string[]]$ProcessNames,[string[]]$InstallRoots)
    $roots = @($InstallRoots | ForEach-Object { [IO.Path]::GetFullPath($_).TrimEnd('\')+'\' })
    foreach ($proc in @(Get-Process -Name $ProcessNames -ErrorAction SilentlyContinue)) {
        $exePath = $null
        try { $exePath = $proc.Path } catch { }
        if (-not $exePath) {
            try { $exePath = (Get-CimInstance Win32_Process -Filter "ProcessId=$($proc.Id)" -ErrorAction Stop).ExecutablePath } catch { }
        }
        if (-not $exePath) {
            [pscustomobject]@{Process=$proc;Name=$proc.ProcessName;Unknown=$true;Path=$null}
            continue
        }
        $full = [IO.Path]::GetFullPath($exePath)
        if (@($roots | Where-Object { $full.StartsWith($_,[StringComparison]::OrdinalIgnoreCase) }).Count) {
            [pscustomobject]@{Process=$proc;Name=$proc.ProcessName;Unknown=$false;Path=$full}
        }
    }
}

function Stop-DiscordProcesses {
    param([string[]]$ProcessNames,[string]$InstallPath,[string[]]$InstallRoots,
          [int]$WaitSeconds=30)
    if ($InstallPath) { $InstallRoots=@($InstallPath) }
    if (-not $InstallRoots -or -not $InstallRoots.Count) {
        Write-Log 'No verified installation scope; refusing to stop processes.' -Level Error
        return $false
    }
    $names=@($ProcessNames + @('Update') | Select-Object -Unique)
    $watch=[Diagnostics.Stopwatch]::StartNew();$announced=$false;$quiet=$false
    do {
        $active=@(Get-ScopedDiscordProcesses -ProcessNames $names -InstallRoots $InstallRoots)
        if (@($active | Where-Object {$_.Unknown}).Count) {
            Write-Log 'A process path could not be verified. Close Discord and its updater, then retry; no files changed.' -Level Error
            return $false
        }
        $updaters=@($active | Where-Object {$_.Name -eq 'Update'})
        if ($updaters.Count) {
            $quiet=$false
            if (-not $announced) { Write-Log 'Waiting for the Discord updater to finish; it will not be force-stopped.' -Level Warning;$announced=$true }
        } elseif ($active.Count) {
            $quiet=$false
            foreach ($item in $active) {
                try { $item.Process | Stop-Process -Force -ErrorAction Stop } catch {
                    Write-Log 'Could not stop a scoped Discord process; no files changed.' -Level Error
                    return $false
                }
            }
        } elseif ($quiet) { return $true } else { $quiet=$true }
        if ($watch.Elapsed.TotalSeconds -ge $WaitSeconds) { break }
        Start-Sleep -Milliseconds 250
    } while ($true)
    Write-Log 'Discord or its updater is still active. Wait for it to finish and retry; no files changed.' -Level Error
    return $false
}

function Stop-AllDiscordProcesses {
    param([array]$Clients)
    if (-not $Clients) { $Clients=@(Get-InstalledClients) }
    $roots=@($Clients | ForEach-Object { Get-ClientInstallRoot $_ } | Select-Object -Unique)
    $names=@($Clients | ForEach-Object { $_.Client.Processes } | Where-Object {$_} | Select-Object -Unique)
    if (-not $roots.Count) { return $false }
    return Stop-DiscordProcesses -ProcessNames $names -InstallRoots $roots
}

function Start-DiscordClient {
    param([hashtable]$Client)
    if ($Script:IsElevated) {
        Write-Log 'Automatic relaunch skipped because this terminal is elevated. Start Discord normally from its shortcut.' -Level Warning
        return
    }
    $root=Get-ClientInstallRoot $Client
    $updater=Join-Path $root 'Update.exe'
    $exe=$Client.Client.Exe
    if (-not $exe) { $exe='Discord.exe' }
    try {
        if (Test-Path -LiteralPath $updater -PathType Leaf) {
            [void](Start-Process -FilePath $updater -ArgumentList @('--processStart',('"'+$exe+'"')) -WindowStyle Hidden -PassThru -ErrorAction Stop)
        } else {
            $path=Join-Path $Client.AppPath $exe
            if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw 'Client executable was not found.' }
            [void](Start-Process -FilePath $path -WindowStyle Hidden -PassThru -ErrorAction Stop)
        }
        Write-Log "Discord launch requested: $($Client.Name.Trim())" -Level Success
    } catch { Write-Log "Could not relaunch Discord: $_" -Level Warning }
}

function Read-VoiceStream {
    param([IO.Stream]$Stream)
    $Stream.Position=0
    $memory=[IO.MemoryStream]::new()
    try { $Stream.CopyTo($memory);return ,$memory.ToArray() } finally {$memory.Dispose()}
}

function Open-VoiceReadGuard {
    param([string]$Path,[IO.FileShare]$Share=[IO.FileShare]::Delete)
    $watch=[Diagnostics.Stopwatch]::StartNew()
    do {
        try { return [IO.File]::Open($Path,[IO.FileMode]::Open,[IO.FileAccess]::Read,$Share) }
        catch [IO.IOException] {
            if ($watch.Elapsed.TotalSeconds -ge [int]$Script:Config.FileLockWaitSeconds) {
                throw [IO.IOException]::new("Cannot obtain a stable file handle for '$Path'. Close Discord/IDA or wait for the updater; no replacement was made.",$_.Exception)
            }
            Start-Sleep -Milliseconds 250
        }
    } while ($true)
}

function Write-NewVerifiedFile {
    param([string]$Path,[byte[]]$Bytes)
    $stream=[IO.File]::Open($Path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
    try { $stream.Write($Bytes,0,$Bytes.Length);$stream.Flush($true) } finally {$stream.Dispose()}
    if ((Get-BytesSha256 ([IO.File]::ReadAllBytes($Path))) -ne (Get-BytesSha256 $Bytes)) { throw 'Backup verification failed.' }
}

function Get-VoiceClientKey {
    param([string]$NodePath)
    return (Get-BytesSha256 ([Text.Encoding]::UTF8.GetBytes([IO.Path]::GetFullPath($NodePath).ToLowerInvariant()))).Substring(0,16)
}

function Save-VerifiedStock {
    param([byte[]]$Bytes)
    $hash=Get-BytesSha256 $Bytes
    if ($hash -ne $Script:VoicePatchManifest.original_sha256) {throw 'Refusing to cache bytes that are not verified stock.'}
    # Keep every build's stock image; never included in rolling backup retention.
    $folder=Join-Path (Join-Path $Script:Config.TempDir 'VoiceBackup') $hash
    [void][IO.Directory]::CreateDirectory($folder)
    $path=Join-Path $folder 'discord_voice.node'
    if ((Test-Path -LiteralPath $path) -and (Get-BytesSha256 ([IO.File]::ReadAllBytes($path))) -eq $hash) {return $path}
    $temporary=Join-Path $folder ('.voice-stock-'+[Guid]::NewGuid().ToString('N')+'.tmp')
    try {
        Write-NewVerifiedFile -Path $temporary -Bytes $Bytes
        if (Test-Path -LiteralPath $path) {[IO.File]::Replace($temporary,$path,[NullString]::Value)}
        else {[IO.File]::Move($temporary,$path)}
        if ((Get-BytesSha256 ([IO.File]::ReadAllBytes($path))) -ne $hash) {throw 'Stock cache verification failed; no node patched.'}
    } finally {
        if (Test-Path -LiteralPath $temporary) {Remove-Item -LiteralPath $temporary -Force}
    }
    return $path
}

function Invoke-AtomicVoiceWrite {
    param([string]$SourcePath,[string]$TargetPath,[string]$ExpectedSourceHash,
          [AllowNull()][string]$ExpectedTargetHash,[byte[]]$OutputBytes,[byte[]]$NormalizedBytes,[string]$ClientName)
    $same=[string]::Equals($SourcePath,$TargetPath,[StringComparison]::OrdinalIgnoreCase)
    $sourceGuard=$null;$targetGuard=$null;$temporary=$null
    try {
        $share=if($same){[IO.FileShare]::Delete}else{[IO.FileShare]::Read}
        $sourceGuard=Open-VoiceReadGuard -Path $SourcePath -Share $share
        [byte[]]$current=Read-VoiceStream $sourceGuard
        if ((Get-BytesSha256 $current) -ne $ExpectedSourceHash) {throw 'Source changed during validation; no replacement made.'}
        $targetExists=Test-Path -LiteralPath $TargetPath -PathType Leaf
        if ($same) { $targetGuard=$sourceGuard;$preimage=$current }
        elseif ($targetExists) {
            $targetGuard=Open-VoiceReadGuard -Path $TargetPath
            [byte[]]$preimage=Read-VoiceStream $targetGuard
            if ((Get-BytesSha256 $preimage) -ne $ExpectedTargetHash) {throw 'Destination changed during validation; no replacement made.'}
        } elseif ($ExpectedTargetHash) {throw 'Destination disappeared during validation.'}
        $outputHash=Get-BytesSha256 $OutputBytes
        if ($same -and $outputHash -eq $ExpectedSourceHash) {
            if (-not $Script:Config.SkipBackup) {
                if (-not (Backup-VoiceNode -SourcePath $TargetPath -ClientName $ClientName -SourceBytes $preimage -NormalizedBytes $NormalizedBytes)) {throw 'History backup failed; no replacement made.'}
            }
            return $false
        }
        $directory=[IO.Path]::GetDirectoryName($TargetPath)
        $temporary=Join-Path $directory ('.voice-patch-'+[Guid]::NewGuid().ToString('N')+'.tmp')
        Write-NewVerifiedFile -Path $temporary -Bytes $OutputBytes
        if (-not $Script:Config.SkipBackup) {
            [void](Save-VerifiedStock $NormalizedBytes)
            if ($targetExists) {
                if (-not (Backup-VoiceNode -SourcePath $TargetPath -ClientName $ClientName -SourceBytes $preimage -NormalizedBytes $NormalizedBytes)) {throw 'History backup failed; no replacement made.'}
            }
        }
        if ($targetExists) {
            [IO.File]::Replace($temporary,$TargetPath,[NullString]::Value)
        } else {[IO.File]::Move($temporary,$TargetPath)}
        $temporary=$null
        if ((Get-BytesSha256 ([IO.File]::ReadAllBytes($TargetPath))) -ne $outputHash) {throw 'Output changed after replacement; inspect the saved backup before retrying.'}
        return $true
    } finally {
        if ($targetGuard -and -not $same) {$targetGuard.Dispose()}
        if ($sourceGuard) {$sourceGuard.Dispose()}
        if ($temporary -and (Test-Path -LiteralPath $temporary)) {Remove-Item -LiteralPath $temporary -Force}
    }
}

function Get-ValidatedVoiceImage {
    param([byte[]]$Bytes, [switch]$CurrentProfileOnly)
    if (-not $CurrentProfileOnly) {
        $match = Find-VoiceBuildProfile $Bytes
        Set-ActiveVoiceProfile $match.Entry
        return $match.Image
    }
    Assert-AuditedPatchManifest
    $image = Get-VoiceImageForProfile -Bytes $Bytes -Manifest $Script:VoicePatchManifest
    if ($null -eq $image) {throw 'Backup/module belongs to a different build or has unexpected bytes; no replacement made.'}
    return $image
}

function Get-VoiceImageForProfile {
    param([byte[]]$Bytes, $Manifest)
    $m = $Manifest
    if ($Bytes.LongLength -ne [long]$m.file_size) {return $null}
    [byte[]]$normalized=$Bytes.Clone()
    foreach($site in $m.patches){
        [byte[]]$original=Convert-HexBytes $site.expected_original
        $valid=(Test-BytesAt $Bytes $site.file_offset $original) -or (Test-BytesAt $Bytes $site.file_offset (Convert-HexBytes $site.patch))
        foreach($legacy in @($site.accepted_legacy)){if($legacy -and (Test-BytesAt $Bytes $site.file_offset (Convert-HexBytes $legacy))){$valid=$true}}
        if($site.gain_patches){foreach($v in $site.gain_patches.PSObject.Properties){if(Test-BytesAt $Bytes $site.file_offset (Convert-HexBytes $v.Value)){$valid=$true}}}
        if(-not $valid){return $null}
        [Array]::Copy($original,0,$normalized,[long]$site.file_offset,$original.Length)
    }
    if((Get-BytesSha256 $normalized) -ne $m.original_sha256){return $null}
    return [pscustomobject]@{Bytes=$Bytes;Normalized=$normalized;InputHash=(Get-BytesSha256 $Bytes)}
}

function Get-OriginalBackupClientName {
    param([string]$ClientName)
    if ([string]::IsNullOrWhiteSpace($ClientName)) {$ClientName='Discord'}
    return ($ClientName -replace '\s+','_' -replace '\[|\]','' -replace '-','_' -replace '[<>:"/\\|?*\x00-\x1F]','_')
}

function Get-BackupList {
    param([string]$ClientKey)
    if (-not (Test-Path -LiteralPath $Script:Config.BackupDir)) {return @()}
    foreach ($file in @(Get-ChildItem -LiteralPath $Script:Config.BackupDir -Filter 'discord_voice.node.*.backup' -File | Sort-Object LastWriteTime,Name -Descending)) {
        $meta=$null
        try {$meta=Get-Content -LiteralPath ($file.FullName+'.json') -Raw -Encoding UTF8 -ErrorAction Stop | ConvertFrom-Json} catch {}
        if ($ClientKey -and (-not $meta -or $meta.ClientKey -ne $ClientKey)) {continue}
        $group='__other__'
        if ($meta -and $meta.ClientName) {$group=Get-OriginalBackupClientName $meta.ClientName}
        elseif ($file.Name -match '^discord_voice\.node\.(.+)\.(\d{8}_\d{6})\.backup$') {$group=$matches[1]}
        # Metadata supports compatible restores; retention uses the original
        # client-name groups, including backups made by older script revisions.
        $hash=$null;$verified=$false;$stock=$false
        if ($meta) {
            $hash=Get-BytesSha256 ([IO.File]::ReadAllBytes($file.FullName))
            $verified=$hash -eq $meta.Sha256
            $stock=$verified -and $meta.StockSha256 -eq $hash
        }
        [pscustomobject]@{Path=$file.FullName;Date=$file.LastWriteTime;Size=$file.Length;Name=$file.Name;Metadata=$meta;Verified=[bool]$verified;IsStock=[bool]$stock;Legacy=(-not $meta);ClientGroup=$group}
    }
}

function Invoke-BackupRetention {
    if (-not $Script:Config.BackupDir) {return}
    [void][IO.Directory]::CreateDirectory($Script:Config.BackupDir)
    $root=[IO.Path]::GetFullPath($Script:Config.BackupDir).TrimEnd('\')
    if ($root.Length -lt 4 -or $root -eq [IO.Path]::GetPathRoot($root).TrimEnd('\')) {throw 'Invalid backup retention directory.'}
    $maxAge=[int]$Script:Config.MaxBackupAgeDays
    if ($maxAge -lt 1) {$maxAge=45}
    $limit=[int]$Script:Config.MaxBackupsPerClient
    if ($limit -lt 1) {$limit=3}
    $cutoff=(Get-Date).AddDays(-$maxAge)
    $removed=0
    foreach ($group in @(Get-BackupList | Group-Object ClientGroup)) {
        $position=0
        foreach ($entry in @($group.Group | Sort-Object Date,Name -Descending)) {
            if ($entry.Date -ge $cutoff) {
                $position++
                if ($position -le $limit) {continue}
            }
            $full=[IO.Path]::GetFullPath($entry.Path)
            if ([IO.Path]::GetDirectoryName($full) -ne $root) {throw 'Backup retention path escaped its configured folder.'}
            Remove-Item -LiteralPath $full -Force -ErrorAction Stop
            if (Test-Path -LiteralPath ($full+'.json')) {Remove-Item -LiteralPath ($full+'.json') -Force}
            $removed++
        }
    }
    if ($removed -gt 0) {Write-Log "Pruned old voice backups: removed $removed file(s) (max $limit per client, max age ${maxAge}d)." -Level Info}
    # VoiceBackup and any earlier Backups\Stock archives are outside this scan.
}

function Backup-VoiceNode {
    param([string]$SourcePath,[string]$ClientName='Discord',[byte[]]$SourceBytes,[byte[]]$NormalizedBytes)
    if ($Script:Config.SkipBackup) {Write-Log 'Skipping backup' -Level Warning;return $true}
    try {
        if (-not $SourceBytes) {$image=Get-ValidatedVoiceImage ([IO.File]::ReadAllBytes($SourcePath));$SourceBytes=$image.Bytes;$NormalizedBytes=$image.Normalized}
        if (-not $NormalizedBytes) {$NormalizedBytes=(Get-ValidatedVoiceImage $SourceBytes).Normalized}
        [void](Save-VerifiedStock $NormalizedBytes)
        [void][IO.Directory]::CreateDirectory($Script:Config.BackupDir)
        if ([string]::IsNullOrWhiteSpace($ClientName)) {$ClientName='Discord'}
        $name=Get-OriginalBackupClientName $ClientName
        $stamp=Get-Date
        $file=Join-Path $Script:Config.BackupDir ("discord_voice.node.$name."+$stamp.ToString('yyyyMMdd_HHmmss')+'.backup')
        # Retain the original filename format without overwriting a snapshot if
        # two patch operations occur within the same second.
        while ((Test-Path -LiteralPath $file) -or (Test-Path -LiteralPath ($file+'.json'))) {
            $stamp=$stamp.AddSeconds(1)
            $file=Join-Path $Script:Config.BackupDir ("discord_voice.node.$name."+$stamp.ToString('yyyyMMdd_HHmmss')+'.backup')
        }
        Write-NewVerifiedFile -Path $file -Bytes $SourceBytes
        $metadata=@{ClientKey=(Get-VoiceClientKey $SourcePath);ClientName=$ClientName;SourcePath=[IO.Path]::GetFullPath($SourcePath);Profile=$Script:VoicePatchManifest.profile;Sha256=(Get-BytesSha256 $SourceBytes);StockSha256=(Get-BytesSha256 $NormalizedBytes);Created=[DateTime]::UtcNow.ToString('o')}
        [IO.File]::WriteAllText($file+'.json',($metadata|ConvertTo-Json),[Text.UTF8Encoding]::new($false))
        Invoke-BackupRetention
        Write-Log "Backup created: $([IO.Path]::GetFileName($file))" -Level Success
        return $true
    } catch {Write-Log "Backup failed: $_" -Level Error;return $false}
}

function Show-BackupList {
    Invoke-BackupRetention
    $records=@(Get-BackupList)
    Write-Host "`n=== Available Backups ===" -ForegroundColor Cyan
    for ($i=0;$i -lt $records.Count;$i++) {
        $entry=$records[$i]
        Write-Host ("  [{0}] {1} - {2} MB - {3}" -f ($i+1),$entry.Date.ToString('yyyy-MM-dd HH:mm:ss'),[Math]::Round($entry.Size/1MB,2),$entry.Name)
    }
    if (-not $records.Count) {Write-Host 'No backups found'}
    Write-Host ('Stock nodes by build: '+(Join-Path $Script:Config.TempDir 'VoiceBackup'))
    Write-Host ''
}

function Restore-ClientStock {
    param([hashtable]$Client)
    $voice=Get-VoiceModulePaths $Client.AppPath
    if(-not $voice){throw 'No installed voice module found.'}
    [void](Get-ValidatedVoiceImage ([IO.File]::ReadAllBytes($voice.VoiceNodePath)))
    if(-not(Stop-DiscordProcesses -ProcessNames $Client.Client.Processes -InstallPath (Get-ClientInstallRoot $Client))){return $false}
    [void](Invoke-VoiceNodePatch -NodePath $voice.VoiceNodePath -ClientName $Client.Name -RestoreStock)
    return $true
}

function Restore-FromBackup {
    param([string]$BackupPath,[hashtable]$Client)
    if(-not $Client){throw 'Select the target client before choosing a history backup.'}
    $voice=Get-VoiceModulePaths $Client.AppPath
    if(-not $voice){throw 'No installed voice module found.'}
    $target=$voice.VoiceNodePath
    $current=Get-ValidatedVoiceImage ([IO.File]::ReadAllBytes($target))
    if(-not $BackupPath){
        $picker=New-Object Windows.Forms.OpenFileDialog
        $picker.Title='Choose a compatible backup for the selected client'
        $picker.Filter='Voice history (*.backup)|*.backup|All files|*.*'
        if(Test-Path -LiteralPath $Script:Config.BackupDir){$picker.InitialDirectory=$Script:Config.BackupDir}
        if($picker.ShowDialog() -ne [Windows.Forms.DialogResult]::OK){return $false}
        $BackupPath=$picker.FileName
    }
    $meta=$null
    if(Test-Path -LiteralPath ($BackupPath+'.json')){
        $meta=Get-Content -LiteralPath ($BackupPath+'.json') -Raw -Encoding UTF8|ConvertFrom-Json
        if($meta.ClientKey -ne (Get-VoiceClientKey $target)){throw 'That backup belongs to a different client/version path. No changes made.'}
    }
    $backup=Get-ValidatedVoiceImage ([IO.File]::ReadAllBytes($BackupPath)) -CurrentProfileOnly
    if($meta -and $meta.Sha256 -ne $backup.InputHash){throw 'Backup hash differs from its saved metadata.'}
    [byte[]]$output=$backup.Bytes.Clone()
    foreach($site in $Script:VoicePatchManifest.patches){
        if($site.kind -eq 'copy_gain' -and $site.legacy_gain_patches){
            foreach($entry in $site.legacy_gain_patches.PSObject.Properties){
                if(Test-BytesAt $output $site.file_offset (Convert-HexBytes $entry.Value)){
                    $newVariant=Convert-HexBytes $site.gain_patches.PSObject.Properties[$entry.Name].Value
                    [Array]::Copy($newVariant,0,$output,[long]$site.file_offset,$newVariant.Length)
                    break
                }
            }
        }

    }
    if(-not(Stop-DiscordProcesses -ProcessNames $Client.Client.Processes -InstallPath (Get-ClientInstallRoot $Client))){return $false}
    [void](Invoke-AtomicVoiceWrite -SourcePath $target -TargetPath $target -ExpectedSourceHash $current.InputHash -ExpectedTargetHash $current.InputHash -OutputBytes $output -NormalizedBytes $current.Normalized -ClientName $Client.Name)
    Write-Log 'Compatible history backup restored and verified; compatible gain bytecode was migrated.' -Level Success
    return $true
}

function Get-VoiceModulePaths {
    param([Parameter(Mandatory)][string]$AppPath)
    $modulesPath = Join-Path $AppPath 'modules'
    $voiceModules = @(Get-ChildItem -LiteralPath $modulesPath -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '^discord_voice(?:-\d+)?$' } |
        Sort-Object @{Expression={ if ($_.Name -match '-(\d+)$') { [int]$matches[1] } else { 0 } };Descending=$true})
    foreach ($module in $voiceModules) {
        foreach ($folder in @((Join-Path $module.FullName 'discord_voice'),$module.FullName)) {
            $node = Join-Path $folder 'discord_voice.node'
            if (Test-Path -LiteralPath $node -PathType Leaf) {
                return @{ModulesPath=$modulesPath;VoiceModule=$module;VoiceFolderPath=$folder;VoiceNodePath=$node}
            }
        }
    }
    return $null
}

function Show-ConfigurationGUI {
    Add-Type -AssemblyName System.Windows.Forms, System.Drawing
    $prevCfg = Get-UserConfig
    $installedClients = @(Get-InstalledClients)
    $initGain = if ($prevCfg -and -not $Script:GainExplicitlySet) { [Math]::Max(1, [Math]::Min(10, $prevCfg.LastGainMultiplier)) } else { $Script:Config.AudioGainMultiplier }

    $Script:GuiInstalledIndices = @{}
    foreach ($ic in $installedClients) { $Script:GuiInstalledIndices[$ic.Index] = $ic }
    $Script:GuiInstalledClients = $installedClients

    $normalHeight = 570
    $debugPanelHeight = 550
    $debugExpandedHeight = [Math]::Max($normalHeight, [Math]::Min($normalHeight + $debugPanelHeight, [Windows.Forms.Screen]::PrimaryScreen.WorkingArea.Height - 70))
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

    $null = & $newLabel 20 20 400 30 "Discord Voice Quality Patcher" (New-Object Drawing.Font("Segoe UI", 16, [Drawing.FontStyle]::Bold)) ([Drawing.Color]::FromArgb(88,101,242))
    $null = & $newLabel 420 28 80 20 "v$Script:SCRIPT_VERSION" (New-Object Drawing.Font("Segoe UI", 9)) ([Drawing.Color]::FromArgb(150,152,157))
    $null = & $newLabel 20 55 480 20 "Profile: 48kHz | $($Script:Config.Bitrate)kbps $Script:RateModeLabel | Stereo" (New-Object Drawing.Font("Segoe UI", 9)) ([Drawing.Color]::FromArgb(185,187,190))
    $null = & $newLabel 20 85 480 25 "Discord Client" (New-Object Drawing.Font("Segoe UI", 11, [Drawing.FontStyle]::Bold)) $null

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
    if ($installedClients.Count -gt 0) {
        $installCount = @(Get-UniqueClientsByAppPath -Clients $installedClients).Count
        $detectedLabel.Text = "Detected: $($installedClients.Count) client entries | $installCount unique install(s)"
    }
    else { $detectedLabel.Text = "No Discord clients detected - please install Discord first"; $detectedLabel.ForeColor = [Drawing.Color]::FromArgb(237,66,69) }

    $null = & $newLabel 20 175 480 25 "Audio Gain Level" (New-Object Drawing.Font("Segoe UI", 12, [Drawing.FontStyle]::Bold)) $null
    $valueLabel = & $newLabel 20 205 480 30 "" (New-Object Drawing.Font("Segoe UI", 14, [Drawing.FontStyle]::Bold)) $null
    $valueLabel.TextAlign = [Drawing.ContentAlignment]::MiddleCenter

    $updateLabel = { param([int]$m)
        $valueLabel.Text = if ($m -eq 1) { "Level 1 — 1x (original volume)" } else { "Level $m — ${m}x" }
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

    $null = & $newLabel 30 290 460 20 "1       2       3       4       5       6       7       8       9      10" (New-Object Drawing.Font("Consolas", 8)) ([Drawing.Color]::FromArgb(150,152,157))
    $null = & $newLabel 20 315 480 30 "Linear gain: level 2 = 2x. Higher levels can clip loud input." (New-Object Drawing.Font("Segoe UI", 9)) ([Drawing.Color]::FromArgb(185,187,190))

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

    $localOnlyChk = New-Object Windows.Forms.CheckBox -Property @{
        Location = "20,405"; Size = "480,25"; Text = "Patch local files only (skip GitHub module download)"
        Checked = $PatchLocalOnly.IsPresent
        ForeColor = [Drawing.Color]::White; Font = New-Object Drawing.Font("Segoe UI", 9)
    }
    $form.Controls.Add($localOnlyChk)

    if($Script:IsElevated){$autoRelaunchChk.Checked=$false;$autoRelaunchChk.Enabled=$false}

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
        Location = "20,68"; Size = "480,20"; TextAlign = [Drawing.ContentAlignment]::MiddleLeft
        Font = New-Object Drawing.Font("Segoe UI", 9); ForeColor = [Drawing.Color]::FromArgb(185,187,190)
    }
    $debugPanel.Controls.Add($counterLabel)
    $Script:DebugCounterLabel = $counterLabel

    $updateCounter = {
        $pb = $Script:DebugPatchCheckboxes
        $gb = $Script:DebugGroupCheckboxes
        $lbl = $Script:DebugCounterLabel
        if ($null -eq $pb -or $null -eq $lbl) { return }
        $enabled = @($pb.Values | Where-Object { $_.Checked }).Count
        $lbl.Text = "$enabled / $($Script:DebugTotalPatches) patches enabled"
        $wasSuppressed = $Script:SuppressGroupToggle
        $Script:SuppressGroupToggle = $true
        try {
            foreach ($gn in $Script:PatchGroups.Keys) {
                $unchecked = @($Script:PatchGroups[$gn].Keys | Where-Object { $pb.ContainsKey($_) -and -not $pb[$_].Checked })
                if ($gb.ContainsKey($gn)) { $gb[$gn].Checked = ($unchecked.Count -eq 0) }
            }

        } finally { $Script:SuppressGroupToggle = $wasSuppressed }
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
        if ($pb) { foreach ($cb in $pb.Values) { if ($cb.Enabled) { $cb.Checked = $false } } }
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
        Location = "215,38"; Size = "285,20"; Text = ""
        Font = New-Object Drawing.Font("Segoe UI", 8); ForeColor = [Drawing.Color]::FromArgb(87,242,135)
    }
    $debugPanel.Controls.Add($copyOffsetsStatus)
    $Script:StatusLabelCopyOffsets = $copyOffsetsStatus

    $historyBtn = New-Object Windows.Forms.Button -Property @{
        Location="20,35";Size="180,28";Text="Restore backup...";FlatStyle="Flat"
        BackColor=[Drawing.Color]::FromArgb(79,84,92);ForeColor=[Drawing.Color]::White
    }
    $historyBtn.Add_Click({
        if(-not $Script:GuiInstalledIndices.ContainsKey($clientCombo.SelectedIndex)){$statusLabel.Text='Select an installed client first';return}
        $form.Tag=@{Action='RestoreBackup';ClientIndex=$clientCombo.SelectedIndex;SkipBackup=(-not $chk.Checked);AutoRelaunch=$autoRelaunchChk.Checked}
        $form.DialogResult='OK';$form.Close()
    })
    $debugPanel.Controls.Add($historyBtn)

    $yPos = 100
    $groupColors = @{
        STEREO     = [Drawing.Color]::FromArgb(254,231,92)
        BITRATE    = [Drawing.Color]::FromArgb(254,231,92)
        BANDWIDTH = [Drawing.Color]::FromArgb(87,242,135)
        FILTER     = [Drawing.Color]::FromArgb(254,231,92)
                CELT       = [Drawing.Color]::FromArgb(78,205,196)
    }

    foreach ($groupName in $Script:PatchGroups.Keys) {
        $patches = $Script:PatchGroups[$groupName]
        if($patches.Count -eq 0){continue}
        $groupColor = $groupColors[$groupName]
        if (-not $groupColor) { $groupColor = [Drawing.Color]::FromArgb(254,231,92) }

        $grpChecked = @($patches.Keys | Where-Object { -not $Script:SelectedPatches[$_] }).Count -eq 0
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
            $offsetHex = 'RVA selected per build'

            $pChk = New-Object Windows.Forms.CheckBox -Property @{
                Location = New-Object Drawing.Point(45, $yPos)
                Size = New-Object Drawing.Size(440, 20)
                Text = $patchInfo.Name; Checked = [bool]$Script:SelectedPatches[$patchKey]
                ForeColor = [Drawing.Color]::White
                Font = New-Object Drawing.Font("Segoe UI", 9)
            }
            $pChk.Add_CheckedChanged({
                if (-not $Script:SuppressGroupToggle) { & $updateCounter }
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

    $null = & $btnStyle 20 "Restore stock" 79 84 92 $false {
        if(-not $Script:GuiInstalledIndices.ContainsKey($clientCombo.SelectedIndex)){$statusLabel.Text='Select an installed client first';return}
        $form.Tag=@{Action='RestoreStock';ClientIndex=$clientCombo.SelectedIndex;SkipBackup=(-not $chk.Checked);AutoRelaunch=$autoRelaunchChk.Checked}
        $form.DialogResult='OK';$form.Close()
    }

    $null = & $btnStyle 115 "Patch" 88 101 242 $true {
        $selectedIdx = $clientCombo.SelectedIndex
        if (-not $Script:GuiInstalledIndices.ContainsKey($selectedIdx)) { $statusLabel.Text = "Selected client is not installed!"; return }
        $patchSel = @{}
        $isDbg = $debugPanel.Visible
        $pb = if ($isDbg) { $Script:DebugPatchCheckboxes } else { $patchCheckboxes }
        foreach ($pk in $Script:AllPatchKeys) {
            if ($isDbg -and $pb -and $pb.ContainsKey($pk)) {
                $patchSel[$pk] = $pb[$pk].Checked
            } else {
                $patchSel[$pk] = $true
            }
        }
        $form.Tag = @{
            Action = 'Patch'; Multiplier = $slider.Value
            SkipBackup = -not $chk.Checked; AutoRelaunch = $autoRelaunchChk.Checked
            ClientIndex = $selectedIdx; DebugMode = $isDbg; SelectedPatches = $patchSel
            PatchLocalOnly = $localOnlyChk.Checked
        }
        $form.DialogResult = "OK"; $form.Close()
    }

    $null = & $btnStyle 210 "Patch All" 87 158 87 $true {
        if ($Script:GuiInstalledClients.Count -eq 0) { $statusLabel.Text = "No Discord clients detected to patch!"; return }
        $patchSel = @{}
        $isDbg = $debugPanel.Visible
        $pb = if ($isDbg) { $Script:DebugPatchCheckboxes } else { $patchCheckboxes }
        foreach ($pk in $Script:AllPatchKeys) {
            if ($isDbg -and $pb -and $pb.ContainsKey($pk)) {
                $patchSel[$pk] = $pb[$pk].Checked
            } else {
                $patchSel[$pk] = $true
            }
        }
        $form.Tag = @{
            Action = 'PatchAll'; Multiplier = $slider.Value
            SkipBackup = -not $chk.Checked; AutoRelaunch = $autoRelaunchChk.Checked
            DebugMode = $isDbg; SelectedPatches = $patchSel
            PatchLocalOnly = $localOnlyChk.Checked
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
            $debugPanel.Height = [Math]::Max(1, $debugExpandedHeight - $debugPanel.Top)
            $debugPanel.Visible = $true
            $debugBadge.Visible = $true
            $form.ClientSize = New-Object Drawing.Size($formWidth, $debugExpandedHeight)
            & $updateCounter
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



function Initialize-Environment {
    foreach($folder in @($Script:Config.TempDir,$Script:Config.BackupDir)) { [void][IO.Directory]::CreateDirectory($folder) }
    if(-not $Script:EnvironmentReady){Write-Log ("Patcher session started: "+[DateTime]::Now.ToString('s')) -Level Info;$Script:EnvironmentReady=$true}
    Invoke-BackupRetention
}

function Remove-PatcherTempFiles {
    # The native engine cleans its temporary file in its own finally block.
}

function Get-UniqueClientsByAppPath {
    param([array]$Clients)
    $seen = @{}; $out = [System.Collections.ArrayList]::new()
    foreach ($c in $Clients) {
        if (-not $c.AppPath -or $seen.ContainsKey($c.AppPath)) { continue }
        $seen[$c.AppPath] = $true; [void]$out.Add($c)
    }
    return @($out)
}

function Get-SafeVoiceChild {
    param([string]$Root, [string]$RelativePath)
    $parts = @($RelativePath.Replace('\','/').Split('/'))
    if (-not $RelativePath -or [IO.Path]::IsPathRooted($RelativePath)) {throw 'Invalid package path.'}
    foreach ($part in $parts) {
        if (-not $part -or $part -in @('.','..') -or $part -match '[<>:"|?*\x00-\x1f]' -or
            $part -match '[. ]$' -or $part -match '^(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)') {throw "Invalid package path: $RelativePath"}
    }
    $base = [IO.Path]::GetFullPath($Root).TrimEnd('\','/') + [IO.Path]::DirectorySeparatorChar
    $path = [IO.Path]::GetFullPath([IO.Path]::Combine($base,($parts -join [IO.Path]::DirectorySeparatorChar)))
    if (-not $path.StartsWith($base,[StringComparison]::OrdinalIgnoreCase)) {throw 'Package path escapes its destination.'}
    return $path
}

function Remove-VoiceStagingDirectory {
    param([string]$Path, [string]$Parent)
    $full = [IO.Path]::GetFullPath($Path)
    $base = [IO.Path]::GetFullPath($Parent).TrimEnd('\','/')
    if ([IO.Path]::GetDirectoryName($full) -ne $base -or [IO.Path]::GetFileName($full) -notmatch '^\.voice-(stage|download|previous)-[0-9a-f]{32}$') {throw 'Refusing to remove a folder outside the staging area.'}
    if (Test-Path -LiteralPath $full) {
        if ((Get-Item -LiteralPath $full -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {throw 'Refusing to remove a linked staging folder.'}
        [void](Get-VoiceFolderFingerprint $full -LinksOnly) # Reject nested links before recursive removal.
        Remove-Item -LiteralPath $full -Recurse -Force -ErrorAction Stop
    }
}

function Get-VoiceFolderFingerprint {
    param([string]$Folder, [switch]$LinksOnly)
    $root = [IO.Path]::GetFullPath($Folder).TrimEnd('\','/')
    $pending = [Collections.Generic.Queue[string]]::new()
    $pending.Enqueue($root)
    $lines = [Collections.Generic.List[string]]::new()
    while ($pending.Count) {
        $directory = $pending.Dequeue()
        $directoryInfo = [IO.DirectoryInfo]::new($directory)
        if ($directoryInfo.Attributes -band [IO.FileAttributes]::ReparsePoint) {throw 'Linked voice folders are not supported.'}
        foreach ($item in $directoryInfo.EnumerateFileSystemInfos()) {
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {throw 'Linked voice files are not supported.'}
            if ($item -is [IO.DirectoryInfo]) {$pending.Enqueue($item.FullName)}
            elseif (-not $LinksOnly) {$lines.Add($item.FullName.Substring($root.Length+1)+'|'+$item.Length+'|'+(Get-VoiceFileSha256 $item.FullName))}
        }
    }
    return Get-BytesSha256 ([Text.Encoding]::UTF8.GetBytes((@($lines | Sort-Object) -join "`n")))
}

function Get-VoiceFileSha256 {
    param([string]$Path)
    $algorithm = [Security.Cryptography.SHA256]::Create()
    $stream = [IO.File]::OpenRead($Path)
    try {return ([BitConverter]::ToString($algorithm.ComputeHash($stream))).Replace('-','').ToLowerInvariant()}
    finally {$stream.Dispose();$algorithm.Dispose()}
}

function Receive-VoiceGitHubFile {
    param([string]$Uri, [string]$Destination)
    $address = [uri]$Uri
    if ($address.Scheme -ne 'https' -or $address.Host -ne 'raw.githubusercontent.com') {throw 'Invalid GitHub download address.'}
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $address -OutFile $Destination -UseBasicParsing -TimeoutSec 120 -ErrorAction Stop -Headers @{'User-Agent'='DiscordVoicePatcher';'Cache-Control'='no-cache'} | Out-Null
    if (-not (Test-Path -LiteralPath $Destination -PathType Leaf) -or (Get-Item -LiteralPath $Destination).Length -eq 0) {throw 'GitHub returned an empty download.'}
}

function Get-PreparedVoiceBackupPath {
    # One shared Stable module for every client. No package catalog or ZIP files.
    $folder = Join-Path $Script:Config.TempDir ('.voice-download-'+[guid]::NewGuid().ToString('N'))
    $module = Join-Path $folder 'module'
    [void][IO.Directory]::CreateDirectory($module)
    $downloadStep = 'preparing the GitHub download'
    try {
        Write-Log 'Downloading the unpatched Stable voice module from GitHub...' -Level Info
        [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
        $repo = $Script:Config.VoiceRepository
        $headers = @{'User-Agent'='DiscordVoicePatcher';'Accept'='application/vnd.github+json';'Cache-Control'='no-cache'}
        $ref = [uri]::EscapeDataString($Script:Config.VoiceRepositoryRef)
        $requestUri = "https://api.github.com/repos/$repo/commits/$ref"
        $downloadStep = "requesting $requestUri"
        $commit = Invoke-RestMethod -Uri $requestUri -UseBasicParsing -TimeoutSec 30 -ErrorAction Stop -Headers $headers
        if ($commit.sha -notmatch '^[0-9a-f]{40}$') {throw 'GitHub did not return a valid revision.'}
        $remotePath = (@($Script:Config.VoiceRepositoryPath.Split('/') | ForEach-Object {[uri]::EscapeDataString($_)}) -join '/')
        $requestUri = "https://api.github.com/repos/$repo/contents/$($remotePath)?ref=$($commit.sha)"
        $downloadStep = "requesting $requestUri"
        # Assign directly: Invoke-RestMethod emits a JSON array as one object.
        # Wrapping the command in @() nests it and joins all names into one URL.
        $files = Invoke-RestMethod -Uri $requestUri -UseBasicParsing -TimeoutSec 30 -ErrorAction Stop -Headers $headers
        # Use the ordinary files in the existing stock folder, just as the old
        # patcher did. Pin all downloads to the same commit during an update.
        $files = @($files | Where-Object {$_.type -eq 'file' -and $_.name -match '^(discord_voice\.node|[a-zA-Z0-9_.-]+\.(js|dll|exe|tflite)|package\.json|manifest\.json)$'})
        foreach ($name in @('discord_voice.node','index.js','package.json','manifest.json')) {
            if (@($files | Where-Object {$_.name -eq $name}).Count -ne 1) {throw "GitHub stock folder is missing $name or contains duplicates."}
        }
        $seen = @{}
        foreach ($file in $files) {
            $destination = Get-SafeVoiceChild $module ([string]$file.name)
            if ($seen.ContainsKey($destination)) {throw 'Duplicate stock download filename.'}
            $seen[$destination] = $true
            $uri = "https://raw.githubusercontent.com/$repo/$($commit.sha)/$remotePath/"+[uri]::EscapeDataString($file.name)
            $downloadStep = "downloading $($file.name) from $uri"
            Receive-VoiceGitHubFile $uri $destination
            if ((Get-Item -LiteralPath $destination).Length -ne [long]$file.size) {throw "Incomplete download: $($file.name)"}
        }
        $downloadStep = 'verifying the downloaded Stable module'
        [byte[]]$bytes = [IO.File]::ReadAllBytes((Join-Path $module 'discord_voice.node'))
        $match = Find-VoiceBuildProfile $bytes
        $hash = Get-BytesSha256 $bytes
        if ($hash -ne $match.Entry.manifest.original_sha256) {throw 'The GitHub node is patched; upload the original Stable node.'}
        Write-Log ("Stable node verified: SHA256 "+$hash) -Level Success
        return [pscustomobject]@{Root=$folder;Folder=$module;Entry=$match.Entry;Fingerprint=(Get-VoiceFolderFingerprint $module)}
    } catch {
        $failure = $_
        try {Remove-VoiceStagingDirectory $folder $Script:Config.TempDir}
        catch {Write-Log ("Temporary download folder retained at ${folder}: $_") -Level Warning}
        throw "Stock module download/verification failed while ${downloadStep}: $failure No installed files changed. Correct the reported problem and retry, or use Patch local files only."
    }
}

function Install-DownloadedVoiceModule {
    param($Client, $Voice, $Download)
    $target = [IO.Path]::GetFullPath($Voice.VoiceFolderPath).TrimEnd('\','/')
    $parent = [IO.Path]::GetDirectoryName($target)
    if ([IO.Path]::GetFileName($target) -ne 'discord_voice') {throw 'Unexpected voice module destination.'}
    $stage = Join-Path $parent ('.voice-stage-'+[guid]::NewGuid().ToString('N'))
    $previous = Join-Path $parent ('.voice-previous-'+[guid]::NewGuid().ToString('N'))
    $movedOriginal = $false; $installed = $false
    try {
        $before = Get-VoiceFolderFingerprint $target
        if ((Get-VoiceFolderFingerprint $Download.Folder) -ne $Download.Fingerprint) {throw 'Downloaded files changed before staging.'}
        [void][IO.Directory]::CreateDirectory($stage)
        foreach ($item in Get-ChildItem -LiteralPath $target -Force) {Copy-Item -LiteralPath $item.FullName -Destination $stage -Recurse -Force}
        if ((Get-VoiceFolderFingerprint $stage) -ne $before) {throw 'Installed module changed while being staged.'}
        foreach ($item in Get-ChildItem -LiteralPath $Download.Folder -File -Force) {
            $destination = Get-SafeVoiceChild $stage $item.Name
            Copy-Item -LiteralPath $item.FullName -Destination $destination -Force
            if ((Get-VoiceFileSha256 $destination) -ne (Get-VoiceFileSha256 $item.FullName)) {throw 'Incomplete stock module staging.'}
        }
        $skipBackup = $Script:Config.SkipBackup
        try {
            $Script:Config.SkipBackup = $true # The complete installed folder is backed up below.
            [void](Invoke-VoiceNodePatch -NodePath (Join-Path $stage 'discord_voice.node') -ClientName $Client.Name)
        } finally {$Script:Config.SkipBackup = $skipBackup}
        $expected = Get-VoiceFolderFingerprint $stage
        if ($before -eq $expected) {Write-Log 'The downloaded module and selected patches are already installed.' -Level Success;return}
        if (-not (Stop-DiscordProcesses -ProcessNames $Client.Client.Processes -InstallPath (Get-ClientInstallRoot $Client))) {throw 'Discord did not close; module unchanged.'}
        if ((Get-VoiceFolderFingerprint $target) -ne $before) {throw 'Installed module changed during preparation; module unchanged.'}
        # Both destinations are verified, unique siblings of the exact module.
        if ([IO.Path]::GetDirectoryName($stage) -ne $parent -or [IO.Path]::GetDirectoryName($previous) -ne $parent) {throw 'Invalid module transaction paths.'}
        [IO.Directory]::Move($target,$previous)
        $movedOriginal = $true
        if ((Get-VoiceFolderFingerprint $previous) -ne $before) {throw 'Module changed while preparing the replacement.'}
        Move-PreparedVoiceModule $stage $target
        $installed = $true
        if ((Get-VoiceFolderFingerprint $target) -ne $expected) {throw 'Installed module verification failed.'}
        $movedOriginal = $false
        if ($skipBackup) {
            try {Remove-VoiceStagingDirectory $previous $parent}
            catch {Write-Log ("Module installed; temporary rollback folder retained at ${previous}: $_") -Level Warning}
        }
        else {Write-Log ("Previous complete module saved: "+$previous) -Level Info}
        Write-Log 'Stable module patched, installed, and verified.' -Level Success
    } catch {
        $failure = $_
        if ($movedOriginal) {
            try {
                if ($installed) {[IO.Directory]::Move($target,$stage)}
                [IO.Directory]::Move($previous,$target)
                Write-Log 'Previous module restored after the installation failed.' -Level Warning
            } catch {throw "Installation failed and automatic rollback could not finish. Previous module: $previous. $_"}
        }
        throw $failure
    } finally {
        try {Remove-VoiceStagingDirectory $stage $parent}
        catch {Write-Log ("Temporary staging folder retained at ${stage}: $_") -Level Warning}
    }
}

function Move-PreparedVoiceModule {
    param([string]$Source, [string]$Destination)
    [IO.Directory]::Move($Source,$Destination)
}

function Invoke-PatchClients {
    param([array]$Clients, [switch]$PatchLocalOnly)
    $success=0;$failed=[Collections.ArrayList]::new();$succeeded=[Collections.ArrayList]::new()
    $download = $null
    if (-not @($Clients).Count) {return @{Success=0;Failed=@();SucceededClients=@();Total=0}}
    try {
        if (-not $PatchLocalOnly) {
            try {$download = Get-PreparedVoiceBackupPath}
            catch {
                Write-Log ([string]$_) -Level Error
                return @{Success=0;Failed=@($Clients | ForEach-Object {$_.Name});SucceededClients=@();Total=@($Clients).Count}
            }
        }
        foreach($client in $Clients){
            try{
                $voice=Get-VoiceModulePaths $client.AppPath
                if(-not $voice){throw 'No installed voice module; start Discord once to install it.'}
                if ($PatchLocalOnly) {
                    [void](Invoke-VoiceNodePatch -NodePath $voice.VoiceNodePath -DryRun)
                    if(-not(Stop-DiscordProcesses -ProcessNames $client.Client.Processes -InstallPath (Get-ClientInstallRoot $client))){throw 'Shutdown verification failed; no files changed.'}
                    [void](Invoke-VoiceNodePatch -NodePath $voice.VoiceNodePath -ClientName $client.Name)
                } else {
                    Install-DownloadedVoiceModule -Client $client -Voice $voice -Download $download
                }
                $success++;[void]$succeeded.Add($client)
            }catch{Write-Log ("Skipped/failed "+$client.Name.Trim()+": "+$_) -Level Error;[void]$failed.Add($client.Name)}
        }
        return @{Success=$success;Failed=@($failed);SucceededClients=@($succeeded);Total=@($Clients).Count}
    } finally {
        if ($null -ne $download) {
            try {Remove-VoiceStagingDirectory $download.Root $Script:Config.TempDir}
            catch {Write-Log ("Temporary download folder retained at $($download.Root): $_") -Level Warning}
        }
    }
}

function Convert-HexBytes {
    param([string]$Text)
    if ([string]::IsNullOrWhiteSpace($Text)) { throw 'Empty byte sequence in manifest.' }
    [byte[]]$converted = @($Text.Trim() -split '\s+' | ForEach-Object { [Convert]::ToByte($_,16) })
    return ,$converted
}
function Get-BytesSha256 {
    param([byte[]]$Data)
    $hasher = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($hasher.ComputeHash($Data))).Replace('-','').ToLowerInvariant() }
    finally { $hasher.Dispose() }
}
function Test-BytesAt {
    param([byte[]]$Data,[long]$Offset,[byte[]]$Expected)
    if ($Offset -lt 0 -or $Offset + $Expected.Length -gt $Data.LongLength) { return $false }
    for ($index=0; $index -lt $Expected.Length; $index++) {
        if ($Data[$Offset+$index] -ne $Expected[$index]) { return $false }
    }
    return $true
}

function Assert-AuditedPatchManifest {
    param($Manifest = $Script:VoicePatchManifest,
          [string]$ExpectedHash = $Script:AuditedPatchPlanHash)
    if ($manifest.schema -ne 'discord-voice-patch-manifest-v6' -or $manifest.complete -ne $true -or
        $manifest.total_expected -ne 20 -or @($manifest.patches).Count -ne 20 -or @($manifest.missing).Count -gt 0) {
        throw 'The manifest must contain all 20 validated sites.'
    }
    if ($manifest.original_sha256 -notmatch '^[0-9a-fA-F]{64}$' -or [long]$manifest.file_size -le 0) {throw 'Invalid build identity.'}
    $names = @($manifest.patches | ForEach-Object {[string]$_.name})
    if (@($names | Select-Object -Unique).Count -ne $names.Count) {throw 'Duplicate patch site names.'}
    $lines = [System.Collections.Generic.List[string]]::new()
    foreach ($value in @($manifest.schema,$manifest.profile,[string]$manifest.file_size,$manifest.original_sha256.ToLowerInvariant())) { $lines.Add([string]$value) }
    if($manifest.target_bitrate_bps -notin @(248000,320000)){throw 'Invalid bitrate test profile: expected 248000 or 320000 bps.'}
    $lines.Add([string]$manifest.target_bitrate_bps)
    if($manifest.target_bitrate_bps -ne 320000 -or $manifest.bitrate_mode -notin @('cbr','negotiated')) {throw 'Expected a complete 320 kbps CBR/comparison profile.'}
    $lines.Add([string]$manifest.bitrate_mode)
    if($manifest.target_bitrate_bps -ne 320000 -or $manifest.bitrate_mode -ne 'cbr') {throw 'Expected the current 320 kbps CBR profile.'}
    if(@($manifest.patches).Count -ne 20 -or @($manifest.patches | Where-Object {$_.kind -and $_.kind -ne 'copy_gain'}).Count -gt 0) {throw 'Expected exactly the 20 current active patches.'}
    $endOfPrevious = -1L
    foreach ($site in @($manifest.patches | Sort-Object { [long]$_.file_offset })) {
        $offset = [long]$site.file_offset
        $length = [int]$site.length
        if ($length -le 0 -or $offset -lt 0 -or $offset+$length -gt [long]$manifest.file_size -or $offset -lt $endOfPrevious) {throw "Invalid patch span: $($site.name)"}
        $endOfPrevious = $offset+$length
        foreach ($value in @($site.expected_original,$site.patch)+@($site.accepted_legacy)) {
            if ($value -and (Convert-HexBytes $value).Length -ne $length) {throw "Invalid patch byte length: $($site.name)"}
        }
        if ($site.kind -eq 'copy_gain') {
            for ($gain=1; $gain -le 10; $gain++) {
                $variant = $site.gain_patches.PSObject.Properties[[string]$gain]
                if (-not $variant -or (Convert-HexBytes $variant.Value).Length -ne $length) {throw 'Missing or invalid gain variant.'}
            }
        }
        $fields = [System.Collections.Generic.List[string]]::new()
        foreach ($value in @([string]$site.name,[string]$site.group,[string][Convert]::ToInt64($site.rva,16),
            [string]$site.file_offset,[string]$site.length,($site.expected_original -replace '\s','').ToUpperInvariant(),
            ($site.patch -replace '\s','').ToUpperInvariant(),$(if ($site.optional) {'1'} else {'0'}),[string]$site.kind)) {
            $fields.Add([string]$value)
        }
        for ($gain=1; $gain -le 10; $gain++) {
            $variant = ''
            if ($site.gain_patches) {
                $entry = $site.gain_patches.PSObject.Properties[[string]$gain]
                if ($entry) { $variant = ($entry.Value -replace '\s','').ToUpperInvariant() }
            }
            $fields.Add($variant)
        }
        for ($gain=1; $gain -le 10; $gain++) {
            $variant=''
            if ($site.legacy_gain_patches) {
                $entry=$site.legacy_gain_patches.PSObject.Properties[[string]$gain]
                if($entry){$variant=($entry.Value -replace '\s','').ToUpperInvariant()}
            }
            $fields.Add($variant)
        }
        $fields.Add((@($site.accepted_legacy | ForEach-Object { ($_ -replace '\s','').ToUpperInvariant() }) -join ','))
        $lines.Add(($fields -join '|'))
    }
    $fingerprint = Get-BytesSha256 ([Text.Encoding]::UTF8.GetBytes(($lines -join "`n")))
    if ($fingerprint -ne $ExpectedHash) {
        throw 'Patch offsets or bytes differ from the audited plan; no changes written. Update the full profile with the verified offset finder.'
    }
}

function Assert-VoiceProfileBank {
    if ($Script:VoiceProfileBank.schema -ne 'discord-voice-profile-bank-v1' -or @($Script:VoiceProfileBank.profiles).Count -lt 1) {throw 'Missing or invalid voice build bank.'}
    $identities = @{}
    $referenceNames = @($Script:RequiredOffsetNames | Sort-Object)
    foreach ($entry in $Script:VoiceProfileBank.profiles) {
        Assert-AuditedPatchManifest -Manifest $entry.manifest -ExpectedHash $entry.plan_sha256
        $identity = [string]$entry.manifest.original_sha256
        if ($identities.ContainsKey($identity)) {throw 'Duplicate build identities in profile bank.'}
        $identities[$identity] = $true
        $names = @($entry.manifest.patches | ForEach-Object {[string]$_.name} | Sort-Object)
        if (Compare-Object $referenceNames $names) {throw 'Build profiles must support the same patch controls.'}
    }
}

function Find-VoiceBuildProfile {
    param([byte[]]$Bytes)
    Assert-VoiceProfileBank
    $matches = @()
    foreach ($entry in $Script:VoiceProfileBank.profiles) {
        $image = Get-VoiceImageForProfile -Bytes $Bytes -Manifest $entry.manifest
        if ($null -ne $image) {$matches += [pscustomobject]@{Entry=$entry;Image=$image}}
    }
    if ($matches.Count -eq 0) {
        throw "No saved profile matches this voice build (SHA256 $(Get-BytesSha256 $Bytes)). Run the offset finder on this node and update this patcher's build bank. No bytes written."
    }
    if ($matches.Count -ne 1) {throw 'Ambiguous build profiles; no bytes written.'}
    return $matches[0]
}

function Set-ActiveVoiceProfile {
    param($Entry)
    $Script:VoicePatchManifest = $Entry.manifest
    $Script:AuditedPatchPlanHash = $Entry.plan_sha256
    $Script:ExpectedPatchSiteCount = [int]$Entry.manifest.total_expected
    foreach ($site in $Entry.manifest.patches) {
        $Script:Offsets[[string]$site.name] = [Convert]::ToInt64($site.rva,16)
    }
    $Script:OffsetsMeta.FinderVersion = $Entry.manifest.version
    $Script:OffsetsMeta.DiscordAppVersion = $Entry.manifest.discord_app_version
    $Script:OffsetsMeta.Size = $Entry.manifest.file_size
    $Script:OffsetsMeta.MD5 = $Entry.manifest.original_md5
    $Script:Config.Bitrate = [int]($Entry.manifest.target_bitrate_bps/1000)
}

function Invoke-VoiceNodePatch {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$NodePath, [string]$OutputPath,
          [string]$ClientName, [switch]$DryRun, [switch]$RestoreStock)
    $sourcePath = (Resolve-Path -LiteralPath $NodePath).ProviderPath
    [byte[]]$inputBytes = [IO.File]::ReadAllBytes($sourcePath)
    $match = Find-VoiceBuildProfile $inputBytes
    Set-ActiveVoiceProfile $match.Entry
    $manifest = $Script:VoicePatchManifest
    Write-Log ("Build profile selected: {0} | app {1}" -f $manifest.profile,(Get-DiscordAppVersion $sourcePath)) -Level Info
    $AudioGainMultiplier = [int]$Script:Config.AudioGainMultiplier
    if ($AudioGainMultiplier -lt 1 -or $AudioGainMultiplier -gt 10) { throw 'Gain must be between 1 and 10.' }
    if ($manifest.schema -ne 'discord-voice-patch-manifest-v6' -or $manifest.complete -ne $true) { throw 'A complete v6 patch manifest is required.' }
    if (@($manifest.patches).Count -ne [int]$manifest.total_expected -or @($manifest.missing).Count -gt 0) { throw 'The manifest is incomplete.' }
    $names = @($manifest.patches | ForEach-Object { [string]$_.name })
    if (@($names | Select-Object -Unique).Count -ne $names.Count) { throw 'Duplicate patch site names.' }
    if ($inputBytes.LongLength -ne [long]$manifest.file_size) { throw "Unsupported voice build: installed app $(Get-DiscordAppVersion $sourcePath); profile $($manifest.profile) expects $($manifest.file_size) bytes, found $($inputBytes.LongLength). Run the finder for this node; no bytes written." }
    [byte[]]$normalizedBytes = $inputBytes.Clone()
    [byte[]]$outputBytes = $inputBytes.Clone()
    $originalInputHash = Get-BytesSha256 $inputBytes
    $orderedSites = @($manifest.patches | Sort-Object { [long]$_.file_offset })
    $endOfPrevious = -1L
    $enabledCount = 0
    foreach ($site in $orderedSites) {
        $offset = [long]$site.file_offset
        $length = [int]$site.length
        if ($length -le 0 -or $offset -lt 0 -or $offset+$length -gt $inputBytes.LongLength -or $offset -lt $endOfPrevious) {
            throw "Invalid or overlapping patch span: $($site.name)"
        }
        $endOfPrevious = $offset+$length
        [byte[]]$expected = Convert-HexBytes $site.expected_original
        [byte[]]$replacement = Convert-HexBytes $site.patch
        if ($expected.Length -ne $length -or $replacement.Length -ne $length) { throw "Length mismatch: $($site.name)" }
        if (-not $Script:SelectedPatches.ContainsKey([string]$site.name)) { throw "Unknown patch site: $($site.name)" }
        $recognized = (Test-BytesAt $inputBytes $offset $expected) -or (Test-BytesAt $inputBytes $offset $replacement)
        foreach($legacy in @($site.accepted_legacy)){if($legacy -and (Test-BytesAt $inputBytes $offset (Convert-HexBytes $legacy))){$recognized=$true}}
        if ($site.kind -eq 'copy_gain') {
            foreach ($variant in $site.gain_patches.PSObject.Properties) {
                [byte[]]$variantBytes = Convert-HexBytes $variant.Value
                if ($variantBytes.Length -ne $length) { throw 'Invalid gain variant length.' }
                if (Test-BytesAt $inputBytes $offset $variantBytes) { $recognized = $true }
            }
            $selectedVariant = $site.gain_patches.PSObject.Properties[[string]$AudioGainMultiplier]
            if ($null -eq $selectedVariant) { throw 'Selected gain is missing from the manifest.' }
            $replacement = Convert-HexBytes $selectedVariant.Value
        }
        if (-not $recognized) { throw "Unexpected instruction bytes at $($site.name) (RVA $($site.rva)); no changes written." }
        if ($Script:DebugModeActive) {
            $state = if ($RestoreStock -or -not $Script:SelectedPatches[[string]$site.name]) { 'STOCK' } else { 'PATCH' }
            Write-Log ("[{0}] {1} | RVA {2} | file 0x{3:X} | {4} bytes" -f $state,$site.name,$site.rva,$offset,$length) -Level Info
        }
        [Array]::Copy($expected,0,$normalizedBytes,$offset,$length)
        if ($RestoreStock -or -not $Script:SelectedPatches[[string]$site.name]) {
            [Array]::Copy($expected,0,$outputBytes,$offset,$length)
        } else {
            [Array]::Copy($replacement,0,$outputBytes,$offset,$length)
            $enabledCount++
        }
    }
    if ((Get-BytesSha256 $normalizedBytes) -ne $manifest.original_sha256) {
        throw "Voice build changed or does not match $($manifest.profile); no bytes written. Run the offset finder on this node and update the build bank."
    }
    $targetPath = $sourcePath
    if ($OutputPath) { $targetPath = [IO.Path]::GetFullPath($OutputPath) }
    $outputHash = Get-BytesSha256 $outputBytes
    $summary = [ordered]@{
        Profile = $manifest.profile
        VerifiedSites = $orderedSites.Count
        EnabledSites = $(if ($RestoreStock) { 0 } else { $enabledCount })
        BitrateMode = [string]$manifest.bitrate_mode
        TargetBitrateBps = [int]$manifest.target_bitrate_bps
        Gain = $AudioGainMultiplier
        Restoring = $RestoreStock.IsPresent
        Source = $sourcePath
        Destination = $targetPath
        InputSha256 = $originalInputHash
        OutputSha256 = $outputHash
        DryRun = $DryRun.IsPresent
    }
    if ($DryRun) {
        Write-Log 'Validation passed. Dry run: no files changed.' -Level Success
        return [pscustomobject]$summary
    }
    $targetDirectory = [IO.Path]::GetDirectoryName($targetPath)
    if (-not (Test-Path -LiteralPath $targetDirectory -PathType Container)) { throw 'The output folder does not exist.' }
    $existingTargetHash=$null
    if(Test-Path -LiteralPath $targetPath){$existingTargetHash=Get-BytesSha256 ([IO.File]::ReadAllBytes($targetPath))}
    $changed=Invoke-AtomicVoiceWrite -SourcePath $sourcePath -TargetPath $targetPath -ExpectedSourceHash $originalInputHash -ExpectedTargetHash $existingTargetHash -OutputBytes $outputBytes -NormalizedBytes $normalizedBytes -ClientName $ClientName
    if(-not $changed){
        $message=if($RestoreStock){'The node is already stock; original bytes verified.'}else{'The selected settings are already applied; stable source verified.'}
        Write-Log $message -Level Success
        return [pscustomobject]$summary
    }
    Write-Log $(if ($RestoreStock) { 'Stock node restored and verified.' } else { 'Patches applied and verified.' }) -Level Success
    return [pscustomobject]$summary
}

function Get-RequestedClients {
    $clients=@(Get-InstalledClients)
    if($FixClient){
        $query=($FixClient -replace '[^a-zA-Z0-9]','').ToLowerInvariant()
        $clients=@($clients | Where-Object {(($_.Name -replace '[^a-zA-Z0-9]','').ToLowerInvariant()).Contains($query)})
    }
    return @(Get-UniqueClientsByAppPath -Clients $clients)
}

function Start-Patching {
    Assert-VoiceProfileBank
    if($NodePath){
        $Script:Config.LogFile=$null
        $result=Invoke-VoiceNodePatch -NodePath $NodePath -OutputPath $OutputPath -DryRun:$DryRun -RestoreStock:$Restore
        if($Restore){
            Write-Host ("{0}/{0} sites verified | Stock node{1}" -f $result.VerifiedSites,$(if($DryRun){' restoration validated (dry run)'}else{' verified'}))
        }else{
            Write-Host ("{0}/{0} sites verified | {1} patches enabled | Gain {2}x | profile {3} kbps ({4})" -f $result.VerifiedSites,$result.EnabledSites,$result.Gain,($result.TargetBitrateBps/1000),$result.BitrateMode)
        }
        Write-Host ('SHA256: '+$result.OutputSha256)
        return $true
    }
    if($OutputPath -or $DryRun){throw '-OutputPath/-DryRun require -NodePath.'}
    Initialize-Environment
    Write-Banner
    $localOnly = $PatchLocalOnly.IsPresent
    if($ListBackups){$Script:LastAction='ListBackups';Show-BackupList;return $true}
    $clients=@();$action='Patch'
    if($FixAll -or $FixClient){$clients=@(Get-RequestedClients);if($Restore){$action='RestoreStock'}}
    elseif($Restore){
        $clients=@(Get-RequestedClients)
        if($clients.Count -ne 1){throw 'Select a client in the GUI, use -FixClient with -Restore, or use -NodePath -Restore.'}
        $action='RestoreStock'
    }else{
        if($NonInteractive){throw 'Specify -NodePath, -FixAll, -FixClient or -ListBackups for non-interactive use.'}
        $choice=Show-ConfigurationGUI
        if(-not $choice){$Script:LastAction='Cancel';return $false}
        $action=$choice.Action
        $Script:Config.SkipBackup=[bool]$choice.SkipBackup
        $Script:Config.AutoRelaunch=[bool]$choice.AutoRelaunch
        $localOnly = $PatchLocalOnly.IsPresent -or [bool]$choice.PatchLocalOnly
        if($choice.Multiplier){$Script:Config.AudioGainMultiplier=[int]$choice.Multiplier}
        Set-PatchSelection -DebugMode:([bool]$choice.DebugMode) -Selection $choice.SelectedPatches
        if($Script:DebugModeActive){Write-DebugPatchSelectionLog}
        if($action -eq 'PatchAll'){$clients=@(Get-UniqueClientsByAppPath -Clients @(Get-InstalledClients));$action='Patch'}
        else{$clients=@(Get-InstalledClients | Where-Object {$_.Index -eq $choice.ClientIndex})}
    }
    $Script:LastAction=$action
    if(-not $clients.Count){Write-Log 'No matching installed clients found.' -Level Error;return $false}
    if($action -eq 'RestoreStock'){
        Write-Host 'Restoring stock node (original, unpatched bytes).' -ForegroundColor Cyan
    }elseif($action -eq 'RestoreBackup'){
        Write-Host 'Restoring the selected backup.' -ForegroundColor Cyan
    }else{Show-Settings}
    if($action -eq 'Patch'){
        Write-Log $(if($localOnly){'Using installed files; GitHub module download disabled.'}else{'Using the same verified Stable module from GitHub for every selected client.'}) -Level Info
        $result=Invoke-PatchClients -Clients $clients -PatchLocalOnly:$localOnly
    }
    else{
        $good=[Collections.ArrayList]::new();$bad=[Collections.ArrayList]::new()
        foreach($client in $clients){
            try{
                $ok=if($action -eq 'RestoreStock'){Restore-ClientStock $client}else{Restore-FromBackup -Client $client}
                if($ok){[void]$good.Add($client)}else{[void]$bad.Add($client.Name)}
            }catch{Write-Log ([string]$_) -Level Error;[void]$bad.Add($client.Name)}
        }
        $result=@{Success=$good.Count;Total=$clients.Count;SucceededClients=@($good);Failed=@($bad)}
    }
    $status=if($result.Success -eq $result.Total){'COMPLETE'}elseif($result.Success){'PARTIALLY COMPLETE'}else{'FAILED'}
    $level=if($status -eq 'COMPLETE'){'Success'}else{'Warning'}
    $actionLabel=switch($action){'RestoreStock'{'STOCK RESTORE'} 'RestoreBackup'{'BACKUP RESTORE'} default{'PATCH'}}
    Write-Log ("=== $actionLabel $status === $($result.Success)/$($result.Total)") -Level $level
    if($Script:Config.AutoRelaunch){foreach($client in $result.SucceededClients){Start-DiscordClient $client}}
    if($result.Success -gt 0){Save-UserConfig}
    return ($result.Total -gt 0 -and $result.Success -eq $result.Total)
}

try {
    $success=Start-Patching
    if($Script:LastAction -eq 'Cancel'){Write-Host 'Cancelled.';exit 0}
    Write-Host $(if($success){'SUCCESS!'}else{'FAILED'})
    if(-not $NodePath -and -not $NonInteractive){Wait-EnterOrTimeout}
    exit $(if($success){0}else{1})
}catch{
    Write-Host "ERROR: $_" -ForegroundColor Red
    if(-not $NodePath -and -not $NonInteractive){Wait-EnterOrTimeout}
    exit 1
}
