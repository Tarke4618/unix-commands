#!/bin/bash

# Dependencies
DEPENDENCIES=(
    "zenity" "notify-send" "ffmpeg" "mediainfo"
    "unrar" "unzip" "p7zip-full" "tar"
    "perl" "sed" "awk"
)

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
