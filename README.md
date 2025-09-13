# Media Utility Suite

This repository contains a suite of tools for managing media files. It is divided into two main components: a powerful shell script for general file management and a set of specialized Python tools for organizing adult media.

## 1. Ultimate Media Utility Script

`Ultimate_Script.sh` is a versatile shell script that provides a graphical user interface (GUI) for various file management tasks.

### Features:

*   **Archive Extraction:** Extract a variety of archive formats.
*   **Photo Management:** Move photos from a source directory to a destination, cleaning up empty folders.
*   **File Renaming:** Batch rename files with simple, regex, or smart renaming modes.
*   **Video Processing:** Compress videos or add subtitles.
*   **Configuration:** A settings panel to customize the script's behavior.
*   **Dependency Check:** Checks for required dependencies and offers to install them.
*   **Dry Run Mode:** Preview changes before they are made.
*   **Backup:** Automatically back up directories before renaming files.

### How to Run:

1.  Make sure you have all the dependencies installed (the script will check for you).
2.  Run the script from your terminal:
    ```bash
    ./Ultimate_Script.sh
    ```
3.  A GUI menu will appear. Select the operation you want to perform.

### Script Structure:

The main script `Ultimate_Script.sh` is a launcher that sources its functionality from the modules located in the `scripts/` directory. This modular design makes the script easier to maintain and extend.

## 2. Python Media Tools

The `metadata&preview_maker/` directory contains a set of specialized Python tools for organizing adult media from different sources.

### Features:

*   **Metadata Scraping:** Scrapes metadata from various online sources.
*   **Cover & Screenshot Downloader:** Downloads cover images and screenshots.
*   **Video Preview & Sheet Generator:** Creates video previews, animated WebP files, and contact sheets.
*   **GUI Launcher:** A simple launcher to choose which processor to run.
*   **Configuration File:** All settings are managed in a central `config.ini` file.

### How to Run:

1.  **Install Dependencies:** The Python scripts require `requests`, `beautifulsoup4`, `loguru`, and `Pillow`. The scripts will attempt to install these for you if they are missing.
2.  **Configure:**
    *   Open the `metadata&preview_maker/config.ini` file.
    *   Set the `video_dir` to the directory where your video files are located.
    *   For the Western processor, you **must** replace `YOUR_API_TOKEN_HERE` with a valid API token from `theporndb.net`.
3.  **Launch the tool:**
    ```bash
    python3 metadata&preview_maker/run.py
    ```
4.  A GUI will appear. Choose which processor you want to run (Jav or Western).
5.  The selected processor will then launch its own GUI for further options.

### Tools:

*   **Jav Processor (`Jav+Preview.py`):** For processing Japanese Adult Videos (JAV). Scrapes metadata from `javdatabase.com`.
*   **Western Processor (`Western+preview.py`):** For processing Western adult videos. Scrapes metadata from `theporndb.net`.
