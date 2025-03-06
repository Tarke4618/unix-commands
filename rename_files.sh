#!/bin/bash

# Utility function to check and install dependencies
check_dependencies() {
    local deps=("zenity" "perl" "sed" "awk")
    for dep in "${deps[@]}"; do
        if ! command -v "$dep" &> /dev/null; then
            echo "Installing $dep..."
            sudo apt-get install -y "$dep"
        fi
    done
}

# Enhanced backup with checksums
backup_files() {
    local dir="$1"
    local backup_dir="$HOME/.file_rename_backups"
    local backup_file="$backup_dir/rename_backup_$(date +%Y%m%d_%H%M%S).txt"
    
    mkdir -p "$backup_dir"
    
    (
        echo "# Backup created on $(date)"
        echo "# Original directory: $dir"
        find "$dir" -depth -printf "%p|%P|%y|%m|%s|%T@\n" | while IFS='|' read -r path relpath type perms size mtime; do
            if [ -f "$path" ]; then
                checksum=$(md5sum "$path" | cut -d' ' -f1)
                echo "$path|$relpath|$type|$perms|$size|$mtime|$checksum"
            else
                echo "$path|$relpath|$type|$perms|$size|$mtime|"
            fi
        done
    ) > "$backup_file"
    
    echo "$backup_file"
}

# Multi-pattern rename function
multi_pattern_rename() {
    local dir="$1"
    local patterns_file="$2"
    local options="$3"
    local total_items=$(find "$dir" \( -type f -o -type d \) | wc -l)
    local renamed=0
    local errors=0

    (
        echo "0"
        echo "# Processing files..."
        current=0

        while IFS='|' read -r pattern replacement type case_sensitive; do
            find "$dir" -type f -print0 | while IFS= read -r -d '' file; do
                ((current++))
                local base=$(basename "$file")
                local parent=$(dirname "$file")
                local new_name="$base"

                case "$type" in
                    "regex")
                        local perl_flags="$([[ "$case_sensitive" == "true" ]] && echo '' || echo 'i')"
                        new_name=$(echo "$base" | perl -pe "s$pattern$replacement$perl_flags")
                        ;;
                    "simple")
                        if [[ "$case_sensitive" == "true" ]]; then
                            new_name=$(echo "$base" | sed "s|$pattern|$replacement|g")
                        else
                            new_name=$(echo "$base" | sed "s|$pattern|$replacement|gI")
                        fi
                        ;;
                    "space")
                        new_name=$(echo "$base" | sed -E 's/([0-9])([A-Za-z])/\1 \2/g; s/([A-Za-z])([0-9])/\1 \2/g')
                        ;;
                    "smart_space")
                        new_name=$(echo "$base" | perl -pe 's/(?<=\d)(?=\D)|(?<=\D)(?=\d)|(?<=[a-z])(?=[A-Z])/ /g')
                        ;;
                esac

                if [ "$base" != "$new_name" ]; then
                    if mv "$file" "$parent/$new_name" 2>/dev/null; then
                        ((renamed++))
                    else
                        ((errors++))
                    fi
                fi
                echo $((current * 100 / (total_items * $(wc -l < "$patterns_file"))))
            done
        done < "$patterns_file"

        echo "100"
    ) | zenity --progress \
               --title="Multi-Pattern Renaming" \
               --text="Processing..." \
               --percentage=0 \
               --auto-close \
               --width=400
}

# Function to get multiple patterns
get_patterns() {
    local temp_dir=$(mktemp -d)
    local patterns_file="$temp_dir/patterns.txt"
    local num_patterns=$(zenity --scale \
        --title="Number of Patterns" \
        --text="How many patterns do you want to apply? (1-10)" \
        --min-value=1 \
        --max-value=10 \
        --value=1 \
        --step=1)

    [ -z "$num_patterns" ] && return 1

    for ((i=1; i<=num_patterns; i++)); do
        local pattern_type=$(zenity --list \
            --title="Pattern Type #$i" \
            --text="Select pattern type:" \
            --radiolist \
            --column="Select" \
            --column="Type" \
            TRUE "Simple Replace" \
            FALSE "Regular Expression" \
            FALSE "Smart Spacing" \
            FALSE "Number-Letter Spacing")

        [ -z "$pattern_type" ] && return 1

        case "$pattern_type" in
            "Simple Replace")
                local pattern=$(zenity --entry --title="Pattern #$i" --text="Enter text to find:")
                local replacement=$(zenity --entry --title="Replacement #$i" --text="Enter replacement:")
                echo "$pattern|$replacement|simple|true" >> "$patterns_file"
                ;;
            "Regular Expression")
                local pattern=$(zenity --entry --title="Regex #$i" --text="Enter regex pattern:")
                local replacement=$(zenity --entry --title="Replacement #$i" --text="Enter replacement pattern:")
                echo "$pattern|$replacement|regex|true" >> "$patterns_file"
                ;;
            "Smart Spacing")
                echo ".|.|smart_space|true" >> "$patterns_file"
                ;;
            "Number-Letter Spacing")
                echo ".|.|space|true" >> "$patterns_file"
                ;;
        esac
    done

    echo "$patterns_file"
}

# Main function
main() {
    check_dependencies

    local dir=$(zenity --file-selection --directory --title="Select Directory")
    [ -z "$dir" ] && exit 1

    local patterns_file=$(get_patterns)
    [ -z "$patterns_file" ] && exit 1

    local options=$(show_advanced_options)
    local backup_file=$(backup_files "$dir") || exit 1

    multi_pattern_rename "$dir" "$patterns_file" "$options"

    if ! zenity --question \
        --title="Complete" \
        --text="Renaming complete. Keep changes?"; then
        restore_backup "$backup_file"
    else
        zenity --info \
            --title="Complete" \
            --text="Changes have been kept.\nBackup saved at:\n$backup_file"
    fi

    rm -f "$patterns_file"
}

# Show advanced options dialog
show_advanced_options() {
    zenity --forms \
        --title="Advanced Options" \
        --text="Configure Options" \
        --add-checkbox="Process hidden files" \
        --add-checkbox="Recursive processing" \
        --add-checkbox="Preview changes" \
        --add-checkbox="Create log file"
}

main
