#!/bin/bash

# Video Processing Functions
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

process_video() {
    local input="$1"
    local output="$2"
    local operation="$3"
    local options="$4"

    if [ "$DRY_RUN" = "true" ]; then
        zenity --info --text="[DRY RUN] Would process video: '$input' with operation '$operation'"
        return
    fi

    case "$operation" in
        "compress")
            local quality="${options:-medium}"
            local presets=([high]="veryfast:18" [medium]="veryfast:23" [low]="veryfast:28")
            local preset_values=${presets[$quality]}
            local speed="${preset_values%:*}"
            local crf="${preset_values#*:}"

            nice -n 10 ffmpeg -i "$input" \
                -c:v libx264 -preset "$speed" -crf "$crf" \
                -c:a aac -b:a 128k \
                -threads $(( $(nproc) / 2 )) \
                -progress "/tmp/progress.txt" \
                -y "$output" 2>/dev/null &;;

        "subtitles")
            local subtitle="$options"
            local ext="${output##*.}"
            local subtitle_codec="srt"
            [[ "$ext" == "mp4" ]] && subtitle_codec="mov_text"

            nice -n 10 ffmpeg -i "$input" -i "$subtitle" \
                -map 0:v -map 0:a -map 1 \
                -c:v copy -c:a copy -c:s "$subtitle_codec" \
                -progress "/tmp/progress.txt" \
                -y "$output" 2>/dev/null &;;
    esac

    local pid=$!
    show_progress $pid "$input" | zenity --progress \
        --title="Processing Video" \
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

    log_operation "Processed video: $input ($operation)"
}
