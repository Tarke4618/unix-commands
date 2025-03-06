#!/bin/bash

# Dependencies required
DEPENDENCIES=("unrar" "unzip" "p7zip-full" "tar" "zenity" "notify-send")

# Configuration
CONFIG_DIR="$HOME/.config/powerful-extractor"
SETTINGS_FILE="$CONFIG_DIR/settings.conf"
LOG_FILE="$CONFIG_DIR/extraction.log"

SUPPORTED_FORMATS=(
    "*.rar" "*.r[0-9][0-9]"
    "*.zip" "*.7z" "*.tar.gz" "*.tgz"
    "*.tar.xz" "*.txz" "*.tar.bz2" "*.tbz2"
    "*.gz" "*.bz2" "*.xz" "*.Z"
    "*.iso" "*.deb" "*.rpm"
    "*.cab" "*.arj" "*.lzh" "*.ace"
    "*.img" "*.dmg" "*.wim"
    "*.cpio" "*.squashfs" "*.xar"
)

# Initialize configuration
init_config() {
    mkdir -p "$CONFIG_DIR"
    touch "$LOG_FILE"
    
    if [ ! -f "$SETTINGS_FILE" ]; then
        cat > "$SETTINGS_FILE" << EOF
DELETE_ARCHIVES=true
SHOW_PROGRESS=true
CREATE_SUBFOLDER=false
EOF
    fi
    source "$SETTINGS_FILE"
}

log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

check_dependencies() {
    local missing=()
    for dep in "${DEPENDENCIES[@]}"; do
        case "$dep" in
            "p7zip-full")
                if ! dpkg-query -W -f='${Status}' p7zip-full 2>/dev/null | grep -q "install ok installed"; then
                    missing+=("$dep")
                fi
                ;;
            *)
                if ! command -v "$dep" &>/dev/null; then
                    missing+=("$dep")
                fi
                ;;
        esac
    done

    if [ ${#missing[@]} -ne 0 ]; then
        zenity --question --title="Dependencies Missing" --text="The following dependencies are missing:\n\n${missing[*]}\n\nInstall now?" --width=400
        if [ $? -eq 0 ]; then
            sudo apt-get install -y ${missing[*]}
        else
            zenity --error --title="Missing Dependencies" --text="Cannot continue without installing dependencies. Exiting." --width=300
            exit 1
        fi
    fi
}

show_progress() {
    local pid=$1
    local text=$2
    (
        while kill -0 $pid 2>/dev/null; do
            echo "# $text"
            sleep 1
        done
    ) | zenity --progress --title="Progress" --text="$text" --percentage=0 --width=400 --auto-close --no-cancel
}

extract_archive() {
    local archive="$1"
    local base_name=$(basename "$archive")
    local extract_dir=$(dirname "$archive")

    case "$archive" in
        *.rar|*.r[0-9][0-9])
            # Handle split RAR files
            local rar_main="$(echo "$archive" | sed 's/\.r[0-9][0-9]$/.rar/')"
            if [[ "$archive" =~ \.r[0-9][0-9]$ && -f "$rar_main" ]]; then
                archive="$rar_main"
            fi
            unrar x "$archive" "$extract_dir" &
            pid=$!
            show_progress $pid "Extracting $base_name..."
            wait $pid
            # Delete all parts of split RAR files
            if [ "$DELETE_ARCHIVES" = "true" ]; then
                find "$extract_dir" -type f \( -name "$(basename "$archive")" -o -name "*.r[0-9][0-9]" \) -delete
                zenity --info --title="Archive Deleted" --text="Deleted archive: $base_name and its parts" --width=300
            fi;;
        *.zip)
            unzip "$archive" -d "$extract_dir" &
            pid=$!
            show_progress $pid "Extracting $base_name..."
            wait $pid
            if [ "$DELETE_ARCHIVES" = "true" ]; then
                rm -f "$archive"
                zenity --info --title="Archive Deleted" --text="Deleted archive: $base_name" --width=300
            fi;;
        *.7z)
            7z x "$archive" -o"$extract_dir" &
            pid=$!
            show_progress $pid "Extracting $base_name..."
            wait $pid
            if [ "$DELETE_ARCHIVES" = "true" ]; then
                rm -f "$archive"
                zenity --info --title="Archive Deleted" --text="Deleted archive: $base_name" --width=300
            fi;;
        *.tar.gz|*.tgz)
            tar -xvzf "$archive" -C "$extract_dir" &
            pid=$!
            show_progress $pid "Extracting $base_name..."
            wait $pid
            if [ "$DELETE_ARCHIVES" = "true" ]; then
                rm -f "$archive"
                zenity --info --title="Archive Deleted" --text="Deleted archive: $base_name" --width=300
            fi;;
        *.tar.bz2|*.tbz2)
            tar -xvjf "$archive" -C "$extract_dir" &
            pid=$!
            show_progress $pid "Extracting $base_name..."
            wait $pid
            if [ "$DELETE_ARCHIVES" = "true" ]; then
                rm -f "$archive"
                zenity --info --title="Archive Deleted" --text="Deleted archive: $base_name" --width=300
            fi;;
        *.tar.xz|*.txz)
            tar -xvJf "$archive" -C "$extract_dir" &
            pid=$!
            show_progress $pid "Extracting $base_name..."
            wait $pid
            if [ "$DELETE_ARCHIVES" = "true" ]; then
                rm -f "$archive"
                zenity --info --title="Archive Deleted" --text="Deleted archive: $base_name" --width=300
            fi;;
        *)
            zenity --error --title="Unsupported Format" --text="The file format is not supported: $base_name" --width=300
            log_message "Unsupported file: $base_name"
            return;;
    esac

    log_message "Extracted $base_name to $extract_dir"
    zenity --info --title="Extraction Complete" --text="Successfully extracted: $base_name" --width=300
}

main_menu() {
    while true; do
        local choice=$(zenity --list --title="Powerful Extractor" \
            --text="<span font='16' color='#4a90d9'>Select an option:</span>" \
            --column="Option" --column="Description" \
            "Extract" "Extract files from an archive" \
            "Exit" "Exit the application" --width=500 --height=300 --ok-label="Select")

        case "$choice" in
            "Extract")
                local archive=$(zenity --file-selection --title="Select Archive to Extract" \
                    --file-filter="Archives | ${SUPPORTED_FORMATS[*]}" \
                    --file-filter="All Files | *")

                if [ -n "$archive" ]; then
                    extract_archive "$archive"
                fi
                ;;
            "Exit")
                exit 0
                ;;
            *)
                zenity --error --title="Invalid Option" --text="Please select a valid option." --width=300
                ;;
        esac
    done
}

# Main Execution
init_config
check_dependencies
main_menu

