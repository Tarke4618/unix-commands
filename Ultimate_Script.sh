#!/bin/bash

# Unified Media Utility Tool
# Main entry point for the script

# Source all the script modules
source scripts/config.sh
source scripts/dependencies.sh
source scripts/logging.sh
source scripts/extract.sh
source scripts/photos.sh
source scripts/rename.sh
source scripts/video.sh
source scripts/main.sh

# Main Execution
init_config
check_dependencies
main_menu
