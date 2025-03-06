#!/bin/bash

# Unified Media Utility Tool
# Combines functionality for file extraction, photo management,
# file renaming, and video processing

# Global Configuration
CONFIG_DIR="$HOME/.config/media-utility"
SETTINGS_FILE="$CONFIG_DIR/settings.conf"
LOG_FILE="$CONFIG_DIR/operations.log"

# Dependencies
DEPENDENCIES=(
    "zenity" "notify-send" "ffmpeg" "mediainfo"
    "unrar" "unzip" "p7zip-full" "tar"
    "perl" "sed" "awk"
)

# Supported archive formats
SUPPORTED_ARCHIVES=(
    "*.rar" "*.r[0-9][0-9]" "*.zip" "*.7z"
    "*.tar.gz" "*.tgz" "*.tar.xz" "*.txz"
    "*.tar.bz2" "*.tbz2" "*.gz" "*.bz2"
    "*.xz" "*.Z" "*.iso" "*.deb" "*.rpm"
)

# Supported image formats
SUPPORTED_IMAGES=(
    "*.jpg" "*.jpeg" "*.png" "*.gif"
    "*.bmp" "*.tiff" "*.webp"
)

# Supported video formats
SUPPORTED_VIDEOS=(
    "*.mp4" "*.mkv" "*.avi" "*.mov" "*.ts"
)

# Initialization Functions
init_config() {
    mkdir -p "$CONFIG_DIR"
    touch "$LOG_FILE"
    
    if [ ! -f "$SETTINGS_FILE" ]; then
        cat > "$SETTINGS_FILE" << EOF
DELETE_ARCHIVES=false
SHOW_PROGRESS=true
CREATE_SUBFOLDER=false
BACKUP_ENABLED=true
EOF
    fi
    source "$SETTINGS_FILE"
}

check_dependencies() {
    local missing=()
    for dep in "${DEPENDENCIES[@]}"; do
        if ! command -v "$dep" &> /dev/null; then
            missing+=("$dep")
        fi
    done

    if [ ${#missing[@]} -ne 0 ]; then
        zenity --question \
            --title="Dependencies Missing" \
            --text="Missing dependencies:\n\n${missing[*]}\n\nInstall now?" \
            --width=400
        if [ $? -eq 0 ]; then
            sudo apt-get install -y "${missing[@]}"
        else
            zenity --error \
                --title="Error" \
                --text="Cannot continue without required dependencies."
            exit 1
        fi
    fi
}

log_operation() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

# Archive Extraction Functions
extract_archive() {
    local archive="$1"
    local extract_dir="$(dirname "$archive")"
    local base_name="$(basename "$archive")"

    (
    echo "0"; echo "# Analyzing archive..."
    
    case "$archive" in
        *.rar|*.r[0-9][0-9])
            unrar x "$archive" "$extract_dir";;
        *.zip)
            unzip "$archive" -d "$extract_dir";;
        *.7z)
            7z x "$archive" -o"$extract_dir";;
        *.tar.gz|*.tgz)
            tar -xzf "$archive" -C "$extract_dir";;
        *.tar.bz2|*.tbz2)
            tar -xjf "$archive" -C "$extract_dir";;
        *.tar.xz|*.txz)
            tar -xJf "$archive" -C "$extract_dir";;
        *)
            zenity --error --text="Unsupported format: $base_name"
            return 1;;
    esac

    echo "100"; echo "# Complete!"
    ) | zenity --progress \
        --title="Extracting Archive" \
        --text="Processing $base_name..." \
        --percentage=0 \
        --auto-close

    if [ "$DELETE_ARCHIVES" = "true" ]; then
        rm -f "$archive"
    fi
    
    log_operation "Extracted: $archive"
}

# Photo Management Functions
manage_photos() {
    local source_dir="$1"
    local dest_dir="$2"

    (
    echo "0"; echo "# Preparing..."
    
    local total_files=$(find "$source_dir" -type f | wc -l)
    local current=0

    find "$source_dir" -type f | while read -r file; do
        ((current++))
        local percent=$((current * 100 / total_files))
        echo "$percent"
        echo "# Moving file $current of $total_files"
        
        if [[ "${file,,}" =~ \.(jpg|jpeg|png|gif|bmp|tiff|webp)$ ]]; then
            mv "$file" "$dest_dir/"
        fi
    done

    find "$source_dir" -type d -empty -delete

    echo "100"; echo "# Complete!"
    ) | zenity --progress \
        --title="Managing Photos" \
        --text="Processing..." \
        --percentage=0 \
        --auto-close

    log_operation "Moved photos from $source_dir to $dest_dir"
}

# File Renaming Functions
rename_files() {
    local dir="$1"
    local pattern="$2"
    local replacement="$3"
    local mode="$4"

    if [ "$BACKUP_ENABLED" = "true" ]; then
        backup_directory "$dir"
    fi

    (
    echo "0"; echo "# Scanning files..."
    
    local total_files=$(find "$dir" -type f | wc -l)
    local current=0

    find "$dir" -type f | while read -r file; do
        ((current++))
        local percent=$((current * 100 / total_files))
        local base_name=$(basename "$file")
        local dir_name=$(dirname "$file")
        local new_name

        case "$mode" in
            "simple")
                new_name=$(echo "$base_name" | sed "s|$pattern|$replacement|g");;
            "regex")
                new_name=$(echo "$base_name" | perl -pe "s/$pattern/$replacement/g");;
            "smart")
                new_name=$(echo "$base_name" | perl -pe 's/(?<=\d)(?=\D)|(?<=\D)(?=\d)|(?<=[a-z])(?=[A-Z])/ /g');;
        esac

        if [ "$base_name" != "$new_name" ]; then
            mv "$file" "$dir_name/$new_name"
        fi

        echo "$percent"
        echo "# Processing: $current of $total_files"
    done

    echo "100"; echo "# Complete!"
    ) | zenity --progress \
        --title="Renaming Files" \
        --text="Processing..." \
        --percentage=0 \
        --auto-close

    log_operation "Renamed files in $dir using pattern: $pattern"
}

# Video Processing Functions
process_video() {
    local input="$1"
    local output="$2"
    local operation="$3"
    local options="$4"

    case "$operation" in
        "compress")
            local quality="${options:-medium}"
            local presets=([high]="veryfast:18" [medium]="veryfast:23" [low]="veryfast:28")
            local preset_values=${presets[$quality]}
            local speed="${preset_values%:*}"
            local crf="${preset_values#*:}"
            
            ffmpeg -i "$input" \
                -c:v libx264 -preset "$speed" -crf "$crf" \
                -c:a aac -b:a 128k \
                -y "$output" &;;
            
        "subtitles")
            local subtitle="$options"
            ffmpeg -i "$input" -i "$subtitle" \
                -c:v copy -c:a copy -c:s mov_text \
                -y "$output" &;;
    esac

    local pid=$!
    show_progress $pid "$input" | zenity --progress \
        --title="Processing Video" \
        --text="Starting..." \
        --percentage=0 \
        --auto-close

    log_operation "Processed video: $input ($operation)"
}

show_progress() {
    local pid=$1
    local input=$2
    local duration=$(mediainfo --Inform="Video;%Duration/String3%" "$input")
    
    while kill -0 $pid 2>/dev/null; do
        echo "# Processing... Please wait"
        sleep 1
    done
}

# Main Menu
main_menu() {
    while true; do
        local choice=$(zenity --list \
            --title="Media Utility Tool" \
            --text="Select an operation:" \
            --column="Operation" --column="Description" \
            "Extract Archives" "Extract compressed files" \
            "Manage Photos" "Organize and move photos" \
            "Rename Files" "Batch rename files" \
            "Process Videos" "Compress or add subtitles" \
            "Settings" "Configure application settings" \
            "Exit" "Exit application" \
            --width=600 --height=400)

        case "$choice" in
            "Extract Archives")
                local archive=$(zenity --file-selection \
                    --title="Select Archive" \
                    --file-filter="Archives | ${SUPPORTED_ARCHIVES[*]}")
                [ -n "$archive" ] && extract_archive "$archive";;
                
            "Manage Photos")
                local source=$(zenity --file-selection --directory \
                    --title="Select Source Directory")
                local dest=$(zenity --file-selection --directory \
                    --title="Select Destination Directory")
                [ -n "$source" ] && [ -n "$dest" ] && manage_photos "$source" "$dest";;
                
            "Rename Files")
                local dir=$(zenity --file-selection --directory \
                    --title="Select Directory")
                local mode=$(zenity --list \
                    --title="Select Rename Mode" \
                    --column="Mode" \
                    "simple" "regex" "smart")
                [ -n "$dir" ] && [ -n "$mode" ] && rename_files "$dir" \
                    "$(zenity --entry --title="Pattern" --text="Enter pattern:")" \
                    "$(zenity --entry --title="Replacement" --text="Enter replacement:")" \
                    "$mode";;
                
            "Process Videos")
                local video=$(zenity --file-selection \
                    --title="Select Video" \
                    --file-filter="Videos | ${SUPPORTED_VIDEOS[*]}")
                local operation=$(zenity --list \
                    --title="Select Operation" \
                    --column="Operation" \
                    "compress" "subtitles")
                
                if [ -n "$video" ] && [ -n "$operation" ]; then
                    local output="${video%.*}_processed.${video##*.}"
                    local options
                    
                    case "$operation" in
                        "compress")
                            options=$(zenity --list \
                                --title="Select Quality" \
                                --column="Quality" \
                                "high" "medium" "low");;
                        "subtitles")
                            options=$(zenity --file-selection \
                                --title="Select Subtitle File" \
                                --file-filter="Subtitles | *.srt *.ass *.ssa");;
                    esac
                    
                    [ -n "$options" ] && process_video "$video" "$output" "$operation" "$options"
                fi;;
                
            "Settings")
                configure_settings;;
                
            "Exit")
                exit 0;;
                
            *)
                exit 0;;
        esac
    done
}

configure_settings() {
    local settings=$(zenity --forms \
        --title="Settings" \
        --text="Configure Settings" \
        --add-checkbox="Delete archives after extraction" \
        --add-checkbox="Show progress dialogs" \
        --add-checkbox="Create subfolders" \
        --add-checkbox="Enable backups")

    if [ -n "$settings" ]; then
        IFS='|' read -r delete_archives show_progress create_subfolder backup_enabled <<< "$settings"
        
        cat > "$SETTINGS_FILE" << EOF
DELETE_ARCHIVES=${delete_archives:-false}
SHOW_PROGRESS=${show_progress:-true}
CREATE_SUBFOLDER=${create_subfolder:-false}
BACKUP_ENABLED=${backup_enabled:-true}
EOF
        
        source "$SETTINGS_FILE"
    fi
}

# Main Execution
init_config
check_dependencies
main_menu
