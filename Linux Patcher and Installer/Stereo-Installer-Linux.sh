#!/usr/bin/env bash
###############################################################################
# DISCORD VOICE FIXER — Stereo Audio Module Installer (Linux)
# Downloads and installs pre-patched stereo voice modules
# Usage: ./Stereo-Installer-Linux.sh [--silent] [--check] [--restore] [--help]
# Made by: Oracle | Shaun | Hallow | Ascend | Sentry | Sikimzo | Cypher
###############################################################################
set -euo pipefail

SCRIPT_VERSION="2.0"

# ─── Configuration ────────────────────────────────────────────────────────────
VOICE_BACKUP_API="https://api.github.com/repos/ProdHallow/Discord-Stereo-Windows-MacOS-Linux/contents/Linux%20Beta%20Patcher/discord_voice"
UPDATE_URL="https://raw.githubusercontent.com/ProdHallow/Discord-Stereo-Windows-MacOS-Linux/main/Linux%20Beta%20Patcher/Stereo-Installer-Linux.sh"

APP_DATA_ROOT="$HOME/.cache/DiscordVoiceFixer"
BACKUP_ROOT="$APP_DATA_ROOT/backups"
ORIGINAL_BACKUP_ROOT="$APP_DATA_ROOT/original_discord_modules"
STATE_FILE="$APP_DATA_ROOT/state.json"
SETTINGS_FILE="$APP_DATA_ROOT/settings.json"
LOG_FILE="$APP_DATA_ROOT/debug.log"
MAX_BACKUPS_PER_CLIENT=1
MAX_LOG_SIZE_MB=5

# ─── Colors ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'
MAGENTA='\033[0;35m'; WHITE='\033[1;37m'; DIM='\033[0;90m'; BLUE='\033[0;34m'
BOLD='\033[1m'; NC='\033[0m'; ORANGE='\033[0;33m'
LIMEGREEN='\033[1;32m'; UNDERLINE='\033[4m'

# ─── CLI Flags ────────────────────────────────────────────────────────────────
SILENT_MODE=false
CHECK_ONLY=false
RESTORE_MODE=false
FIX_CLIENT=""
DIAG_MODE=false
CLEANUP_MODE=false
AUTO_RESTART_DISCORD=true

for arg in "$@"; do
    case "$arg" in
        --silent|-s)    SILENT_MODE=true ;;
        --check|-c)     CHECK_ONLY=true ;;
        --restore|-r)   RESTORE_MODE=true ;;
        --fix=*)        FIX_CLIENT="${arg#--fix=}" ;;
        --diagnostics)  DIAG_MODE=true ;;
        --cleanup)      CLEANUP_MODE=true ;;
        --no-restart)   AUTO_RESTART_DISCORD=false ;;
        --help|-h)
            echo "Discord Voice Fixer — Linux Installer v${SCRIPT_VERSION}"
            echo ""
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --silent, -s        Run silently (no prompts, fix all clients)"
            echo "  --check, -c         Check Discord versions and fix status"
            echo "  --restore, -r       Restore original voice modules"
            echo "  --fix=<name>        Fix only the client matching <name>"
            echo "  --diagnostics       Show detailed diagnostics for all clients"
            echo "  --cleanup           Remove invalid/corrupted backups"
            echo "  --no-restart        Don't auto-restart Discord after fix"
            echo "  --help, -h          Show this help"
            echo ""
            echo "Examples:"
            echo "  $0                  # Interactive mode"
            echo "  $0 --silent         # Auto-fix all clients"
            echo "  $0 --check          # Check status"
            echo "  $0 --restore        # Restore from backup"
            echo "  $0 --diagnostics    # Full system diagnostics"
            exit 0
            ;;
    esac
done

# ─── Logging ──────────────────────────────────────────────────────────────────
ensure_dir() { [[ -d "$1" ]] || mkdir -p "$1" 2>/dev/null || true; }

rotate_log() {
    if [[ -f "$LOG_FILE" ]]; then
        local size_kb
        size_kb=$(du -k "$LOG_FILE" 2>/dev/null | cut -f1 || echo "0")
        if [[ "${size_kb:-0}" -gt $(( MAX_LOG_SIZE_MB * 1024 )) ]]; then
            mv "$LOG_FILE" "${LOG_FILE}.old" 2>/dev/null || true
        fi
    fi
}

log_file() {
    ensure_dir "$(dirname "$LOG_FILE")"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [$1] $2" >> "$LOG_FILE" 2>/dev/null || true
}

status() {
    local color="$NC" level="INFO"
    case "${2:-}" in
        red)       color="$RED";       level="ERROR" ;;
        green)     color="$GREEN";     level="OK" ;;
        limegreen) color="$LIMEGREEN"; level="OK" ;;
        yellow)    color="$YELLOW";    level="WARN" ;;
        cyan)      color="$CYAN";      level="INFO" ;;
        blue)      color="$BLUE";      level="INFO" ;;
        magenta)   color="$MAGENTA";   level="INFO" ;;
        orange)    color="$ORANGE";    level="WARN" ;;
        dim)       color="$DIM";       level="DEBUG" ;;
    esac
    log_file "$level" "$1"
    if ! $SILENT_MODE || [[ "$level" == "ERROR" ]] || [[ "$level" == "OK" ]]; then
        echo -e "${DIM}[$(date '+%H:%M:%S')]${NC} ${color}${1}${NC}"
    fi
}

banner() {
    echo ""
    echo -e "${CYAN}╔══════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║${NC}  ${WHITE}${BOLD}Discord Voice Fixer${NC} — ${CYAN}Linux Installer v${SCRIPT_VERSION}${NC}        ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}  ${DIM}48kHz | 512kbps | True Stereo | Filterless${NC}        ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}  ${DIM}Oracle | Shaun | Hallow | Ascend | Sentry${NC}         ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}  ${DIM}Sikimzo | Cypher${NC}                                  ${CYAN}║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════════════╝${NC}"
    echo ""
}

# ─── Progress Bar ─────────────────────────────────────────────────────────────
progress_bar() {
    local pct="$1" label="${2:-Working...}" width=40
    local filled=$(( pct * width / 100 ))
    local empty=$(( width - filled ))
    local bar=""
    for (( i=0; i<filled; i++ )); do bar+="█"; done
    for (( i=0; i<empty; i++ )); do bar+="░"; done
    printf "\r  ${CYAN}[${bar}]${NC} ${WHITE}%3d%%${NC} ${DIM}%s${NC}  " "$pct" "$label"
    if [[ "$pct" -ge 100 ]]; then echo ""; fi
}

# ─── Dependency Check ─────────────────────────────────────────────────────────
check_dependencies() {
    local missing=()
    command -v curl   &>/dev/null || missing+=("curl")
    command -v jq     &>/dev/null || missing+=("jq")
    command -v md5sum &>/dev/null || missing+=("coreutils")

    if [[ ${#missing[@]} -gt 0 ]]; then
        status "[X] Missing dependencies: ${missing[*]}" red
        echo ""
        echo -e "  Install with:"
        echo -e "    ${WHITE}Ubuntu/Debian:${NC}  sudo apt install ${missing[*]}"
        echo -e "    ${WHITE}Fedora/RHEL:${NC}    sudo dnf install ${missing[*]}"
        echo -e "    ${WHITE}Arch:${NC}           sudo pacman -S ${missing[*]}"
        exit 1
    fi
    log_file "INFO" "Dependencies OK: curl, jq, md5sum"
}

# ─── Settings Management ─────────────────────────────────────────────────────
load_settings() {
    if [[ -f "$SETTINGS_FILE" ]]; then
        AUTO_RESTART_DISCORD=$(jq -r '.AutoStartDiscord // true' "$SETTINGS_FILE" 2>/dev/null || echo "true")
        [[ "$AUTO_RESTART_DISCORD" == "true" ]] && AUTO_RESTART_DISCORD=true || AUTO_RESTART_DISCORD=false
    fi
}

save_settings() {
    ensure_dir "$(dirname "$SETTINGS_FILE")"
    cat > "$SETTINGS_FILE" << EOF
{
    "AutoStartDiscord": $AUTO_RESTART_DISCORD,
    "LastRun": "$(date -Iseconds)",
    "ScriptVersion": "$SCRIPT_VERSION"
}
EOF
}

# ─── Disk Space Check ────────────────────────────────────────────────────────
get_available_space_mb() {
    local path="$1"
    df -BM "$path" 2>/dev/null | tail -1 | awk '{gsub(/M/,"",$4); print $4}' || echo "0"
}

check_disk_space() {
    local path="$1" needed_mb="$2"
    local available
    available=$(get_available_space_mb "$path")
    if [[ "${available:-0}" -gt 0 ]] && [[ "$available" -lt "$needed_mb" ]]; then
        status "[!] Low disk space: ${available}MB available, need ~${needed_mb}MB" orange
        return 1
    fi
    return 0
}

# ─── Discord Client Detection ────────────────────────────────────────────────
declare -a CLIENT_NAMES=()
declare -a CLIENT_PATHS=()
declare -a CLIENT_APP_PATHS=()
declare -a CLIENT_VOICE_PATHS=()
declare -a CLIENT_VERSIONS=()
declare -a CLIENT_PROCESS_NAMES=()
declare -a CLIENT_NODE_HASHES=()
declare -a CLIENT_NODE_SIZES=()

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
    app_dirs=$(find "$base" -maxdepth 1 -type d -name "app-*" 2>/dev/null | sort -V -r || true)
    if [[ -n "$app_dirs" ]]; then
        while IFS= read -r app_dir; do
            local modules_dir="$app_dir/modules"
            if [[ -d "$modules_dir" ]]; then
                local voice_dir
                voice_dir=$(find "$modules_dir" -maxdepth 1 -type d -name "discord_voice*" 2>/dev/null | head -1 || true)
                if [[ -n "$voice_dir" ]]; then
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
    node_file=$(find "$base" -maxdepth 6 -name "discord_voice.node" -type f 2>/dev/null | head -1 || true)
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

# Get .node file hash and size for a voice path
get_node_info() {
    local voice_path="$1"
    local node_file
    node_file=$(find "$voice_path" -name "*.node" -type f 2>/dev/null | head -1 || true)
    if [[ -n "$node_file" ]]; then
        local hash size
        hash=$(md5sum "$node_file" 2>/dev/null | cut -d' ' -f1 || true)
        size=$(stat -c%s "$node_file" 2>/dev/null || echo "0")
        echo "${hash}|${size}"
    else
        echo "|0"
    fi
}

find_discord_clients() {
    CLIENT_NAMES=()
    CLIENT_PATHS=()
    CLIENT_APP_PATHS=()
    CLIENT_VOICE_PATHS=()
    CLIENT_VERSIONS=()
    CLIENT_PROCESS_NAMES=()
    CLIENT_NODE_HASHES=()
    CLIENT_NODE_SIZES=()

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
            if [[ ${#found_voice_paths[@]} -gt 0 ]]; then
                for fvp in "${found_voice_paths[@]}"; do
                    [[ "$fvp" == "$voice_path" ]] && { dup=true; break; }
                done
            fi
            $dup && continue

            local version
            version=$(get_app_version "$app_path")

            # Get node file info
            local node_info hash size
            node_info=$(get_node_info "$voice_path")
            hash="${node_info%%|*}"
            size="${node_info##*|}"

            CLIENT_NAMES+=("$name")
            CLIENT_PATHS+=("$base")
            CLIENT_APP_PATHS+=("$app_path")
            CLIENT_VOICE_PATHS+=("$voice_path")
            CLIENT_VERSIONS+=("$version")
            CLIENT_PROCESS_NAMES+=("$proc")
            CLIENT_NODE_HASHES+=("$hash")
            CLIENT_NODE_SIZES+=("$size")
            found_voice_paths+=("$voice_path")

            log_file "INFO" "Found: $name v$version at $voice_path (hash=${hash:0:8}..., ${size} bytes)"
        fi
    done

    return 0
}

# ─── Process Management ──────────────────────────────────────────────────────
kill_discord() {
    local procs=("Discord" "DiscordCanary" "DiscordPTB" "DiscordDevelopment" "discord")
    local attempts=0 max_attempts=3

    while [[ $attempts -lt $max_attempts ]]; do
        local running=false
        for pname in "${procs[@]}"; do
            if pgrep -f "$pname" &>/dev/null; then
                running=true
                break
            fi
        done

        if ! $running; then
            return 0
        fi

        if [[ $attempts -eq 0 ]]; then
            # Graceful SIGTERM first
            for pname in "${procs[@]}"; do
                pkill -f "$pname" 2>/dev/null || true
            done
            sleep 2
        else
            # Force SIGKILL
            for pname in "${procs[@]}"; do
                pkill -9 -f "$pname" 2>/dev/null || true
            done
            sleep 1
        fi

        (( attempts++ )) || true
    done

    # Final check
    for pname in "${procs[@]}"; do
        if pgrep -f "$pname" &>/dev/null; then
            status "  [!] Warning: Could not kill all Discord processes" orange
            log_file "WARN" "Discord processes still running after $max_attempts kill attempts"
            return 1
        fi
    done

    return 0
}

is_discord_running() {
    pgrep -f "Discord|discord" &>/dev/null
}

start_discord() {
    # Try common launch methods
    local launchers=(
        "discord"
        "discord-canary"
        "discord-ptb"
        "/opt/discord/Discord"
        "/opt/discord-canary/DiscordCanary"
        "/usr/bin/discord"
        "/snap/bin/discord"
    )

    for launcher in "${launchers[@]}"; do
        if command -v "$launcher" &>/dev/null; then
            nohup "$launcher" &>/dev/null &
            return 0
        fi
        if [[ -x "$launcher" ]]; then
            nohup "$launcher" &>/dev/null &
            return 0
        fi
    done

    # Try flatpak
    if command -v flatpak &>/dev/null; then
        if flatpak list 2>/dev/null | grep -qi discord; then
            nohup flatpak run com.discordapp.Discord &>/dev/null &
            return 0
        fi
    fi

    return 1
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
    local node_hash="${3:-}"

    ensure_app_dirs

    if [[ -f "$STATE_FILE" ]]; then
        local tmp
        tmp=$(mktemp)
        jq --arg k "$key" --arg v "$version" --arg d "$fix_date" --arg h "$node_hash" \
            '.[$k] = {"LastFixedVersion": $v, "LastFixDate": $d, "NodeHash": $h}' \
            "$STATE_FILE" > "$tmp" 2>/dev/null && mv "$tmp" "$STATE_FILE" || rm -f "$tmp"
    else
        jq -n --arg k "$key" --arg v "$version" --arg d "$fix_date" --arg h "$node_hash" \
            '{($k): {"LastFixedVersion": $v, "LastFixDate": $d, "NodeHash": $h}}' \
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

# ─── Backup Validation ──────────────────────────────────────────────────────
backup_has_content() {
    local backup_path="$1"
    local voice_dir="$backup_path/voice_module"
    [[ -d "$voice_dir" ]] || return 1

    # Check for critical files (.node or .so)
    local count
    count=$(find "$voice_dir" -type f \( -name "*.node" -o -name "*.so" -o -name "*.dll" \) 2>/dev/null | wc -l || echo "0")
    [[ $count -gt 0 ]] || return 1

    # Check none are empty (0 bytes)
    local empty_count
    empty_count=$(find "$voice_dir" -type f \( -name "*.node" -o -name "*.so" \) -empty 2>/dev/null | wc -l || echo "0")
    if [[ $empty_count -gt 0 ]]; then
        log_file "WARN" "Backup has $empty_count empty critical files: $backup_path"
        return 1
    fi

    # Check .node file is reasonable size (>1KB)
    local node_file
    node_file=$(find "$voice_dir" -name "*.node" -type f 2>/dev/null | head -1 || true)
    if [[ -n "$node_file" ]]; then
        local fsize
        fsize=$(stat -c%s "$node_file" 2>/dev/null || echo "0")
        if [[ "$fsize" -lt 1024 ]]; then
            log_file "WARN" "Backup .node file too small (${fsize} bytes): $node_file"
            return 1
        fi
    fi

    return 0
}

validate_backup_integrity() {
    local backup_path="$1"

    # Check metadata.json exists and is valid JSON
    local meta="$backup_path/metadata.json"
    if [[ ! -f "$meta" ]]; then
        echo "INVALID|Missing metadata.json"
        return
    fi

    if ! jq empty "$meta" 2>/dev/null; then
        echo "INVALID|Corrupted metadata.json"
        return
    fi

    local cn
    cn=$(jq -r '.ClientName // empty' "$meta" 2>/dev/null || true)
    if [[ -z "$cn" ]]; then
        echo "INVALID|Missing ClientName in metadata"
        return
    fi

    if ! backup_has_content "$backup_path"; then
        echo "INVALID|Missing or empty critical files"
        return
    fi

    echo "VALID"
}

# ─── Backup Management ──────────────────────────────────────────────────────
create_original_backup() {
    local voice_path="$1" client_name="$2" version="$3"
    local sname
    sname=$(sanitize_name "$client_name")
    local backup_path="$ORIGINAL_BACKUP_ROOT/$sname"

    if [[ -d "$backup_path" ]]; then
        # Validate existing backup
        local validation
        validation=$(validate_backup_integrity "$backup_path")
        if [[ "${validation%%|*}" == "VALID" ]]; then
            status "  Original backup already exists and is valid" dim
            return 0
        else
            status "  [!] Existing original backup is corrupted — recreating..." orange
            rm -rf "$backup_path"
        fi
    fi

    if [[ ! -d "$voice_path" ]]; then
        status "  [!] Voice folder does not exist: $voice_path" orange
        return 1
    fi

    local file_count
    file_count=$(find "$voice_path" -type f 2>/dev/null | wc -l || echo "0")
    if [[ $file_count -eq 0 ]]; then
        status "  [!] Voice folder is empty, cannot create backup" orange
        return 1
    fi

    # Disk space check
    local needed_mb
    needed_mb=$(du -sm "$voice_path" 2>/dev/null | cut -f1 || echo "0")
    needed_mb=$(( needed_mb + 10 ))
    if ! check_disk_space "$ORIGINAL_BACKUP_ROOT" "$needed_mb"; then
        return 1
    fi

    ensure_dir "$backup_path/voice_module"
    status "  Creating ORIGINAL backup (will never be deleted)..." magenta
    cp -r "$voice_path"/* "$backup_path/voice_module/" 2>/dev/null

    if ! backup_has_content "$backup_path"; then
        status "  [!] Backup validation failed — files may be corrupted" orange
        rm -rf "$backup_path"
        return 1
    fi

    local total_size node_hash
    total_size=$(du -sh "$backup_path/voice_module" 2>/dev/null | cut -f1 || echo "unknown")
    node_hash=$(find "$backup_path/voice_module" -name "*.node" -type f -exec md5sum {} \; 2>/dev/null | head -1 | cut -d' ' -f1 || true)

    cat > "$backup_path/metadata.json" << EOF
{
    "ClientName": "$client_name",
    "AppVersion": "$version",
    "BackupDate": "$(date -Iseconds)",
    "IsOriginal": true,
    "Description": "Original Discord modules - preserved for reverting to mono audio",
    "FileCount": $file_count,
    "NodeHash": "${node_hash:-unknown}",
    "Platform": "linux"
}
EOF

    status "  [OK] Original backup created: $sname ($file_count files, $total_size)" magenta
    status "       This backup will NEVER be deleted automatically" cyan
    log_file "INFO" "Original backup created: $sname ($file_count files, hash=${node_hash:-unknown})"
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
    file_count=$(find "$voice_path" -type f 2>/dev/null | wc -l || echo "0")
    if [[ $file_count -eq 0 ]]; then
        status "  [!] Voice folder is empty" orange
        return 1
    fi

    ensure_dir "$backup_path/voice_module"
    status "  Backing up voice module..." cyan
    cp -r "$voice_path"/* "$backup_path/voice_module/" 2>/dev/null

    if ! backup_has_content "$backup_path"; then
        status "  [!] Backup validation failed" orange
        rm -rf "$backup_path"
        return 1
    fi

    local node_hash
    node_hash=$(find "$backup_path/voice_module" -name "*.node" -type f -exec md5sum {} \; 2>/dev/null | head -1 | cut -d' ' -f1 || true)

    cat > "$backup_path/metadata.json" << EOF
{
    "ClientName": "$client_name",
    "AppVersion": "$version",
    "BackupDate": "$(date -Iseconds)",
    "IsOriginal": false,
    "FileCount": $file_count,
    "NodeHash": "${node_hash:-unknown}",
    "Platform": "linux"
}
EOF

    status "  [OK] Backup created: $backup_name ($file_count files)" green
    log_file "INFO" "Backup created: $backup_name ($file_count files, hash=${node_hash:-unknown})"
    return 0
}

remove_old_backups() {
    local clients=()
    for dir in "$BACKUP_ROOT"/*/; do
        [[ -d "$dir" ]] || continue
        local meta="$dir/metadata.json"
        [[ -f "$meta" ]] || continue
        local cn
        cn=$(jq -r '.ClientName // empty' "$meta" 2>/dev/null || true)
        [[ -n "$cn" ]] || continue

        local found=false
        if [[ ${#clients[@]} -gt 0 ]]; then
            for c in "${clients[@]}"; do
                [[ "$c" == "$cn" ]] && { found=true; break; }
            done
        fi
        $found || clients+=("$cn")
    done

    [[ ${#clients[@]} -gt 0 ]] || return 0
    for cn in "${clients[@]}"; do
        local dirs=()
        for dir in "$BACKUP_ROOT"/*/; do
            [[ -d "$dir" ]] || continue
            local meta="$dir/metadata.json"
            [[ -f "$meta" ]] || continue
            local this_cn
            this_cn=$(jq -r '.ClientName // empty' "$meta" 2>/dev/null || true)
            [[ "$this_cn" == "$cn" ]] && dirs+=("$dir")
        done

        if [[ ${#dirs[@]} -gt $MAX_BACKUPS_PER_CLIENT ]]; then
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

# Clean up invalid/corrupted backups
cleanup_invalid_backups() {
    local cleaned=0 total=0

    status "Scanning backups for corruption..." blue
    echo ""

    # Check regular backups
    for dir in "$BACKUP_ROOT"/*/; do
        [[ -d "$dir" ]] || continue
        (( total++ )) || true
        local validation
        validation=$(validate_backup_integrity "$dir")
        local vstatus="${validation%%|*}"
        local vmsg="${validation#*|}"

        if [[ "$vstatus" == "INVALID" ]]; then
            local dirname
            dirname=$(basename "$dir")
            status "  [X] $dirname — $vmsg" red
            rm -rf "$dir" 2>/dev/null
            (( cleaned++ )) || true
        fi
    done

    # Check original backups
    for dir in "$ORIGINAL_BACKUP_ROOT"/*/; do
        [[ -d "$dir" ]] || continue
        (( total++ )) || true
        local validation
        validation=$(validate_backup_integrity "$dir")
        local vstatus="${validation%%|*}"
        local vmsg="${validation#*|}"

        if [[ "$vstatus" == "INVALID" ]]; then
            local dirname
            dirname=$(basename "$dir")
            status "  [X] [ORIGINAL] $dirname — $vmsg" red
            rm -rf "$dir" 2>/dev/null
            (( cleaned++ )) || true
        fi
    done

    echo ""
    if [[ $cleaned -gt 0 ]]; then
        status "[OK] Cleaned up $cleaned of $total backup(s)" green
    else
        status "[OK] All $total backup(s) are valid" green
    fi
}

list_backups() {
    local idx=0

    # Original backups
    for dir in "$ORIGINAL_BACKUP_ROOT"/*/; do
        [[ -d "$dir" ]] || continue
        local meta="$dir/metadata.json"
        [[ -f "$meta" ]] || continue

        local validation
        validation=$(validate_backup_integrity "$dir")
        [[ "${validation%%|*}" == "VALID" ]] || continue

        local cn av bd
        cn=$(jq -r '.ClientName // "Unknown"' "$meta" 2>/dev/null || echo "Unknown")
        av=$(jq -r '.AppVersion // "?"' "$meta" 2>/dev/null || echo "?")
        bd=$(jq -r '.BackupDate // "?"' "$meta" 2>/dev/null || echo "?")
        local bd_fmt
        bd_fmt=$(date -d "$bd" '+%b %d, %Y %H:%M' 2>/dev/null || echo "$bd")
        echo "ORIGINAL|$dir|$cn|$av|$bd_fmt"
        (( idx++ )) || true
    done

    # Regular backups (newest first)
    while IFS= read -r dir; do
        [[ -d "$dir" ]] || continue
        local meta="$dir/metadata.json"
        [[ -f "$meta" ]] || continue

        local validation
        validation=$(validate_backup_integrity "$dir")
        [[ "${validation%%|*}" == "VALID" ]] || continue

        local cn av bd
        cn=$(jq -r '.ClientName // "Unknown"' "$meta" 2>/dev/null || echo "Unknown")
        av=$(jq -r '.AppVersion // "?"' "$meta" 2>/dev/null || echo "?")
        bd=$(jq -r '.BackupDate // "?"' "$meta" 2>/dev/null || echo "?")
        local bd_fmt
        bd_fmt=$(date -d "$bd" '+%b %d, %Y %H:%M' 2>/dev/null || echo "$bd")
        echo "BACKUP|$dir|$cn|$av|$bd_fmt"
        (( idx++ )) || true
    done < <(ls -dt "$BACKUP_ROOT"/*/ 2>/dev/null)
}

restore_from_backup() {
    local backup_path="$1" target_voice_path="$2" is_original="${3:-false}"
    local voice_backup="$backup_path/voice_module"

    if [[ ! -d "$voice_backup" ]]; then
        status "[X] Backup is corrupted: voice_module folder missing" red
        return 1
    fi

    if ! backup_has_content "$backup_path"; then
        status "[X] Backup is invalid: missing or empty critical files" red
        return 1
    fi

    if [[ "$is_original" == "true" ]]; then
        status "  Restoring ORIGINAL voice module (reverting to mono)..." magenta
    else
        status "  Restoring voice module..." cyan
    fi

    # Clear target and copy
    if [[ -z "$target_voice_path" ]] || [[ "$target_voice_path" == "/" ]]; then
        status "[X] Invalid target path — aborting restore for safety" red
        return 1
    fi

    if [[ -d "$target_voice_path" ]]; then
        rm -rf "$target_voice_path"/* 2>/dev/null
    else
        ensure_dir "$target_voice_path"
    fi

    cp -r "$voice_backup"/* "$target_voice_path"/

    local restored_count
    restored_count=$(find "$target_voice_path" -type f 2>/dev/null | wc -l)
    if [[ $restored_count -eq 0 ]]; then
        status "  [X] Restore failed: no files were copied" red
        return 1
    fi

    status "  [OK] Restored $restored_count files" green
    log_file "INFO" "Restored $restored_count files to $target_voice_path"
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
        log_file "INFO" "Download attempt $attempt: $VOICE_BACKUP_API"

        local api_response http_code
        api_response=$(curl -sS -w "\n%{http_code}" -L \
            -H "Accept: application/vnd.github.v3+json" \
            "$VOICE_BACKUP_API" 2>&1) || {
            local last_line="${api_response##*$'\n'}"
            if [[ "$last_line" == "403" ]]; then
                status "  [X] GitHub API rate limit exceeded. Try again later." red
                status "      Tip: Wait a few minutes or use a VPN if in a restricted region." yellow
                return 1
            fi
            if [[ $attempt -lt $max_retries ]]; then
                status "  [!] Attempt $attempt failed — retrying..." orange
                continue
            fi
            status "  [X] Failed to fetch file list after $max_retries attempts" red
            status "      Error: ${api_response:0:200}" dim
            return 1
        }

        # Extract HTTP code from last line
        http_code="${api_response##*$'\n'}"
        api_response="${api_response%$'\n'*}"

        if [[ "$http_code" == "404" ]]; then
            status "  [X] Repository not found (404). Check the URL configuration." red
            log_file "ERROR" "GitHub API returned 404"
            return 1
        fi

        ensure_dir "$dest_path"

        local file_count=0
        local failed_files=()
        local total_bytes=0

        # Parse JSON array of files
        local file_names file_urls file_sizes
        file_names=$(echo "$api_response" | jq -r '.[] | select(.type == "file") | .name' 2>/dev/null || true)
        file_urls=$(echo "$api_response" | jq -r '.[] | select(.type == "file") | .download_url' 2>/dev/null || true)
        file_sizes=$(echo "$api_response" | jq -r '.[] | select(.type == "file") | .size' 2>/dev/null || true)

        if [[ -z "$file_names" ]]; then
            if [[ $attempt -lt $max_retries ]]; then
                status "  [!] Empty response, retrying..." orange
                continue
            fi
            status "  [X] GitHub repository response is empty" red
            return 1
        fi

        local expected_count
        expected_count=$(echo "$file_names" | wc -l)
        status "  Found $expected_count file(s) to download" cyan

        while IFS= read -r fname && IFS= read -r furl <&3 && IFS= read -r fexpected_size <&4; do
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

                # Size validation
                if [[ "$ext" == "node" || "$ext" == "so" ]]; then
                    if [[ $fsize -lt 1024 ]]; then
                        status "  [!] Warning: $fname seems too small ($fsize bytes)" orange
                        failed_files+=("$fname (size: $fsize)")
                        continue
                    fi
                fi

                # Verify against expected size from API
                if [[ -n "$fexpected_size" ]] && [[ "$fexpected_size" != "null" ]] && [[ "$fexpected_size" -gt 0 ]]; then
                    if [[ "$fsize" -ne "$fexpected_size" ]]; then
                        status "  [!] Size mismatch: $fname (got $fsize, expected $fexpected_size)" orange
                        log_file "WARN" "Size mismatch: $fname (got $fsize, expected $fexpected_size)"
                    fi
                fi

                local fsize_fmt
                if [[ $fsize -gt 1048576 ]]; then
                    fsize_fmt="$(( fsize / 1048576 )) MB"
                elif [[ $fsize -gt 1024 ]]; then
                    fsize_fmt="$(( fsize / 1024 )) KB"
                else
                    fsize_fmt="$fsize B"
                fi

                status "  Downloaded: $fname ($fsize_fmt)" cyan
                (( file_count++ )) || true
                (( total_bytes += fsize )) || true
            else
                status "  [!] Failed to download $fname" orange
                failed_files+=("$fname")
            fi
        done < <(echo "$file_names") 3< <(echo "$file_urls") 4< <(echo "$file_sizes")

        if [[ $file_count -eq 0 ]]; then
            if [[ $attempt -lt $max_retries ]]; then
                status "  [!] No files downloaded, retrying..." orange
                continue
            fi
            status "  [X] No valid files were downloaded" red
            return 1
        fi

        if [[ ${#failed_files[@]} -gt 0 ]]; then
            status "  [!] Warning: ${#failed_files[@]} file(s) failed:" orange
            for ff in "${failed_files[@]}"; do
                status "      - $ff" orange
            done
        fi

        local total_fmt
        if [[ $total_bytes -gt 1048576 ]]; then
            total_fmt="$(( total_bytes / 1048576 )) MB"
        else
            total_fmt="$(( total_bytes / 1024 )) KB"
        fi

        status "  [OK] Downloaded $file_count file(s) ($total_fmt total)" green
        return 0
    done

    return 1
}

# ─── Verify Fix Status ──────────────────────────────────────────────────────
verify_fix() {
    local voice_path="$1" client_name="$2"
    local sname
    sname=$(sanitize_name "$client_name")
    local orig_path="$ORIGINAL_BACKUP_ROOT/$sname/voice_module"

    local node_file
    node_file=$(find "$voice_path" -name "*.node" -type f 2>/dev/null | head -1 || true)
    if [[ -z "$node_file" ]]; then
        echo "ERROR|No .node file found in voice module"
        return
    fi

    local current_hash current_size
    current_hash=$(md5sum "$node_file" 2>/dev/null | cut -d' ' -f1 || true)
    current_size=$(stat -c%s "$node_file" 2>/dev/null || echo "0")

    # Check for zero-size corruption
    if [[ "$current_size" -eq 0 ]]; then
        echo "ERROR|Voice module file is empty (0 bytes) — corrupted"
        return
    fi

    if [[ "$current_size" -lt 1024 ]]; then
        echo "ERROR|Voice module file is suspiciously small (${current_size} bytes)"
        return
    fi

    if [[ -d "$orig_path" ]]; then
        local orig_node
        orig_node=$(find "$orig_path" -name "*.node" -type f 2>/dev/null | head -1 || true)
        if [[ -n "$orig_node" ]]; then
            local orig_hash
            orig_hash=$(md5sum "$orig_node" 2>/dev/null | cut -d' ' -f1 || true)
            if [[ "$current_hash" == "$orig_hash" ]]; then
                echo "NOTFIXED|Original mono modules detected|$current_hash|$current_size"
                return
            else
                echo "FIXED|Stereo fix is applied|$current_hash|$current_size"
                return
            fi
        fi
    fi

    echo "UNKNOWN|No original backup to compare — run fix first|$current_hash|$current_size"
}

# ─── Script Self-Update Check ────────────────────────────────────────────────
check_script_update() {
    status "Checking for script updates..." blue
    local tmp_script
    tmp_script=$(mktemp)

    if curl -sS --fail -L -o "$tmp_script" "$UPDATE_URL" 2>/dev/null; then
        local remote_version
        remote_version=$(grep '^SCRIPT_VERSION=' "$tmp_script" 2>/dev/null | head -1 | cut -d'"' -f2 || true)

        if [[ -n "$remote_version" ]] && [[ "$remote_version" != "$SCRIPT_VERSION" ]]; then
            status "[!] Script update available: v$SCRIPT_VERSION → v$remote_version" yellow
            echo ""
            echo -e "  Download from:"
            echo -e "  ${CYAN}${UNDERLINE}${UPDATE_URL}${NC}"
            echo ""
            rm -f "$tmp_script"
            return 0
        else
            status "[OK] Script is up to date (v$SCRIPT_VERSION)" green
        fi
    else
        status "  [!] Could not check for updates" orange
    fi

    rm -f "$tmp_script"
    return 1
}

# ─── Fix a Single Client ────────────────────────────────────────────────────
fix_client() {
    local idx="$1" download_path="$2"
    local name="${CLIENT_NAMES[$idx]}"
    local voice_path="${CLIENT_VOICE_PATHS[$idx]}"
    local app_path="${CLIENT_APP_PATHS[$idx]}"
    local version="${CLIENT_VERSIONS[$idx]}"

    status "" blue
    status "=== Fixing: $name ===" blue
    status "  Version: v$version" cyan
    status "  Voice module: $voice_path" dim

    # Backup
    status "  Creating backup..." cyan
    create_voice_backup "$voice_path" "$name" "$version" || true

    # Ensure writable
    if [[ -z "$voice_path" ]] || [[ "$voice_path" == "/" ]]; then
        status "  [X] Invalid voice path — aborting for safety" red
        return 1
    fi

    if [[ ! -w "$voice_path" ]]; then
        status "  Path not writable, attempting chmod..." yellow
        chmod -R +w "$voice_path" 2>/dev/null || {
            status "  [X] Cannot make voice folder writable. Try:" red
            status "      sudo chmod -R +w '$voice_path'" yellow
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

    # Verify node file exists and is non-empty
    local new_node
    new_node=$(find "$voice_path" -name "*.node" -type f 2>/dev/null | head -1 || true)
    if [[ -z "$new_node" ]]; then
        status "  [X] No .node file found after copy — something went wrong" red
        return 1
    fi

    local new_size new_hash
    new_size=$(stat -c%s "$new_node" 2>/dev/null || echo "0")
    new_hash=$(md5sum "$new_node" 2>/dev/null | cut -d' ' -f1 || true)

    if [[ "$new_size" -lt 1024 ]]; then
        status "  [X] Copied .node file is suspiciously small (${new_size} bytes)" red
        status "      The downloaded file may be corrupted. Try again." yellow
        return 1
    fi

    save_fix_state "$name" "$version" "$new_hash"

    local size_fmt
    if [[ $new_size -gt 1048576 ]]; then
        size_fmt="$(( new_size / 1048576 )) MB"
    else
        size_fmt="$(( new_size / 1024 )) KB"
    fi

    status "[OK] $name fixed successfully ($copied_count files, $size_fmt)" limegreen
    status "     Hash: ${new_hash:0:16}..." dim
    log_file "INFO" "Fixed: $name v$version ($copied_count files, hash=$new_hash)"
    return 0
}

# ═══════════════════════════════════════════════════════════════════════════════
#  DIAGNOSTICS
# ═══════════════════════════════════════════════════════════════════════════════
run_diagnostics() {
    banner
    check_dependencies
    ensure_app_dirs

    echo -e "${WHITE}${BOLD}=== SYSTEM DIAGNOSTICS ===${NC}"
    echo ""

    # System info
    echo -e "${CYAN}System:${NC}"
    echo -e "  OS:       $(grep PRETTY_NAME /etc/os-release 2>/dev/null | cut -d'"' -f2 || uname -s)"
    echo -e "  Kernel:   $(uname -r)"
    echo -e "  Arch:     $(uname -m)"
    echo -e "  Disk:     $(get_available_space_mb "$HOME") MB free (home)"
    echo ""

    # Dependencies
    echo -e "${CYAN}Dependencies:${NC}"
    for dep in curl jq md5sum; do
        if command -v "$dep" &>/dev/null; then
            local ver
            ver=$("$dep" --version 2>/dev/null | head -1 | head -c 60 || echo "version unavailable")
            echo -e "  ${GREEN}✓${NC} $dep — $ver"
        else
            echo -e "  ${RED}✗${NC} $dep — NOT FOUND"
        fi
    done
    echo ""

    # Scan for clients
    echo -e "${CYAN}Discord Installations:${NC}"
    find_discord_clients

    if [[ ${#CLIENT_NAMES[@]} -eq 0 ]]; then
        echo -e "  ${RED}No Discord installations found${NC}"
        echo ""
        echo -e "${CYAN}Searched:${NC}"
        for p in "${SEARCH_PATHS[@]}"; do
            if [[ -d "$p" ]]; then
                echo -e "  ${YELLOW}●${NC} $p (exists, no voice module)"
            else
                echo -e "  ${DIM}○ $p${NC}"
            fi
        done
    else
        for i in "${!CLIENT_NAMES[@]}"; do
            echo ""
            echo -e "  ${WHITE}${BOLD}${CLIENT_NAMES[$i]}${NC}"
            echo -e "    Version:     ${CLIENT_VERSIONS[$i]}"
            echo -e "    Base path:   ${CLIENT_PATHS[$i]}"
            echo -e "    App path:    ${CLIENT_APP_PATHS[$i]}"
            echo -e "    Voice path:  ${CLIENT_VOICE_PATHS[$i]}"

            local node_file
            node_file=$(find "${CLIENT_VOICE_PATHS[$i]}" -name "*.node" -type f 2>/dev/null | head -1 || true)
            if [[ -n "$node_file" ]]; then
                local fsize fhash
                fsize=$(stat -c%s "$node_file" 2>/dev/null || echo "0")
                fhash=$(md5sum "$node_file" 2>/dev/null | cut -d' ' -f1 || true)
                local size_fmt
                if [[ $fsize -gt 1048576 ]]; then
                    size_fmt="$(echo "scale=1; $fsize / 1048576" | bc 2>/dev/null || echo "$(( fsize / 1048576 ))") MB"
                else
                    size_fmt="$(( fsize / 1024 )) KB"
                fi
                echo -e "    Node file:   $(basename "$node_file") ($size_fmt)"
                echo -e "    MD5:         $fhash"

                if [[ $fsize -lt 1024 ]]; then
                    echo -e "    ${RED}⚠ WARNING: File suspiciously small — may be corrupted${NC}"
                fi
            else
                echo -e "    ${RED}⚠ No .node file found!${NC}"
            fi

            # Check fix status
            local result
            result=$(verify_fix "${CLIENT_VOICE_PATHS[$i]}" "${CLIENT_NAMES[$i]}")
            local rstatus="${result%%|*}"
            case "$rstatus" in
                FIXED)    echo -e "    Fix status:  ${GREEN}STEREO ACTIVE${NC}" ;;
                NOTFIXED) echo -e "    Fix status:  ${YELLOW}ORIGINAL MONO${NC}" ;;
                UNKNOWN)  echo -e "    Fix status:  ${DIM}UNKNOWN${NC}" ;;
                ERROR)    local rmsg; IFS='|' read -r _ rmsg _ <<< "$result"; echo -e "    Fix status:  ${RED}ERROR: $rmsg${NC}" ;;
            esac

            # Check update status
            local uresult
            uresult=$(check_discord_updated "${CLIENT_NAMES[$i]}" "${CLIENT_VERSIONS[$i]}")
            local urtype="${uresult%%|*}"
            case "$urtype" in
                NEW)     echo -e "    Update:      ${YELLOW}Never fixed${NC}" ;;
                UPDATED) IFS='|' read -r _ old new _ <<< "$uresult"; echo -e "    Update:      ${ORANGE}Updated v$old → v$new${NC}" ;;
                OK)      IFS='|' read -r _ ver date <<< "$uresult"; echo -e "    Update:      ${GREEN}Up to date (fixed: $date)${NC}" ;;
            esac
        done
    fi

    # Backups
    echo ""
    echo -e "${CYAN}Backups:${NC}"
    local orig_count=0 backup_count=0 invalid_count=0

    for dir in "$ORIGINAL_BACKUP_ROOT"/*/; do
        [[ -d "$dir" ]] || continue
        local validation
        validation=$(validate_backup_integrity "$dir")
        if [[ "${validation%%|*}" == "VALID" ]]; then
            (( orig_count++ )) || true
        else
            (( invalid_count++ )) || true
        fi
    done

    for dir in "$BACKUP_ROOT"/*/; do
        [[ -d "$dir" ]] || continue
        local validation
        validation=$(validate_backup_integrity "$dir")
        if [[ "${validation%%|*}" == "VALID" ]]; then
            (( backup_count++ )) || true
        else
            (( invalid_count++ )) || true
        fi
    done

    echo -e "  Original:  $orig_count"
    echo -e "  Regular:   $backup_count"
    if [[ $invalid_count -gt 0 ]]; then
        echo -e "  ${RED}Invalid:   $invalid_count (run --cleanup to remove)${NC}"
    fi

    local backup_size
    backup_size=$(du -sh "$APP_DATA_ROOT" 2>/dev/null | cut -f1 || echo "0")
    echo -e "  Total size: ${backup_size:-0}"

    # Log file
    echo ""
    echo -e "${CYAN}Log:${NC}"
    if [[ -f "$LOG_FILE" ]]; then
        local log_size
        log_size=$(du -h "$LOG_FILE" 2>/dev/null | cut -f1 || echo "0")
        echo -e "  File: $LOG_FILE ($log_size)"
        echo -e "  Last 3 entries:"
        tail -3 "$LOG_FILE" 2>/dev/null | while read -r line; do
            echo -e "    ${DIM}$line${NC}"
        done
    else
        echo -e "  ${DIM}No log file${NC}"
    fi

    echo ""
}

# ═══════════════════════════════════════════════════════════════════════════════
#  SILENT MODE
# ═══════════════════════════════════════════════════════════════════════════════
run_silent() {
    log_file "INFO" "Starting in silent mode"
    find_discord_clients

    if [[ ${#CLIENT_NAMES[@]} -eq 0 ]]; then
        # Check for installations without voice modules
        local no_voice=() no_modules=()
        for i in "${!SEARCH_PATHS[@]}"; do
            local base="${SEARCH_PATHS[$i]}"
            [[ -d "$base" ]] || continue
            local app_dirs
            app_dirs=$(find "$base" -maxdepth 1 -type d -name "app-*" 2>/dev/null | head -1 || true)
            if [[ -n "$app_dirs" ]]; then
                if [[ -d "$app_dirs/modules" ]]; then
                    no_voice+=("${SEARCH_NAMES[$i]}")
                else
                    no_modules+=("${SEARCH_NAMES[$i]}")
                fi
            fi
        done

        if [[ ${#no_voice[@]} -gt 0 ]]; then
            echo "[!] Discord found but voice module not downloaded yet."
            echo "    Join a voice channel first, wait 30 seconds, then run again."
            echo "    Affected: ${no_voice[*]}"
            exit 1
        fi
        if [[ ${#no_modules[@]} -gt 0 ]]; then
            echo "[!] Discord installation corrupted (missing modules folder)."
            echo "    Affected: ${no_modules[*]}"
            echo "    Reinstall Discord or run in interactive mode for guided repair."
            exit 1
        fi
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
    local filtered_idx=()
    if [[ -n "$FIX_CLIENT" ]]; then
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
    local indices=()
    if [[ ${#filtered_idx[@]} -gt 0 ]]; then
        indices=("${filtered_idx[@]}")
    else
        indices=("${!CLIENT_NAMES[@]}")
    fi
    for i in "${indices[@]}"; do
        echo "Fixing ${CLIENT_NAMES[$i]} v${CLIENT_VERSIONS[$i]}..."
        if fix_client "$i" "$download_path"; then
            (( success++ )) || true
        else
            (( failed++ )) || true
        fi
    done

    remove_old_backups
    echo "Fixed $success of $(( success + failed )) client(s)"

    # Auto-restart
    if $AUTO_RESTART_DISCORD && [[ $success -gt 0 ]]; then
        echo "Starting Discord..."
        start_discord && echo "[OK] Discord started" || echo "[!] Could not start Discord automatically"
    fi

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

    local backup_list
    backup_list=$(list_backups)
    if [[ -z "$backup_list" ]]; then
        status "[X] No valid backups found" red
        status "    You need to run the fix at least once to create a backup." yellow
        exit 1
    fi

    echo ""
    echo -e "  ${WHITE}${BOLD}Available backups:${NC}"
    echo ""
    local idx=0
    local backup_paths=()
    local backup_originals=()
    while IFS='|' read -r btype bpath bcn bav bdate; do
        (( idx++ )) || true
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

    if [[ -z "$sel" ]] || [[ "$sel" -lt 1 ]] 2>/dev/null || [[ "$sel" -gt $idx ]] 2>/dev/null; then
        status "Restore cancelled" yellow
        exit 0
    fi

    local sel_path="${backup_paths[$(( sel - 1 ))]}"
    local sel_orig="${backup_originals[$(( sel - 1 ))]}"

    if [[ "$sel_orig" == "true" ]]; then
        echo ""
        echo -e "  ${YELLOW}${BOLD}WARNING: This will revert to ORIGINAL mono audio modules.${NC}"
        echo -e "  ${YELLOW}You will lose the stereo fix for the selected client.${NC}"
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

    if [[ -z "$cchoice" ]] || [[ "$cchoice" -lt 1 ]] 2>/dev/null || [[ "$cchoice" -gt ${#CLIENT_NAMES[@]} ]] 2>/dev/null; then
        status "Invalid selection" red
        exit 1
    fi

    local target_voice="${CLIENT_VOICE_PATHS[$(( cchoice - 1 ))]}"
    local target_name="${CLIENT_NAMES[$(( cchoice - 1 ))]}"

    status "" blue
    status "Closing Discord..." blue
    kill_discord

    status "Restoring backup to $target_name..." blue
    if restore_from_backup "$sel_path" "$target_voice" "$sel_orig"; then
        status "" green
        if [[ "$sel_orig" == "true" ]]; then
            status "═══════════════════════════════════════════════════" magenta
            status "  RESTORE COMPLETE — Original mono modules restored" magenta
            status "═══════════════════════════════════════════════════" magenta
        else
            status "═══════════════════════════════════════════════════" green
            status "  RESTORE COMPLETE" green
            status "═══════════════════════════════════════════════════" green
        fi
        status "Restart Discord to apply changes." cyan

        if $AUTO_RESTART_DISCORD; then
            echo ""
            read -rp "  Start Discord now? (Y/n): " start_confirm
            if [[ "${start_confirm,,}" != "n" ]]; then
                start_discord && status "[OK] Discord started" green || status "[!] Could not start Discord automatically" orange
            fi
        fi
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
    load_settings
    rotate_log

    log_file "INFO" "Starting interactive mode v$SCRIPT_VERSION"

    status "Scanning for Discord installations..." blue
    find_discord_clients

    if [[ ${#CLIENT_NAMES[@]} -eq 0 ]]; then
        status "[X] No Discord installations found!" red
        echo ""

        # Check for partial installations
        local found_any=false
        for i in "${!SEARCH_PATHS[@]}"; do
            local base="${SEARCH_PATHS[$i]}"
            if [[ -d "$base" ]]; then
                found_any=true
                local app_dirs
                app_dirs=$(find "$base" -maxdepth 1 -type d -name "app-*" 2>/dev/null | head -1 || true)
                if [[ -n "$app_dirs" ]]; then
                    if [[ -d "$app_dirs/modules" ]]; then
                        echo -e "  ${YELLOW}●${NC} ${SEARCH_NAMES[$i]} — ${YELLOW}modules folder exists but no voice module${NC}"
                        echo -e "    ${DIM}Join a voice channel in Discord to trigger voice module download${NC}"
                    else
                        echo -e "  ${RED}●${NC} ${SEARCH_NAMES[$i]} — ${RED}missing modules folder (corrupted)${NC}"
                        echo -e "    ${DIM}Reinstall Discord to fix this${NC}"
                    fi
                else
                    echo -e "  ${ORANGE}●${NC} ${SEARCH_NAMES[$i]} — ${ORANGE}found config but no app folders${NC}"
                fi
            fi
        done

        if ! $found_any; then
            echo "  Searched the following locations:"
            for p in "${SEARCH_PATHS[@]}"; do
                echo -e "    ${DIM}○ $p${NC}"
            done
            echo ""
            echo "  Make sure Discord is installed and has been opened at least once."
            echo "  If you just installed Discord, join a voice channel first to"
            echo "  download the voice module, then run this script again."
        fi

        exit 1
    fi

    status "[OK] Found ${#CLIENT_NAMES[@]} client(s):" green
    for i in "${!CLIENT_NAMES[@]}"; do
        local node_info="${CLIENT_NODE_SIZES[$i]}"
        local size_fmt
        if [[ "${node_info:-0}" -gt 1048576 ]]; then
            size_fmt="$(( node_info / 1048576 )) MB"
        elif [[ "${node_info:-0}" -gt 0 ]]; then
            size_fmt="$(( node_info / 1024 )) KB"
        else
            size_fmt="?"
        fi
        status "  [$(( i + 1 ))] ${CLIENT_NAMES[$i]} (v${CLIENT_VERSIONS[$i]}, $size_fmt)" cyan
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
        echo -e "${CYAN}══════════════════════════════════════════════════════${NC}"
        echo -e "  ${WHITE}[1]${NC} Fix single client"
        echo -e "  ${GREEN}[2]${NC} Fix ALL clients"
        echo -e "  ${BLUE}[3]${NC} Verify fix status"
        echo -e "  ${MAGENTA}[4]${NC} Restore from backup"
        echo -e "  ${YELLOW}[5]${NC} Check for Discord updates"
        echo -e "  ${CYAN}[6]${NC} Full diagnostics"
        echo -e "  ${DIM}[7]${NC} Cleanup invalid backups"
        echo -e "  ${DIM}[8]${NC} Check for script updates"
        echo -e "  ${DIM}[9]${NC} Open backup folder"
        echo -e "  ${RED}[Q]${NC} Quit"
        echo -e "${CYAN}══════════════════════════════════════════════════════${NC}"
        echo ""
        read -rp "  Choice: " choice

        case "${choice^^}" in
            1) menu_fix_single ;;
            2) menu_fix_all ;;
            3) menu_verify ;;
            4) run_restore ;;
            5) menu_check_updates ;;
            6) run_diagnostics ;;
            7) cleanup_invalid_backups ;;
            8) check_script_update || true ;;
            9) echo "  Backups: $APP_DATA_ROOT"; command -v xdg-open &>/dev/null && xdg-open "$APP_DATA_ROOT" 2>/dev/null || true ;;
            Q) save_settings; echo "Goodbye!"; exit 0 ;;
            *) echo -e "  ${RED}Invalid choice${NC}" ;;
        esac
    done
}

menu_fix_single() {
    echo ""
    echo -e "  ${WHITE}${BOLD}Select client to fix:${NC}"
    echo ""
    for i in "${!CLIENT_NAMES[@]}"; do
        echo -e "  ${WHITE}[$(( i + 1 ))]${NC} ${CLIENT_NAMES[$i]} (v${CLIENT_VERSIONS[$i]})"
    done
    echo -e "  ${RED}[C]${NC} Cancel"
    echo ""
    read -rp "  Choice: " sel

    [[ "${sel^^}" == "C" ]] && return
    if [[ -z "$sel" ]] || [[ "$sel" -lt 1 ]] 2>/dev/null || [[ "$sel" -gt ${#CLIENT_NAMES[@]} ]] 2>/dev/null; then
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
    if kill_discord; then
        status "[OK] Discord processes closed" green
    else
        status "[!] Some processes may still be running, continuing anyway..." orange
    fi
    sleep 1

    # Fix
    if fix_client "$idx" "$download_path"; then
        remove_old_backups
        echo ""
        echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
        echo -e "${GREEN}  ✓ FIX COMPLETED SUCCESSFULLY${NC}"
        echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
        echo ""

        if $AUTO_RESTART_DISCORD; then
            read -rp "  Start Discord now? (Y/n): " start_confirm
            if [[ "${start_confirm,,}" != "n" ]]; then
                start_discord && status "[OK] Discord started" green || status "[!] Could not start Discord — start it manually" orange
            fi
        else
            status "Restart Discord to apply changes." cyan
        fi
    else
        echo ""
        echo -e "${RED}═══════════════════════════════════════════════════${NC}"
        echo -e "${RED}  ✗ FIX FAILED${NC}"
        echo -e "${RED}═══════════════════════════════════════════════════${NC}"
        echo ""
        status "Check the log at: $LOG_FILE" dim
    fi

    rm -rf "$tmp_dir"
}

menu_fix_all() {
    echo ""
    echo -e "  ${WHITE}Fix all ${#CLIENT_NAMES[@]} client(s)?${NC}"
    for i in "${!CLIENT_NAMES[@]}"; do
        echo -e "    ${CYAN}•${NC} ${CLIENT_NAMES[$i]} (v${CLIENT_VERSIONS[$i]})"
    done
    echo ""
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
        if kill_discord; then
            status "[OK] Discord processes closed" green
        else
            status "[!] Some processes may still be running, continuing..." orange
        fi
        sleep 1
    fi

    # Fix all
    local success=0 failed=0 fail_names=()
    for i in "${!CLIENT_NAMES[@]}"; do
        if fix_client "$i" "$download_path"; then
            (( success++ )) || true
        else
            (( failed++ )) || true
            fail_names+=("${CLIENT_NAMES[$i]}")
        fi
    done

    remove_old_backups

    echo ""
    echo -e "${CYAN}═══════════════════════════════════════════════════════${NC}"
    if [[ $failed -eq 0 ]]; then
        echo -e "${GREEN}  ✓ FIX ALL COMPLETE: $success/${#CLIENT_NAMES[@]} successful${NC}"
    else
        echo -e "${YELLOW}  FIX ALL: $success/${#CLIENT_NAMES[@]} successful, $failed failed${NC}"
        for fn in "${fail_names[@]}"; do
            echo -e "    ${RED}✗${NC} $fn"
        done
    fi
    echo -e "${CYAN}═══════════════════════════════════════════════════════${NC}"
    echo ""

    if $AUTO_RESTART_DISCORD && [[ $success -gt 0 ]]; then
        read -rp "  Start Discord now? (Y/n): " start_confirm
        if [[ "${start_confirm,,}" != "n" ]]; then
            start_discord && status "[OK] Discord started" green || status "[!] Could not start Discord — start it manually" orange
        fi
    else
        status "Restart Discord to apply changes." cyan
    fi

    rm -rf "$tmp_dir"
}

menu_verify() {
    echo ""
    status "=== VERIFYING FIX STATUS ===" blue
    echo ""

    for i in "${!CLIENT_NAMES[@]}"; do
        local result
        result=$(verify_fix "${CLIENT_VOICE_PATHS[$i]}" "${CLIENT_NAMES[$i]}")
        local rstatus rmsg rest
        IFS='|' read -r rstatus rmsg rest <<< "$result"

        case "$rstatus" in
            FIXED)
                echo -e "  ${GREEN}[✓]${NC} ${CLIENT_NAMES[$i]}"
                echo -e "      ${GREEN}Stereo fix is active${NC}"
                ;;
            NOTFIXED)
                echo -e "  ${YELLOW}[✗]${NC} ${CLIENT_NAMES[$i]}"
                echo -e "      ${YELLOW}Original mono modules — run fix to enable stereo${NC}"
                ;;
            UNKNOWN)
                echo -e "  ${DIM}[?]${NC} ${CLIENT_NAMES[$i]}"
                echo -e "      ${DIM}$rmsg${NC}"
                ;;
            ERROR)
                echo -e "  ${RED}[X]${NC} ${CLIENT_NAMES[$i]}"
                echo -e "      ${RED}$rmsg${NC}"
                ;;
        esac

        # Show hash info
        IFS='|' read -r _ _ hash size <<< "$result"
        if [[ -n "$hash" ]]; then
            echo -e "      ${DIM}Hash: ${hash:0:16}...  Size: $size bytes${NC}"
        fi
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
                echo -e "         ${YELLOW}Re-running the fix is recommended${NC}"
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
if $DIAG_MODE; then
    run_diagnostics
elif $CLEANUP_MODE; then
    banner
    ensure_app_dirs
    cleanup_invalid_backups
elif $SILENT_MODE || $CHECK_ONLY; then
    check_dependencies
    ensure_app_dirs
    run_silent
elif $RESTORE_MODE; then
    check_dependencies
    run_restore
else
    run_interactive
fi
