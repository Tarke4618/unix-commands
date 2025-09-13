#!/bin/bash

# File Renaming Functions
backup_directory() {
    local dir="$1"
    local backup_file="$CONFIG_DIR/backup-$(date +%Y%m%d%H%M%S).tar.gz"

    if [ "$DRY_RUN" = "true" ]; then
        zenity --info --text="[DRY RUN] Would create backup of '$dir' to '$backup_file'"
        return
    fi

    tar -czf "$backup_file" -C "$dir" .
    log_operation "Created backup of '$dir' to '$backup_file'"
    zenity --info --text="Backup created at:\n$backup_file"
}

rename_files() {
    local dir="$1"
    local pattern="$2"
    local replacement="$3"
    local mode="$4"

    if [ "$BACKUP_ENABLED" = "true" ]; then
        backup_directory "$dir"
    fi

    if [ "$DRY_RUN" = "true" ]; then
        zenity --info --text="[DRY RUN] File renaming in '$dir'"
        find "$dir" -type f | while read -r file; do
            local base_name=$(basename "$file")
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
                echo "[DRY RUN] Would rename '$base_name' to '$new_name'"
            fi
        done
        zenity --info --text="[DRY RUN] File renaming preview complete. Check the console for details."
        return
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
