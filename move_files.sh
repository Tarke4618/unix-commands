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
    percentage=$((current * 100 / total_files))
    echo "$percentage"
    echo "# Moving file $current of $total_files"
    mv "$file" "$DEST_DIR"
done

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
    zenity --info --text="Files have been moved successfully!"
fi
