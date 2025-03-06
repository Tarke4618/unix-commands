#!/bin/bash

DEPENDENCIES=("ffmpeg" "mediainfo" "zenity")
ZENITY_COMMON="--width=600 --height=200"

check_dependencies() {
    for dep in "${DEPENDENCIES[@]}"; do
        if ! command -v "$dep" &> /dev/null; then
            zenity --question --title="Dependencies" \
                --text="Install $dep?" \
                --ok-label="Install" && \
                sudo apt-get install -y "$dep"
        fi
    done
}

show_progress() {
    local pid=$1
    local input=$2
    local duration=$(mediainfo --Inform="Video;%Duration/String3%" "$input" | cut -d. -f1)
    local duration_seconds=$(echo "$duration" | awk -F: '{print $1*3600 + $2*60 + $3}')

    while kill -0 $pid 2>/dev/null; do
        if [ -f "/tmp/progress.txt" ]; then
            current_time=$(tail -n 1 "/tmp/progress.txt" | grep -o "time=[0-9:.]* " | cut -d= -f2)
            if [ ! -z "$current_time" ]; then
                current_seconds=$(echo "$current_time" | awk -F: '{print $1*3600 + $2*60 + $3}')
                progress=$((current_seconds * 100 / duration_seconds))
                echo "$progress"
                echo "# Processing: $progress% ($(date -u -d @"$current_seconds" +"%H:%M:%S") / $duration)"
            fi
        fi
        sleep 1
    done
}

add_soft_subtitles() {
    local video="$1"
    local subtitle="$2"
    local output="$3"
    local ext="${output##*.}"
    local subtitle_codec="srt"
    [[ "$ext" == "mp4" ]] && subtitle_codec="mov_text"
    
    nice -n 10 ffmpeg -i "$video" -i "$subtitle" \
        -map 0:v -map 0:a -map 1 \
        -c:v copy -c:a copy -c:s "$subtitle_codec" \
        -progress "/tmp/progress.txt" \
        "$output" 2>/dev/null &
    
    local pid=$!
    show_progress $pid "$video" | zenity --progress \
        --title="Adding Subtitles" \
        --text="Starting..." \
        --percentage=0 \
        --auto-close \
        --cancel-label="Cancel"
    
    if [ $? -eq 1 ]; then
        kill $pid 2>/dev/null
        rm -f "$output" "/tmp/progress.txt"
        exit 1
    fi
    rm -f "/tmp/progress.txt"
}

compress_video() {
    local input="$1"
    local output="$2"
    local quality="$3"
    
    local presets=([high]="veryfast:18" [medium]="veryfast:23" [low]="veryfast:28")
    local preset_values=${presets[$quality]}
    local speed="${preset_values%:*}"
    local crf="${preset_values#*:}"
    
    nice -n 10 ffmpeg -i "$input" \
        -c:v libx264 -preset "$speed" -crf "$crf" \
        -c:a aac -b:a 128k \
        -threads $(( $(nproc) / 2 )) \
        -progress "/tmp/progress.txt" \
        "$output" 2>/dev/null &
    
    local pid=$!
    show_progress $pid "$input" | zenity --progress \
        --title="Compressing Video" \
        --text="Starting..." \
        --percentage=0 \
        --auto-close \
        --cancel-label="Cancel"
    
    if [ $? -eq 1 ]; then
        kill $pid 2>/dev/null
        rm -f "$output" "/tmp/progress.txt"
        exit 1
    fi
    rm -f "/tmp/progress.txt"
}

main() {
    check_dependencies
    
    local file=$(zenity --file-selection \
        --title="Select Video" \
        --file-filter="Videos | *.mp4 *.mkv *.avi *.mov *.ts")
    [ -z "$file" ] && exit 1
    
    local operation=$(zenity --list \
        --title="Select Operation" \
        --column="Operation" \
        "Add Subtitles" \
        "Compress Video")
    
    case "$operation" in
        "Add Subtitles")
            local subtitle=$(zenity --file-selection \
                --title="Select Subtitle" \
                --file-filter="Subtitles | *.srt *.ass *.ssa")
            [ -z "$subtitle" ] && exit 1
            local output="${file%.*}_sub.${file##*.}"
            add_soft_subtitles "$file" "$subtitle" "$output"
            ;;
        "Compress Video")
            local quality=$(zenity --list \
                --title="Quality" \
                --column="Level" \
                "high" "medium" "low")
            local output="${file%.*}_compressed.${file##*.}"
            compress_video "$file" "$output" "$quality"
            ;;
    esac

    [ $? -eq 0 ] && zenity --info --text="Operation completed successfully!"
}

main
