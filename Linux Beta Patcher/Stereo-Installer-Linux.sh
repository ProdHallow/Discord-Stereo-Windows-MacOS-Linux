#!/usr/bin/env bash
###############################################################################
# DISCORD VOICE FIXER — Stereo Audio Module Installer (Linux)
# Downloads and installs pre-patched stereo voice modules
# Usage: ./DiscordVoiceFixer_linux.sh [--silent] [--check] [--restore] [--help]
# Made by: Oracle | Shaun | Hallow | Ascend | Sentry | Sikimzo | Cypher
###############################################################################
set -euo pipefail

SCRIPT_VERSION="1.0"

# ─── Configuration ────────────────────────────────────────────────────────────
# PLACEHOLDER: Update these URLs when repos are created
VOICE_BACKUP_API="https://api.github.com/repos/ProdHallow/PLACEHOLDER-linux-voice-backup/contents/Discord%20Voice%20Backup"
SETTINGS_JSON_URL="https://raw.githubusercontent.com/ProdHallow/PLACEHOLDER-linux-voice-backup/main/settings.json"
UPDATE_URL="https://raw.githubusercontent.com/ProdHallow/PLACEHOLDER-linux-voice-backup/main/DiscordVoiceFixer_linux.sh"

SAMPLE_RATE=48000
BITRATE=512

APP_DATA_ROOT="$HOME/.cache/DiscordVoiceFixer"
BACKUP_ROOT="$APP_DATA_ROOT/backups"
ORIGINAL_BACKUP_ROOT="$APP_DATA_ROOT/original_discord_modules"
STATE_FILE="$APP_DATA_ROOT/state.json"
LOG_FILE="$APP_DATA_ROOT/debug.log"
MAX_BACKUPS_PER_CLIENT=1

# ─── Colors ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'
MAGENTA='\033[0;35m'; WHITE='\033[1;37m'; DIM='\033[0;90m'; BLUE='\033[0;34m'
BOLD='\033[1m'; NC='\033[0m'; ORANGE='\033[0;33m'

# ─── CLI Flags ────────────────────────────────────────────────────────────────
SILENT_MODE=false
CHECK_ONLY=false
RESTORE_MODE=false
FIX_CLIENT=""

for arg in "$@"; do
    case "$arg" in
        --silent|-s)   SILENT_MODE=true ;;
        --check|-c)    CHECK_ONLY=true ;;
        --restore|-r)  RESTORE_MODE=true ;;
        --fix=*)       FIX_CLIENT="${arg#--fix=}" ;;
        --help|-h)
            echo "Discord Voice Fixer — Linux Installer v${SCRIPT_VERSION}"
            echo ""
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --silent, -s      Run silently (no prompts, fix all clients)"
            echo "  --check, -c       Check Discord versions and fix status"
            echo "  --restore, -r     Restore original voice modules"
            echo "  --fix=<name>      Fix only the client matching <name>"
            echo "  --help, -h        Show this help"
            echo ""
            echo "Examples:"
            echo "  $0                # Interactive mode"
            echo "  $0 --silent       # Auto-fix all clients"
            echo "  $0 --check        # Check status"
            echo "  $0 --restore      # Restore from backup"
            exit 0
            ;;
    esac
done

# ─── Logging ──────────────────────────────────────────────────────────────────
ensure_dir() { [[ -d "$1" ]] || mkdir -p "$1" 2>/dev/null || true; }

log_file() {
    ensure_dir "$(dirname "$LOG_FILE")"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [$1] $2" >> "$LOG_FILE" 2>/dev/null || true
}

status() {
    local color="$NC" level="INFO"
    case "${2:-}" in
        red)     color="$RED";     level="ERROR" ;;
        green)   color="$GREEN";   level="OK" ;;
        yellow)  color="$YELLOW";  level="WARN" ;;
        cyan)    color="$CYAN";    level="INFO" ;;
        blue)    color="$BLUE";    level="INFO" ;;
        magenta) color="$MAGENTA"; level="INFO" ;;
        orange)  color="$ORANGE";  level="WARN" ;;
        dim)     color="$DIM";     level="INFO" ;;
    esac
    log_file "$level" "$1"
    if ! $SILENT_MODE || [[ "$level" == "ERROR" ]] || [[ "$level" == "OK" ]]; then
        echo -e "${DIM}[$(date '+%H:%M:%S')]${NC} ${color}${1}${NC}"
    fi
}

banner() {
    echo ""
    echo -e "${CYAN}╔══════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║${NC}  ${WHITE}${BOLD}Discord Voice Fixer${NC} — ${CYAN}Linux Installer v${SCRIPT_VERSION}${NC}      ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}  ${DIM}48kHz | 512kbps | True Stereo | Filterless${NC}      ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}  ${DIM}Oracle | Shaun | Hallow | Ascend | Sentry${NC}       ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}  ${DIM}Sikimzo | Cypher${NC}                                ${CYAN}║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════════╝${NC}"
    echo ""
}

# ─── Dependency Check ─────────────────────────────────────────────────────────
check_dependencies() {
    local missing=()
    command -v curl  &>/dev/null || missing+=("curl")
    command -v jq    &>/dev/null || missing+=("jq")
    command -v md5sum &>/dev/null || missing+=("coreutils (md5sum)")

    if [[ ${#missing[@]} -gt 0 ]]; then
        status "[X] Missing dependencies: ${missing[*]}" red
        echo ""
        echo "Install with:"
        echo "  Ubuntu/Debian:  sudo apt install ${missing[*]}"
        echo "  Fedora/RHEL:    sudo dnf install ${missing[*]}"
        echo "  Arch:           sudo pacman -S ${missing[*]}"
        exit 1
    fi
}

# ─── Discord Client Detection ────────────────────────────────────────────────
declare -a CLIENT_NAMES=()
declare -a CLIENT_PATHS=()
declare -a CLIENT_APP_PATHS=()
declare -a CLIENT_VOICE_PATHS=()
declare -a CLIENT_VERSIONS=()
declare -a CLIENT_PROCESS_NAMES=()

# Search paths and labels
declare -a SEARCH_PATHS=(
    "$HOME/.config/discord"
    "$HOME/.config/discordcanary"
    "$HOME/.config/discordptb"
    "$HOME/.config/discorddevelopment"
    "$HOME/.var/app/com.discordapp.Discord/config/discord"
    "/snap/discord/current/usr/share/discord/resources"
    "/opt/discord/resources"
    "/opt/discord-canary/resources"
    "/opt/discord-ptb/resources"
    "/usr/share/discord/resources"
    "/usr/lib/discord/resources"
)

declare -a SEARCH_NAMES=(
    "Discord Stable"
    "Discord Canary"
    "Discord PTB"
    "Discord Development"
    "Discord (Flatpak)"
    "Discord (Snap)"
    "Discord (/opt)"
    "Discord Canary (/opt)"
    "Discord PTB (/opt)"
    "Discord (/usr/share)"
    "Discord (/usr/lib)"
)

declare -a SEARCH_PROCESSES=(
    "Discord"
    "DiscordCanary"
    "DiscordPTB"
    "DiscordDevelopment"
    "Discord"
    "Discord"
    "Discord"
    "DiscordCanary"
    "DiscordPTB"
    "Discord"
    "Discord"
)

find_voice_module() {
    local base="$1"
    # Pattern 1: Electron auto-update structure (config dir with app-*/modules/discord_voice/)
    local app_dirs
    app_dirs=$(find "$base" -maxdepth 1 -type d -name "app-*" 2>/dev/null | sort -V -r)
    if [[ -n "$app_dirs" ]]; then
        while IFS= read -r app_dir; do
            local modules_dir="$app_dir/modules"
            if [[ -d "$modules_dir" ]]; then
                local voice_dir
                voice_dir=$(find "$modules_dir" -maxdepth 1 -type d -name "discord_voice*" 2>/dev/null | head -1)
                if [[ -n "$voice_dir" ]]; then
                    # Check for nested discord_voice/ subfolder
                    if [[ -d "$voice_dir/discord_voice" ]]; then
                        echo "$voice_dir/discord_voice|$app_dir"
                    else
                        echo "$voice_dir|$app_dir"
                    fi
                    return 0
                fi
            fi
        done <<< "$app_dirs"
    fi

    # Pattern 2: Direct search for discord_voice.node
    local node_file
    node_file=$(find "$base" -maxdepth 6 -name "discord_voice.node" -type f 2>/dev/null | head -1)
    if [[ -n "$node_file" ]]; then
        local voice_dir
        voice_dir=$(dirname "$node_file")
        echo "$voice_dir|$base"
        return 0
    fi

    return 1
}

get_app_version() {
    local app_path="$1"
    if [[ "$app_path" =~ app-([0-9.]+) ]]; then
        echo "${BASH_REMATCH[1]}"
    else
        echo "Unknown"
    fi
}

find_discord_clients() {
    CLIENT_NAMES=()
    CLIENT_PATHS=()
    CLIENT_APP_PATHS=()
    CLIENT_VOICE_PATHS=()
    CLIENT_VERSIONS=()
    CLIENT_PROCESS_NAMES=()

    local found_voice_paths=()

    for i in "${!SEARCH_PATHS[@]}"; do
        local base="${SEARCH_PATHS[$i]}"
        local name="${SEARCH_NAMES[$i]}"
        local proc="${SEARCH_PROCESSES[$i]}"

        [[ -d "$base" ]] || continue

        local result
        if result=$(find_voice_module "$base"); then
            local voice_path="${result%%|*}"
            local app_path="${result##*|}"

            # Deduplicate by voice path
            local dup=false
            for fvp in "${found_voice_paths[@]:-}"; do
                [[ "$fvp" == "$voice_path" ]] && { dup=true; break; }
            done
            $dup && continue

            local version
            version=$(get_app_version "$app_path")

            CLIENT_NAMES+=("$name")
            CLIENT_PATHS+=("$base")
            CLIENT_APP_PATHS+=("$app_path")
            CLIENT_VOICE_PATHS+=("$voice_path")
            CLIENT_VERSIONS+=("$version")
            CLIENT_PROCESS_NAMES+=("$proc")
            found_voice_paths+=("$voice_path")
        fi
    done

    return 0
}

# ─── Process Management ──────────────────────────────────────────────────────
kill_discord() {
    local procs=("Discord" "DiscordCanary" "DiscordPTB" "DiscordDevelopment" "discord")
    for pname in "${procs[@]}"; do
        pkill -f "$pname" 2>/dev/null || true
    done
    sleep 2
    for pname in "${procs[@]}"; do
        pkill -9 -f "$pname" 2>/dev/null || true
    done
    sleep 1
}

is_discord_running() {
    pgrep -f "Discord|discord" &>/dev/null
}

# ─── State Management ────────────────────────────────────────────────────────
ensure_app_dirs() {
    ensure_dir "$APP_DATA_ROOT"
    ensure_dir "$BACKUP_ROOT"
    ensure_dir "$ORIGINAL_BACKUP_ROOT"
}

sanitize_name() {
    echo "$1" | tr ' ' '_' | tr -d '[]()/' | tr '-' '_'
}

get_state_value() {
    local key="$1" field="$2"
    if [[ -f "$STATE_FILE" ]]; then
        jq -r ".\"$key\".\"$field\" // empty" "$STATE_FILE" 2>/dev/null || echo ""
    fi
}

save_fix_state() {
    local client_name="$1" version="$2"
    local key
    key=$(sanitize_name "$client_name")
    local fix_date
    fix_date=$(date -Iseconds)

    ensure_app_dirs

    if [[ -f "$STATE_FILE" ]]; then
        local tmp
        tmp=$(mktemp)
        jq --arg k "$key" --arg v "$version" --arg d "$fix_date" \
            '.[$k] = {"LastFixedVersion": $v, "LastFixDate": $d}' \
            "$STATE_FILE" > "$tmp" 2>/dev/null && mv "$tmp" "$STATE_FILE"
    else
        jq -n --arg k "$key" --arg v "$version" --arg d "$fix_date" \
            '{($k): {"LastFixedVersion": $v, "LastFixDate": $d}}' \
            > "$STATE_FILE"
    fi
}

check_discord_updated() {
    local client_name="$1" current_version="$2"
    local key
    key=$(sanitize_name "$client_name")
    local last_version
    last_version=$(get_state_value "$key" "LastFixedVersion")
    local last_date
    last_date=$(get_state_value "$key" "LastFixDate")

    if [[ -z "$last_version" ]]; then
        echo "NEW"
        return
    fi

    if [[ "$current_version" != "$last_version" ]]; then
        echo "UPDATED|$last_version|$current_version|$last_date"
        return
    fi

    echo "OK|$current_version|$last_date"
}

# ─── Backup Management ───────────────────────────────────────────────────────
backup_has_content() {
    local backup_path="$1"
    local voice_dir="$backup_path/voice_module"
    [[ -d "$voice_dir" ]] || return 1
    local count
    count=$(find "$voice_dir" -type f \( -name "*.node" -o -name "*.so" -o -name "*.dll" \) 2>/dev/null | wc -l)
    [[ $count -gt 0 ]] || return 1
    return 0
}

create_original_backup() {
    local voice_path="$1" client_name="$2" version="$3"
    local sname
    sname=$(sanitize_name "$client_name")
    local backup_path="$ORIGINAL_BACKUP_ROOT/$sname"

    if [[ -d "$backup_path" ]]; then
        status "  Original backup already exists, skipping..." yellow
        return 0
    fi

    if [[ ! -d "$voice_path" ]]; then
        status "  [!] Voice folder does not exist: $voice_path" orange
        return 1
    fi

    local file_count
    file_count=$(find "$voice_path" -type f 2>/dev/null | wc -l)
    if [[ $file_count -eq 0 ]]; then
        status "  [!] Voice folder is empty, cannot create backup" orange
        return 1
    fi

    ensure_dir "$backup_path/voice_module"
    cp -r "$voice_path"/* "$backup_path/voice_module/" 2>/dev/null

    if ! backup_has_content "$backup_path"; then
        status "  [!] Backup validation failed" orange
        rm -rf "$backup_path"
        return 1
    fi

    local total_size
    total_size=$(du -sh "$backup_path/voice_module" 2>/dev/null | cut -f1)

    cat > "$backup_path/metadata.json" << EOF
{
    "ClientName": "$client_name",
    "AppVersion": "$version",
    "BackupDate": "$(date -Iseconds)",
    "IsOriginal": true,
    "Description": "Original Discord modules - preserved for reverting to mono audio",
    "FileCount": $file_count,
    "Platform": "linux"
}
EOF

    status "  [OK] Original backup created: $sname ($file_count files, $total_size)" magenta
    status "       This backup will NEVER be deleted automatically" cyan
    return 0
}

create_voice_backup() {
    local voice_path="$1" client_name="$2" version="$3"
    local sname
    sname=$(sanitize_name "$client_name")
    local timestamp
    timestamp=$(date '+%Y-%m-%d_%H%M%S')
    local backup_name="${sname}_${version}_${timestamp}"
    local backup_path="$BACKUP_ROOT/$backup_name"

    # Ensure original backup exists first
    local orig_path="$ORIGINAL_BACKUP_ROOT/$sname"
    if [[ ! -d "$orig_path" ]]; then
        create_original_backup "$voice_path" "$client_name" "$version"
    fi

    if [[ ! -d "$voice_path" ]]; then
        status "  [!] Voice folder does not exist" orange
        return 1
    fi

    local file_count
    file_count=$(find "$voice_path" -type f 2>/dev/null | wc -l)
    if [[ $file_count -eq 0 ]]; then
        status "  [!] Voice folder is empty" orange
        return 1
    fi

    ensure_dir "$backup_path/voice_module"
    cp -r "$voice_path"/* "$backup_path/voice_module/" 2>/dev/null

    if ! backup_has_content "$backup_path"; then
        status "  [!] Backup validation failed" orange
        rm -rf "$backup_path"
        return 1
    fi

    cat > "$backup_path/metadata.json" << EOF
{
    "ClientName": "$client_name",
    "AppVersion": "$version",
    "BackupDate": "$(date -Iseconds)",
    "IsOriginal": false,
    "FileCount": $file_count,
    "Platform": "linux"
}
EOF

    status "  [OK] Backup created: $backup_name ($file_count files)" green
    return 0
}

remove_old_backups() {
    # Keep only the most recent backup per client
    local clients=()
    for dir in "$BACKUP_ROOT"/*/; do
        [[ -d "$dir" ]] || continue
        local meta="$dir/metadata.json"
        [[ -f "$meta" ]] || continue
        local cn
        cn=$(jq -r '.ClientName // empty' "$meta" 2>/dev/null)
        [[ -n "$cn" ]] || continue

        local found=false
        for c in "${clients[@]:-}"; do
            [[ "$c" == "$cn" ]] && { found=true; break; }
        done
        $found || clients+=("$cn")
    done

    for cn in "${clients[@]:-}"; do
        local dirs=()
        for dir in "$BACKUP_ROOT"/*/; do
            [[ -d "$dir" ]] || continue
            local meta="$dir/metadata.json"
            [[ -f "$meta" ]] || continue
            local this_cn
            this_cn=$(jq -r '.ClientName // empty' "$meta" 2>/dev/null)
            [[ "$this_cn" == "$cn" ]] && dirs+=("$dir")
        done

        if [[ ${#dirs[@]} -gt $MAX_BACKUPS_PER_CLIENT ]]; then
            # Sort by modification time, newest first
            local sorted
            sorted=$(for d in "${dirs[@]}"; do echo "$d"; done | while read -r d; do
                stat -c '%Y %n' "$d" 2>/dev/null || echo "0 $d"
            done | sort -rn | tail -n +$(( MAX_BACKUPS_PER_CLIENT + 1 )) | cut -d' ' -f2-)

            while IFS= read -r old_dir; do
                [[ -n "$old_dir" ]] && rm -rf "$old_dir" 2>/dev/null
            done <<< "$sorted"
        fi
    done
}

list_backups() {
    local backups=()
    local idx=0

    # Original backups
    for dir in "$ORIGINAL_BACKUP_ROOT"/*/; do
        [[ -d "$dir" ]] || continue
        local meta="$dir/metadata.json"
        [[ -f "$meta" ]] || continue
        local cn av bd
        cn=$(jq -r '.ClientName // "Unknown"' "$meta" 2>/dev/null)
        av=$(jq -r '.AppVersion // "?"' "$meta" 2>/dev/null)
        bd=$(jq -r '.BackupDate // "?"' "$meta" 2>/dev/null)
        local bd_fmt
        bd_fmt=$(date -d "$bd" '+%b %d, %Y %H:%M' 2>/dev/null || echo "$bd")
        echo "ORIGINAL|$dir|$cn|$av|$bd_fmt"
        (( idx++ ))
    done

    # Regular backups (newest first)
    for dir in $(ls -dt "$BACKUP_ROOT"/*/ 2>/dev/null); do
        [[ -d "$dir" ]] || continue
        local meta="$dir/metadata.json"
        [[ -f "$meta" ]] || continue
        local cn av bd
        cn=$(jq -r '.ClientName // "Unknown"' "$meta" 2>/dev/null)
        av=$(jq -r '.AppVersion // "?"' "$meta" 2>/dev/null)
        bd=$(jq -r '.BackupDate // "?"' "$meta" 2>/dev/null)
        local bd_fmt
        bd_fmt=$(date -d "$bd" '+%b %d, %Y %H:%M' 2>/dev/null || echo "$bd")
        echo "BACKUP|$dir|$cn|$av|$bd_fmt"
        (( idx++ ))
    done
}

restore_from_backup() {
    local backup_path="$1" target_voice_path="$2" is_original="${3:-false}"
    local voice_backup="$backup_path/voice_module"

    if [[ ! -d "$voice_backup" ]]; then
        status "[X] Backup is corrupted: voice_module folder missing" red
        return 1
    fi

    if ! backup_has_content "$backup_path"; then
        status "[X] Backup is invalid: missing critical files" red
        return 1
    fi

    if [[ "$is_original" == "true" ]]; then
        status "  Restoring ORIGINAL voice module (reverting to mono)..." magenta
    else
        status "  Restoring voice module..." cyan
    fi

    # Clear target and copy
    if [[ -d "$target_voice_path" ]]; then
        rm -rf "$target_voice_path"/* 2>/dev/null
    else
        ensure_dir "$target_voice_path"
    fi

    cp -r "$voice_backup"/* "$target_voice_path"/

    local restored_count
    restored_count=$(find "$target_voice_path" -type f 2>/dev/null | wc -l)
    status "  [OK] Restored $restored_count files" cyan
    return 0
}

# ─── Download Voice Backup Files ─────────────────────────────────────────────
download_voice_files() {
    local dest_path="$1"
    local max_retries=3

    for (( attempt=1; attempt<=max_retries; attempt++ )); do
        if [[ $attempt -gt 1 ]]; then
            status "  Retry attempt $attempt of $max_retries..." yellow
            sleep 2
        fi

        status "  Fetching file list from GitHub..." cyan

        local api_response
        api_response=$(curl -sS --fail -L \
            -H "Accept: application/vnd.github.v3+json" \
            "$VOICE_BACKUP_API" 2>&1) || {
            if [[ "$api_response" == *"403"* ]]; then
                status "  [X] GitHub API rate limit exceeded. Try again later." red
                return 1
            fi
            if [[ $attempt -lt $max_retries ]]; then
                status "  [!] Attempt $attempt failed — retrying..." orange
                continue
            fi
            status "  [X] Failed to fetch file list after $max_retries attempts" red
            return 1
        }

        ensure_dir "$dest_path"

        local file_count=0
        local failed_files=()

        # Parse JSON array of files
        local file_names file_urls
        file_names=$(echo "$api_response" | jq -r '.[] | select(.type == "file") | .name' 2>/dev/null)
        file_urls=$(echo "$api_response" | jq -r '.[] | select(.type == "file") | .download_url' 2>/dev/null)

        if [[ -z "$file_names" ]]; then
            if [[ $attempt -lt $max_retries ]]; then
                status "  [!] Empty response, retrying..." orange
                continue
            fi
            status "  [X] GitHub repository response is empty" red
            return 1
        fi

        while IFS= read -r fname && IFS= read -r furl <&3; do
            status "  Downloading: $fname" cyan
            local fpath="$dest_path/$fname"

            if curl -sS --fail -L -o "$fpath" "$furl" 2>/dev/null; then
                if [[ ! -f "$fpath" ]] || [[ ! -s "$fpath" ]]; then
                    status "  [!] Downloaded file is empty: $fname" orange
                    failed_files+=("$fname")
                    continue
                fi

                local fsize
                fsize=$(stat -c%s "$fpath" 2>/dev/null || echo "0")
                local ext="${fname##*.}"
                if [[ "$ext" == "node" || "$ext" == "so" ]] && [[ $fsize -lt 1024 ]]; then
                    status "  [!] Warning: $fname seems too small ($fsize bytes)" orange
                fi

                (( file_count++ ))
            else
                status "  [!] Failed to download $fname" orange
                failed_files+=("$fname")
            fi
        done < <(echo "$file_names") 3< <(echo "$file_urls")

        if [[ $file_count -eq 0 ]]; then
            if [[ $attempt -lt $max_retries ]]; then
                status "  [!] No files downloaded, retrying..." orange
                continue
            fi
            status "  [X] No valid files were downloaded" red
            return 1
        fi

        if [[ ${#failed_files[@]} -gt 0 ]]; then
            status "  [!] Warning: ${#failed_files[@]} file(s) failed to download" orange
        fi

        status "  Downloaded $file_count voice backup files" cyan
        return 0
    done

    return 1
}

# ─── Verify Fix Status ───────────────────────────────────────────────────────
verify_fix() {
    local voice_path="$1" client_name="$2"
    local sname
    sname=$(sanitize_name "$client_name")
    local orig_path="$ORIGINAL_BACKUP_ROOT/$sname/voice_module"

    local node_file
    node_file=$(find "$voice_path" -name "*.node" -type f 2>/dev/null | head -1)
    if [[ -z "$node_file" ]]; then
        echo "ERROR|No .node file found in voice module"
        return
    fi

    local current_hash
    current_hash=$(md5sum "$node_file" 2>/dev/null | cut -d' ' -f1)

    if [[ -d "$orig_path" ]]; then
        local orig_node
        orig_node=$(find "$orig_path" -name "*.node" -type f 2>/dev/null | head -1)
        if [[ -n "$orig_node" ]]; then
            local orig_hash
            orig_hash=$(md5sum "$orig_node" 2>/dev/null | cut -d' ' -f1)
            if [[ "$current_hash" == "$orig_hash" ]]; then
                echo "NOTFIXED|Original mono modules detected|$current_hash"
                return
            else
                echo "FIXED|Stereo fix is applied|$current_hash"
                return
            fi
        fi
    fi

    echo "UNKNOWN|No original backup to compare — run fix first|$current_hash"
}

# ─── Fix a Single Client ─────────────────────────────────────────────────────
fix_client() {
    local idx="$1" download_path="$2"
    local name="${CLIENT_NAMES[$idx]}"
    local voice_path="${CLIENT_VOICE_PATHS[$idx]}"
    local app_path="${CLIENT_APP_PATHS[$idx]}"
    local version="${CLIENT_VERSIONS[$idx]}"

    status "" blue
    status "=== Fixing: $name ===" blue
    status "  Version: v$version" cyan
    status "  Voice module: $voice_path" cyan

    # Backup
    status "  Creating backup..." cyan
    create_voice_backup "$voice_path" "$name" "$version" || true

    # Ensure writable
    if [[ ! -w "$voice_path" ]]; then
        status "  File not writable, attempting chmod..." yellow
        chmod -R +w "$voice_path" 2>/dev/null || {
            status "  [X] Cannot make voice folder writable. Try: sudo chmod -R +w '$voice_path'" red
            return 1
        }
    fi

    # Clear and copy
    if [[ -d "$voice_path" ]]; then
        rm -rf "$voice_path"/* 2>/dev/null
    else
        ensure_dir "$voice_path"
    fi

    status "  Copying module files..." cyan
    cp -r "$download_path"/* "$voice_path"/

    # Verify copy
    local copied_count
    copied_count=$(find "$voice_path" -type f 2>/dev/null | wc -l)
    if [[ $copied_count -eq 0 ]]; then
        status "  [X] No files were copied to target" red
        return 1
    fi

    save_fix_state "$name" "$version"
    status "[OK] $name fixed successfully ($copied_count files)" green
    return 0
}

# ═══════════════════════════════════════════════════════════════════════════════
#  SILENT MODE
# ═══════════════════════════════════════════════════════════════════════════════
run_silent() {
    log_file "INFO" "Starting in silent mode"
    find_discord_clients

    if [[ ${#CLIENT_NAMES[@]} -eq 0 ]]; then
        echo "No Discord clients found."
        exit 1
    fi

    if $CHECK_ONLY; then
        echo "Checking Discord versions..."
        local needs_fix=false
        for i in "${!CLIENT_NAMES[@]}"; do
            local result
            result=$(check_discord_updated "${CLIENT_NAMES[$i]}" "${CLIENT_VERSIONS[$i]}")
            local rtype="${result%%|*}"
            case "$rtype" in
                NEW)     echo "[NEW] ${CLIENT_NAMES[$i]}: v${CLIENT_VERSIONS[$i]} — Never fixed"; needs_fix=true ;;
                UPDATED) echo "[UPDATE] ${CLIENT_NAMES[$i]}: ${result#UPDATED|}"; needs_fix=true ;;
                OK)      echo "[OK] ${CLIENT_NAMES[$i]}: ${result#OK|}" ;;
            esac
        done
        $needs_fix && exit 1 || exit 0
    fi

    # Filter by client name if specified
    if [[ -n "$FIX_CLIENT" ]]; then
        local filtered_idx=()
        for i in "${!CLIENT_NAMES[@]}"; do
            if [[ "${CLIENT_NAMES[$i]}" == *"$FIX_CLIENT"* ]]; then
                filtered_idx+=("$i")
            fi
        done
        if [[ ${#filtered_idx[@]} -eq 0 ]]; then
            echo "Client '$FIX_CLIENT' not found."
            exit 1
        fi
    fi

    # Download
    local tmp_dir
    tmp_dir=$(mktemp -d)
    trap "rm -rf '$tmp_dir'" EXIT

    local download_path="$tmp_dir/VoiceBackup"
    echo "Downloading voice modules..."
    if ! download_voice_files "$download_path"; then
        echo "[FAIL] Download failed"
        exit 1
    fi

    # Kill Discord
    kill_discord

    # Fix clients
    local success=0 failed=0
    local indices=("${filtered_idx[@]:-${!CLIENT_NAMES[@]}}")
    for i in "${indices[@]}"; do
        echo "Fixing ${CLIENT_NAMES[$i]} v${CLIENT_VERSIONS[$i]}..."
        if fix_client "$i" "$download_path"; then
            (( success++ ))
        else
            (( failed++ ))
        fi
    done

    remove_old_backups
    echo "Fixed $success of $(( success + failed )) client(s)"
    exit 0
}

# ═══════════════════════════════════════════════════════════════════════════════
#  RESTORE MODE
# ═══════════════════════════════════════════════════════════════════════════════
run_restore() {
    banner
    ensure_app_dirs
    find_discord_clients

    if [[ ${#CLIENT_NAMES[@]} -eq 0 ]]; then
        status "[X] No Discord clients found" red
        exit 1
    fi

    status "=== RESTORE MODE ===" blue

    # List available backups
    local backup_list
    backup_list=$(list_backups)
    if [[ -z "$backup_list" ]]; then
        status "[X] No backups found" red
        status "    You need to run the fix at least once to create a backup." yellow
        exit 1
    fi

    echo ""
    echo -e "  ${WHITE}Available backups:${NC}"
    echo ""
    local idx=0
    local backup_paths=()
    local backup_originals=()
    while IFS='|' read -r btype bpath bcn bav bdate; do
        (( idx++ ))
        backup_paths+=("$bpath")
        if [[ "$btype" == "ORIGINAL" ]]; then
            backup_originals+=("true")
            echo -e "  ${MAGENTA}[$idx] [ORIGINAL] $bcn v$bav — $bdate${NC}"
        else
            backup_originals+=("false")
            echo -e "  ${WHITE}[$idx]${NC} $bcn v$bav — $bdate"
        fi
    done <<< "$backup_list"

    echo ""
    read -rp "  Select backup (1-$idx, Enter to cancel): " sel

    if [[ -z "$sel" ]] || [[ "$sel" -lt 1 ]] || [[ "$sel" -gt $idx ]]; then
        status "Restore cancelled" yellow
        exit 0
    fi

    local sel_path="${backup_paths[$(( sel - 1 ))]}"
    local sel_orig="${backup_originals[$(( sel - 1 ))]}"

    if [[ "$sel_orig" == "true" ]]; then
        echo ""
        echo -e "  ${YELLOW}WARNING: This will revert to ORIGINAL mono audio modules.${NC}"
        read -rp "  Are you sure? (y/N): " confirm
        [[ "$confirm" == "y" || "$confirm" == "Y" ]] || { status "Restore cancelled" yellow; exit 0; }
    fi

    # Select target client
    echo ""
    echo -e "  ${WHITE}Restore to which client?${NC}"
    echo ""
    for i in "${!CLIENT_NAMES[@]}"; do
        echo -e "  ${WHITE}[$(( i + 1 ))]${NC} ${CLIENT_NAMES[$i]} (v${CLIENT_VERSIONS[$i]})"
    done
    echo ""
    read -rp "  Choice (1-${#CLIENT_NAMES[@]}): " cchoice

    if [[ -z "$cchoice" ]] || [[ "$cchoice" -lt 1 ]] || [[ "$cchoice" -gt ${#CLIENT_NAMES[@]} ]]; then
        status "Invalid selection" red
        exit 1
    fi

    local target_voice="${CLIENT_VOICE_PATHS[$(( cchoice - 1 ))]}"
    local target_name="${CLIENT_NAMES[$(( cchoice - 1 ))]}"

    status "" blue
    status "Closing Discord..." blue
    kill_discord

    status "Restoring backup..." blue
    if restore_from_backup "$sel_path" "$target_voice" "$sel_orig"; then
        status "" green
        if [[ "$sel_orig" == "true" ]]; then
            status "[OK] Restore complete — ORIGINAL modules restored (mono audio)" magenta
        else
            status "[OK] Restore complete!" green
        fi
        status "Restart Discord to apply changes." cyan
    else
        status "[X] Restore failed" red
        exit 1
    fi
}

# ═══════════════════════════════════════════════════════════════════════════════
#  INTERACTIVE MODE
# ═══════════════════════════════════════════════════════════════════════════════
run_interactive() {
    banner
    check_dependencies
    ensure_app_dirs

    status "Scanning for Discord installations..." blue
    find_discord_clients

    if [[ ${#CLIENT_NAMES[@]} -eq 0 ]]; then
        status "[X] No Discord installations found!" red
        echo ""
        echo "Searched the following locations:"
        for p in "${SEARCH_PATHS[@]}"; do
            [[ -d "$p" ]] && echo -e "  ${RED}✗${NC} $p" || echo -e "  ${DIM}- $p${NC}"
        done
        echo ""
        echo "Make sure Discord is installed and has been opened at least once."
        echo "If you just installed Discord, join a voice channel first to"
        echo "download the voice module, then run this script again."
        exit 1
    fi

    status "[OK] Found ${#CLIENT_NAMES[@]} client(s):" green
    for i in "${!CLIENT_NAMES[@]}"; do
        status "  [$(( i + 1 ))] ${CLIENT_NAMES[$i]} (v${CLIENT_VERSIONS[$i]})" cyan
        status "      ${CLIENT_VOICE_PATHS[$i]}" dim
    done

    # Check for updates
    echo ""
    local has_updates=false
    for i in "${!CLIENT_NAMES[@]}"; do
        local result
        result=$(check_discord_updated "${CLIENT_NAMES[$i]}" "${CLIENT_VERSIONS[$i]}")
        local rtype="${result%%|*}"
        case "$rtype" in
            NEW)     status "  ${CLIENT_NAMES[$i]}: Never fixed" yellow; has_updates=true ;;
            UPDATED)
                IFS='|' read -r _ old new date <<< "$result"
                status "  ${CLIENT_NAMES[$i]}: Updated v$old → v$new" orange
                has_updates=true
                ;;
            OK)
                IFS='|' read -r _ ver date <<< "$result"
                local date_fmt
                date_fmt=$(date -d "$date" '+%b %d, %H:%M' 2>/dev/null || echo "$date")
                status "  ${CLIENT_NAMES[$i]}: Fixed (v$ver, $date_fmt)" dim
                ;;
        esac
    done

    # Main menu
    while true; do
        echo ""
        echo -e "${CYAN}══════════════════════════════════════════════════${NC}"
        echo -e "  ${WHITE}[1]${NC} Fix single client"
        echo -e "  ${GREEN}[2]${NC} Fix ALL clients"
        echo -e "  ${BLUE}[3]${NC} Verify fix status"
        echo -e "  ${MAGENTA}[4]${NC} Restore from backup"
        echo -e "  ${YELLOW}[5]${NC} Check for Discord updates"
        echo -e "  ${DIM}[6]${NC} Open backup folder"
        echo -e "  ${RED}[Q]${NC} Quit"
        echo -e "${CYAN}══════════════════════════════════════════════════${NC}"
        echo ""
        read -rp "  Choice: " choice

        case "${choice^^}" in
            1) menu_fix_single ;;
            2) menu_fix_all ;;
            3) menu_verify ;;
            4) run_restore; return ;;
            5) menu_check_updates ;;
            6) echo "  Backups: $APP_DATA_ROOT"; command -v xdg-open &>/dev/null && xdg-open "$APP_DATA_ROOT" 2>/dev/null || true ;;
            Q) echo "Goodbye!"; exit 0 ;;
            *) echo -e "  ${RED}Invalid choice${NC}" ;;
        esac
    done
}

menu_fix_single() {
    echo ""
    echo -e "  ${WHITE}Select client to fix:${NC}"
    echo ""
    for i in "${!CLIENT_NAMES[@]}"; do
        echo -e "  ${WHITE}[$(( i + 1 ))]${NC} ${CLIENT_NAMES[$i]} (v${CLIENT_VERSIONS[$i]})"
    done
    echo -e "  ${RED}[C]${NC} Cancel"
    echo ""
    read -rp "  Choice: " sel

    [[ "${sel^^}" == "C" ]] && return
    if [[ -z "$sel" ]] || [[ "$sel" -lt 1 ]] || [[ "$sel" -gt ${#CLIENT_NAMES[@]} ]]; then
        status "Invalid selection" red
        return
    fi

    local idx=$(( sel - 1 ))

    echo ""
    status "=== STARTING FIX ===" blue
    status "Client: ${CLIENT_NAMES[$idx]}" cyan

    # Download
    local tmp_dir
    tmp_dir=$(mktemp -d)

    status "" blue
    status "Downloading voice backup files..." blue
    local download_path="$tmp_dir/VoiceBackup"
    if ! download_voice_files "$download_path"; then
        status "[X] Failed to download voice backup files" red
        rm -rf "$tmp_dir"
        return
    fi

    # Check if Discord is running
    if is_discord_running; then
        echo ""
        echo -e "  ${YELLOW}Discord is currently running. It will be closed to apply the fix.${NC}"
        read -rp "  Continue? (Y/n): " confirm
        [[ "${confirm,,}" == "n" ]] && { status "Cancelled" yellow; rm -rf "$tmp_dir"; return; }
    fi

    status "" blue
    status "Closing Discord processes..." blue
    kill_discord
    status "[OK] Discord processes closed" green

    # Fix
    if fix_client "$idx" "$download_path"; then
        remove_old_backups
        status "" green
        status "=== FIX COMPLETED SUCCESSFULLY ===" green
        status "Restart Discord to apply changes." cyan
    else
        status "" red
        status "[X] Fix failed" red
    fi

    rm -rf "$tmp_dir"
}

menu_fix_all() {
    echo ""
    echo -e "  ${WHITE}Fix all ${#CLIENT_NAMES[@]} client(s)?${NC}"
    read -rp "  Continue? (Y/n): " confirm
    [[ "${confirm,,}" == "n" ]] && return

    status "" blue
    status "=== FIX ALL DISCORD CLIENTS ===" blue

    # Download
    local tmp_dir
    tmp_dir=$(mktemp -d)

    status "Downloading voice backup files..." blue
    local download_path="$tmp_dir/VoiceBackup"
    if ! download_voice_files "$download_path"; then
        status "[X] Failed to download voice backup files" red
        rm -rf "$tmp_dir"
        return
    fi

    # Kill Discord
    if is_discord_running; then
        status "" blue
        status "Closing Discord processes..." blue
        kill_discord
        status "[OK] Discord processes closed" green
    fi

    # Fix all
    local success=0 failed=0
    for i in "${!CLIENT_NAMES[@]}"; do
        if fix_client "$i" "$download_path"; then
            (( success++ ))
        else
            (( failed++ ))
        fi
    done

    remove_old_backups

    status "" blue
    echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"
    if [[ $failed -eq 0 ]]; then
        echo -e "${GREEN}  ✓ FIX ALL COMPLETE: $success/${#CLIENT_NAMES[@]} successful${NC}"
    else
        echo -e "${YELLOW}  FIX ALL: $success/${#CLIENT_NAMES[@]} successful, $failed failed${NC}"
    fi
    echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"
    echo ""
    status "Restart Discord to apply changes." cyan

    rm -rf "$tmp_dir"
}

menu_verify() {
    echo ""
    status "=== VERIFYING FIX STATUS ===" blue
    echo ""

    for i in "${!CLIENT_NAMES[@]}"; do
        local result
        result=$(verify_fix "${CLIENT_VOICE_PATHS[$i]}" "${CLIENT_NAMES[$i]}")
        local rstatus="${result%%|*}"
        local rmsg rest
        IFS='|' read -r rstatus rmsg rest <<< "$result"

        case "$rstatus" in
            FIXED)
                echo -e "  ${GREEN}[✓]${NC} ${CLIENT_NAMES[$i]} — ${GREEN}Stereo fix is active${NC}"
                ;;
            NOTFIXED)
                echo -e "  ${YELLOW}[✗]${NC} ${CLIENT_NAMES[$i]} — ${YELLOW}Original mono modules${NC}"
                ;;
            UNKNOWN)
                echo -e "  ${DIM}[?]${NC} ${CLIENT_NAMES[$i]} — ${DIM}$rmsg${NC}"
                ;;
            ERROR)
                echo -e "  ${RED}[X]${NC} ${CLIENT_NAMES[$i]} — ${RED}$rmsg${NC}"
                ;;
        esac
    done

    echo ""
}

menu_check_updates() {
    echo ""
    status "Checking Discord versions..." blue
    echo ""

    for i in "${!CLIENT_NAMES[@]}"; do
        local result
        result=$(check_discord_updated "${CLIENT_NAMES[$i]}" "${CLIENT_VERSIONS[$i]}")
        local rtype="${result%%|*}"
        case "$rtype" in
            NEW)
                echo -e "  ${YELLOW}[NEW]${NC} ${CLIENT_NAMES[$i]}: v${CLIENT_VERSIONS[$i]} — Never fixed"
                ;;
            UPDATED)
                IFS='|' read -r _ old new date <<< "$result"
                echo -e "  ${ORANGE}[UPDATE]${NC} ${CLIENT_NAMES[$i]}: v$old → v$new"
                ;;
            OK)
                IFS='|' read -r _ ver date <<< "$result"
                local date_fmt
                date_fmt=$(date -d "$date" '+%b %d, %H:%M' 2>/dev/null || echo "$date")
                echo -e "  ${GREEN}[OK]${NC} ${CLIENT_NAMES[$i]}: v$ver (fixed: $date_fmt)"
                ;;
        esac
    done

    echo ""
}

# ═══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════
if $SILENT_MODE || $CHECK_ONLY; then
    check_dependencies
    ensure_app_dirs
    find_discord_clients
    run_silent
elif $RESTORE_MODE; then
    check_dependencies
    run_restore
else
    run_interactive
fi
