#!/bin/bash

# Required for GUI dialogs
if ! command -v zenity &> /dev/null; then
    echo "Please install zenity first: sudo apt-get install zenity"
    exit 1
fi

# Set your source and destination directories here
SOURCE_DIR="/path/to/your/source/directory"
DEST_DIR="/path/to/your/destination/directory"

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
total_files=$(find "$SOURCE_DIR" -maxdepth 3 -mindepth 1 -type f | wc -l)
current=0

# Find and move files
find "$SOURCE_DIR" -maxdepth 3 -mindepth 1 -type f | while read -r file; do
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
    zenity --info --text="Files have been moved, empty folders cleaned up, and non-image files removed!"
fi
