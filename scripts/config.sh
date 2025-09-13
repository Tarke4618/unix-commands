#!/bin/bash

# Global Configuration
CONFIG_DIR="$HOME/.config/media-utility"
SETTINGS_FILE="$CONFIG_DIR/settings.conf"
LOG_FILE="$CONFIG_DIR/operations.log"

# Supported archive formats
SUPPORTED_ARCHIVES=(
    "*.rar" "*.r[0-9][0-9]" "*.zip" "*.7z"
    "*.tar.gz" "*.tgz" "*.tar.xz" "*.txz"
    "*.tar.bz2" "*.tbz2" "*.gz" "*.bz2"
    "*.xz" "*.Z" "*.iso" "*.deb" "*.rpm"
)

# Supported image formats
SUPPORTED_IMAGES=(
    "*.jpg" "*.jpeg" "*.png" "*.gif"
    "*.bmp" "*.tiff" "*.webp"
)

# Supported video formats
SUPPORTED_VIDEOS=(
    "*.mp4" "*.mkv" "*.avi" "*.mov" "*.ts"
)

# Initialization Functions
init_config() {
    mkdir -p "$CONFIG_DIR"
    touch "$LOG_FILE"

    if [ ! -f "$SETTINGS_FILE" ]; then
        cat > "$SETTINGS_FILE" << EOF
DELETE_ARCHIVES=false
SHOW_PROGRESS=true
CREATE_SUBFOLDER=false
BACKUP_ENABLED=true
DRY_RUN=false
EOF
    fi
    source "$SETTINGS_FILE"
}

configure_settings() {
    local settings=$(zenity --forms \
        --title="Settings" \
        --text="Configure Settings" \
        --add-checkbox="Delete archives after extraction" \
        --add-checkbox="Show progress dialogs" \
        --add-checkbox="Create subfolders" \
        --add-checkbox="Enable backups" \
        --add-checkbox="Dry run (preview changes)")

    if [ -n "$settings" ]; then
        IFS='|' read -r delete_archives show_progress create_subfolder backup_enabled dry_run <<< "$settings"

        cat > "$SETTINGS_FILE" << EOF
DELETE_ARCHIVES=${delete_archives:-false}
SHOW_PROGRESS=${show_progress:-true}
CREATE_SUBFOLDER=${create_subfolder:-false}
BACKUP_ENABLED=${backup_enabled:-true}
DRY_RUN=${dry_run:-false}
EOF

        source "$SETTINGS_FILE"
    fi
}
