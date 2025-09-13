#!/bin/bash

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
        if [ "$DRY_RUN" = "true" ]; then
            zenity --info --text="[DRY RUN] Would delete archive: $archive"
        else
            rm -f "$archive"
            log_operation "Deleted archive: $archive"
        fi
    fi

    log_operation "Extracted: $archive"
}
