#!/bin/bash

# Photo Management Functions
manage_photos() {
    local source_dir="$1"
    local dest_dir="$2"

    if [ "$DRY_RUN" = "true" ]; then
        zenity --info --text="[DRY RUN] Photo management from '$source_dir' to '$dest_dir'"
        find "$source_dir" -type f | while read -r file; do
            if [[ "${file,,}" =~ \.(jpg|jpeg|png|gif|bmp|tiff|webp)$ ]]; then
                echo "[DRY RUN] Would move '$file' to '$dest_dir/'"
            fi
        done
        find "$source_dir" -type d -empty -delete | while read -r dir; do
            echo "[DRY RUN] Would delete empty directory '$dir'"
        done
        zenity --info --text="[DRY RUN] Photo management preview complete. Check the console for details."
        return
    fi

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
