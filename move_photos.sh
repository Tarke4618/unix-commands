#!/bin/bash

# Required for GUI dialogs
if ! command -v zenity &> /dev/null; then
    zenity --error --text="Please install zenity first:\nsudo apt-get install zenity"
    exit 1
fi

# Prompt for source directory
SOURCE_DIR=$(zenity --file-selection --directory \
                   --title="Select Source Directory" \
                   --filename="$HOME/")

# Exit if source directory selection was canceled
if [ -z "$SOURCE_DIR" ]; then
    exit 1
fi

# Prompt for destination directory
DEST_DIR=$(zenity --file-selection --directory \
                  --title="Select Destination Directory" \
                  --filename="$HOME/")

# Exit if destination directory selection was canceled
if [ -z "$DEST_DIR" ]; then
    exit 1
fi

# Confirm the operation
zenity --question \
    --title="Confirm Operation" \
    --text="This will:\n\n1. Move all files from:\n$SOURCE_DIR\n\nto:\n$DEST_DIR\n\n2. Remove empty folders from source\n3. Keep only images in destination\n\nContinue?" \
    --width=400

# Exit if user didn't confirm
if [ $? -ne 0 ]; then
    exit 1
fi

# Show progress dialog
(
echo "0"
echo "# Checking directories..."

# Check if source directory exists
if [ ! -d "$SOURCE_DIR" ]; then
    zenity --error --text="Source directory does not exist: $SOURCE_DIR"
    exit 1
fi

# Create destination directory if it doesn't exist
mkdir -p "$DEST_DIR"

echo "25"
echo "# Finding files..."

# Count total files to move
total_files=$(find "$SOURCE_DIR" -maxdepth 5 -mindepth 1 -type f | wc -l)
current=0

# Find and move files
find "$SOURCE_DIR" -maxdepth 5 -mindepth 1 -type f | while read -r file; do
    ((current++))
    percentage=$((current * 75 / total_files)) # Using 75% for moving files
    echo "$percentage"
    echo "# Moving file $current of $total_files"
    mv "$file" "$DEST_DIR"
done

echo "80"
echo "# Cleaning up empty directories in source..."

# Remove empty directories (including nested ones) up to 3 levels deep
find "$SOURCE_DIR" -mindepth 1 -maxdepth 3 -type d -empty -delete

echo "90"
echo "# Cleaning up non-image files in destination..."

# Remove all files except images and GIFs in destination
# Using case-insensitive matches for file extensions
find "$DEST_DIR" -type f ! -iname "*.jpg" \
                          ! -iname "*.jpeg" \
                          ! -iname "*.png" \
                          ! -iname "*.gif" \
                          ! -iname "*.bmp" \
                          ! -iname "*.tiff" \
                          ! -iname "*.webp" \
                          -delete

echo "100"
echo "# Complete!"
) | zenity --progress \
    --title="Moving Files" \
    --text="Starting..." \
    --percentage=0 \
    --auto-close \
    --width=300

# Show completion message
if [ $? -eq 0 ]; then
    zenity --info --text="Operation completed successfully!\n\nFiles have been moved, empty folders cleaned up, and non-image files removed!"
fi
