#!/bin/bash

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
