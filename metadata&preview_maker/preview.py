#!/usr/bin/env python3

import os
import string
import subprocess
import shutil
import random
import sys
import unicodedata
import re
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from time import sleep
from typing import List, Tuple, Optional, Dict, Any

# --- Dependency Check/Installation ---
try:
    from loguru import logger
except ImportError:
    print("Loguru not found, attempting to install...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "loguru"])
        from loguru import logger
        logger.success("Loguru installed successfully.")
    except Exception as e:
        print(f"Failed to install loguru: {e}. Please install it manually (`pip install loguru`).")
        sys.exit(1)

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    logger.warning("Pillow (PIL) not found, attempting to install...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow"])
        from PIL import Image, ImageDraw, ImageFont
        logger.success("Pillow installed successfully.")
    except Exception as e:
        logger.error(f"Failed to install Pillow: {e}. Please install it manually (`pip install Pillow`).")
        sys.exit(1)

# --- NEW IMPORT FOR GUI ---
import tkinter as tk
from tkinter import filedialog

# --- Configuration ---
class Config:
    INPUT_FOLDER = r"G:\temp6" # This will be overwritten by the GUI selection
    CUSTOM_OUTPUT_PATH: Optional[str] = None

    CREATE_WEBP_PREVIEW = True
    CREATE_WEBP_PREVIEW_SHEET = True
    CREATE_IMAGE_PREVIEW_SHEET = True

    CREATE_WEBM_PREVIEW = False
    CREATE_GIF_PREVIEW = False
    CREATE_WEBM_PREVIEW_SHEET = False
    CREATE_GIF_PREVIEW_SHEET = False

    NUM_OF_SEGMENTS = 16
    SEGMENT_DURATION = 1.5
    ADD_BLACK_BARS = False
    GRID_WIDTH = 4
    TIMESTAMPS_MODE = 2
    IMAGE_SHEET_FORMAT = "PNG"
    CALCULATE_MD5 = False

    KEEP_TEMP_FILES = False
    IGNORE_EXISTING = True
    PRINT_CUT_POINTS = False
    CONFIRM_CUT_POINTS_REQUIRED = False
    BLACKLISTED_CUT_POINTS = []
    EXCLUDED_FILES = [""]

    FONT_PATH = "/usr/share/fonts/liberation/LiberationSans-Regular.ttf" # Adjust if needed for your OS

    VALID_VIDEO_EXTENSIONS = (".mp4", ".mkv", ".m2ts", ".m4v", ".avi", ".ts", ".wmv", ".mov")

    @classmethod
    def validate(cls):
        """Validate configuration settings."""
        if cls.CREATE_WEBP_PREVIEW_SHEET:
            if cls.GRID_WIDTH not in [3, 4]:
                logger.error(f"Invalid GRID_WIDTH ({cls.GRID_WIDTH}). Must be 3 or 4 for WebP sheets.")
                return False
            min_segments = 9 if cls.GRID_WIDTH == 3 else 12
            max_segments = 30 if cls.GRID_WIDTH == 3 else 28
            if not (min_segments <= cls.NUM_OF_SEGMENTS <= max_segments and cls.NUM_OF_SEGMENTS % cls.GRID_WIDTH == 0):
                logger.error(f"NUM_OF_SEGMENTS ({cls.NUM_OF_SEGMENTS}) invalid for GRID_WIDTH {cls.GRID_WIDTH} for WebP sheets.")
                logger.error(f"For GRID_WIDTH=3, must be mult of 3 between 9-30.")
                logger.error(f"For GRID_WIDTH=4, must be mult of 4 between 12-28.")
                return False

        # Check font path more carefully
        font_path = Path(cls.FONT_PATH)
        if not font_path.is_file():
             # Try common alternatives if the default doesn't exist
             common_fonts = [
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", # Debian/Ubuntu
                 "/usr/share/fonts/TTF/DejaVuSans.ttf", # Fedora/CentOS
                 "C:/Windows/Fonts/Arial.ttf" # Windows
             ]
             found_alternative = False
             for alt_font in common_fonts:
                 if Path(alt_font).is_file():
                     logger.warning(f"Specified font '{cls.FONT_PATH}' not found. Using fallback: '{alt_font}'.")
                     cls.FONT_PATH = alt_font
                     found_alternative = True
                     break
             if not found_alternative:
                 logger.warning(f"Specified font '{cls.FONT_PATH}' not found, and no common alternatives found. Text overlay/info image might fail or use PIL default.")
        else:
            logger.debug(f"Using font: {cls.FONT_PATH}")


        input_path = Path(cls.INPUT_FOLDER)
        # Validate the *selected* path
        if not input_path.is_dir():
             logger.error(f"Selected input folder '{cls.INPUT_FOLDER}' does not exist or is not a directory.")
             return False # Make this an error now that user selected it

        if cls.CUSTOM_OUTPUT_PATH:
             output_path = Path(cls.CUSTOM_OUTPUT_PATH)
             output_path.mkdir(parents=True, exist_ok=True)
             cls.CUSTOM_OUTPUT_PATH = str(output_path)

        if cls.IMAGE_SHEET_FORMAT.upper() not in ["PNG", "JPG", "JPEG"]:
            logger.warning(f"Invalid IMAGE_SHEET_FORMAT '{cls.IMAGE_SHEET_FORMAT}'. Defaulting to PNG.")
            cls.IMAGE_SHEET_FORMAT = "PNG"

        logger.info("Configuration validated.")
        return True

# --- Utility Functions ---
def run_command(command: str, cwd: Optional[str] = None) -> Tuple[str, str, int]:
    """Execute a shell command and return stdout, stderr, and exit code."""
    try:
        # Use appropriate encoding, handle potential errors
        result = subprocess.run(command, shell=True, capture_output=True, text=True, encoding='utf-8', errors='surrogateescape', cwd=cwd)
        stdout = result.stdout.strip() if result.stdout else ''
        stderr = result.stderr.strip() if result.stderr else ''
        if result.returncode != 0:
            stderr_snippet = (stderr[:500] + '...') if len(stderr) > 500 else stderr
            logger.warning(f"Command failed (Exit Code {result.returncode}): {command}")
            if stderr: logger.warning(f"Stderr Snippet: {stderr_snippet}")
        return stdout, stderr, result.returncode
    except Exception as e:
        logger.error(f"Exception running command '{command}': {e}")
        return "", str(e), -1

def format_duration(seconds: float) -> str:
    """Convert seconds into HH:MM:SS format."""
    try:
        td = timedelta(seconds=int(round(seconds))) # Round to nearest second
        hours, remainder = divmod(td.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if td.days > 0:
            hours += td.days * 24
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    except Exception:
        return "00:00:00"

def sanitize_filename(filename: str) -> str:
    """Clean filename for filesystem compatibility."""
    try:
        # Handle potential non-string input
        if not isinstance(filename, str):
            filename = str(filename)

        # Normalize unicode characters
        normalized = unicodedata.normalize('NFKD', filename).encode('ascii', 'ignore').decode('ascii')

        # Remove or replace invalid characters
        # Allow alphanumeric, underscore, hyphen, period. Replace others with underscore.
        sanitized = re.sub(r'[^\w.\-]+', '_', normalized)

        # Remove leading/trailing underscores/periods and excessive consecutive underscores
        sanitized = re.sub(r'_+', '_', sanitized).strip('_.')

        # Ensure filename is not empty after sanitization
        return sanitized if sanitized else f"sanitized_{random.randint(1000, 9999)}"
    except Exception as e:
        logger.error(f"Filename sanitization failed for '{filename}': {e}")
        # Provide a safe fallback filename
        return f"sanitized_error_{random.randint(1000, 9999)}"

def get_md5_hash(file_path: Path) -> str:
    """Calculate MD5 hash of a file."""
    hash_md5 = hashlib.md5()
    try:
        with file_path.open("rb") as f:
            # Read in larger chunks for potentially better performance
            for chunk in iter(lambda: f.read(65536), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except FileNotFoundError:
        logger.error(f"File not found for MD5 calculation: {file_path}")
        return "N/A (File Not Found)"
    except Exception as e:
        logger.error(f"Error computing MD5 hash for {file_path.name}: {e}")
        return "N/A (Error)"

# --- Core Processing Class ---
class VideoProcessor:
    def __init__(self, video_path: Path, config: Config):
        self.original_video_path = video_path # Store the initial path
        self.video_path = video_path        # This might be updated after moving
        self.config = config
        self.base_filename = sanitize_filename(video_path.stem)
        if self.config.ADD_BLACK_BARS:
             self.base_filename += "_black_bars"

        # Determine the base output directory (either custom or the input folder)
        base_output_dir = Path(config.CUSTOM_OUTPUT_PATH or config.INPUT_FOLDER)
        # The specific output directory for *this* video's results
        self.output_dir = base_output_dir / self.base_filename
        # The temporary directory within the specific output directory
        self.temp_dir = self.output_dir / f"{self.base_filename}-temp"

        self.metadata: Dict[str, Any] = {}
        self.cut_points_sec: List[float] = []
        self.segment_files: List[Path] = []
        self.timestamped_segment_files: List[Path] = []
        self.segment_frame_files: List[Path] = []
        self.is_vertical = False

    def _check_existing_outputs(self) -> bool:
        """
        Check for existing output files based on current config.
        Also checks if the original video is already in the target output dir.
        """
        logger.debug(f"Checking existing outputs in: {self.output_dir}")
        img_sheet_suffix = f".{self.config.IMAGE_SHEET_FORMAT.lower()}"
        # Define expected output files based on configuration
        output_files_config = {
            "WebP Preview": (self.output_dir / f"{self.base_filename}_preview.webp", self.config.CREATE_WEBP_PREVIEW),
            "WebP Sheet": (self.output_dir / f"{self.base_filename}_preview_sheet.webp", self.config.CREATE_WEBP_PREVIEW_SHEET),
            "Image Sheet": (self.output_dir / f"{self.base_filename}_preview_sheet{img_sheet_suffix}", self.config.CREATE_IMAGE_PREVIEW_SHEET),
            # Check for the *original* video file name within the target output directory
            "Original Video (Moved)": (self.output_dir / self.original_video_path.name, True) # Original video should always end up here if processing runs
        }

        required_files_exist = []
        required_files_missing = []
        files_to_potentially_delete = [] # Track generated previews/sheets for potential deletion

        original_video_in_target = False

        for name, (file_path, create_flag) in output_files_config.items():
            is_original_video_check = (name == "Original Video (Moved)")

            if file_path.exists():
                if is_original_video_check:
                    original_video_in_target = True
                    # If original video is found in target, update self.video_path now
                    self.video_path = file_path
                    logger.debug(f"  Found existing original video in target: {file_path.name}")
                # Only consider generated files for 'required existing' check if create_flag is True
                elif create_flag:
                    logger.debug(f"  Found existing generated file: {file_path.name}")
                    required_files_exist.append(name)
                    files_to_potentially_delete.append((name, file_path))
            else:
                # Note missing generated files if create_flag is True
                if create_flag and not is_original_video_check:
                    logger.debug(f"  Missing required generated file: {file_path.name}")
                    required_files_missing.append(name)
                elif is_original_video_check:
                    logger.debug(f"  Original video not found in target directory: {file_path.name}")
                    # If original is missing from target, ensure self.video_path points to original location
                    if self.video_path != self.original_video_path:
                        logger.debug(f"  Resetting video_path to original: {self.original_video_path}")
                        self.video_path = self.original_video_path


        # --- Decide whether to process ---
        all_required_generated_exist = not required_files_missing

        # Scenario 1: All generated outputs exist AND original video is in target dir
        if all_required_generated_exist and original_video_in_target and not self.config.IGNORE_EXISTING:
            logger.info(f"All required outputs and original video exist for '{self.base_filename}' in '{self.output_dir}'. IGNORE_EXISTING is False. Skipping.")
            return False # Skip processing

        # Scenario 2: IGNORE_EXISTING is True - always proceed, but delete existing generated files first
        if self.config.IGNORE_EXISTING:
            if files_to_potentially_delete:
                 logger.info(f"IGNORE_EXISTING is True. Deleting existing generated output files for '{self.base_filename}'...")
                 for name, file_path in files_to_potentially_delete:
                     logger.info(f"  Deleting: {file_path.name}")
                     try: file_path.unlink()
                     except OSError as e: logger.error(f"  Failed to delete {file_path.name}: {e}") # Log error but continue
                     sleep(0.05)
            logger.debug("IGNORE_EXISTING is True. Proceeding with generation.")
            return True # Proceed with processing

        # Scenario 3: Some generated files missing OR original video not in target (and IGNORE_EXISTING is False)
        if not all_required_generated_exist or not original_video_in_target:
            # If some generated files exist but others are missing (and IGNORE_EXISTING is False), prompt user
            if files_to_potentially_delete:
                logger.warning(f"Some generated outputs missing, but others exist for '{self.base_filename}'.")
                for name, file_path in files_to_potentially_delete:
                    try:
                        choice = input(f"  Existing '{name}' found: '{file_path.name}'. Delete before regenerating? (yes/no): ").strip().lower()
                    except EOFError:
                        logger.warning("  Cannot prompt for input (EOFError). Skipping regeneration for safety.")
                        return False # Skip processing if prompt fails
                    if choice in ["yes", "y"]:
                        logger.info(f"  Deleting: {file_path.name}")
                        try: file_path.unlink()
                        except OSError as e: logger.error(f"  Failed to delete {file_path.name}: {e}"); return False # Fail if deletion fails
                    else:
                        logger.warning(f"  User chose not to delete '{file_path.name}'. Skipping regeneration for '{self.base_filename}'.")
                        return False # Skip processing if user refuses deletion
                    sleep(0.05)
            # If we reach here, either no existing generated files needed deletion, or user approved deletion.
            logger.debug("Proceeding with generation (files missing or original not moved yet, and IGNORE_EXISTING is False).")
            return True # Proceed with processing

        # Should not be reached, but default to skip for safety
        logger.warning("Unexpected state in _check_existing_outputs. Skipping generation.")
        return False

    def run(self):
        """Main processing workflow for the video."""
        # Check existing outputs and decide if processing is needed.
        # This also updates self.video_path if the original video is already in the target.
        should_process = self._check_existing_outputs()

        if not should_process:
            return False # Skip this file

        # --- Ensure Output Directory Exists ---
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Ensured output directory exists: {self.output_dir}")
        except Exception as mkdir_e:
            logger.error(f"Failed to create output directory '{self.output_dir}': {mkdir_e}. Skipping this file.")
            return False

        logger.info(f"--- Processing: {self.original_video_path.name} ---") # Use original name for initial logging
        logger.info(f"Target output directory: {self.output_dir}")
        sleep(0.2)

        # --- MOVE ORIGINAL VIDEO FILE (if not already there) ---
        target_video_path = self.output_dir / self.original_video_path.name
        if self.video_path.resolve() != target_video_path.resolve():
            logger.info(f"Moving video file to output directory: {target_video_path}")
            try:
                shutil.move(str(self.video_path), str(target_video_path))
                self.video_path = target_video_path # IMPORTANT: Update the path attribute used by subsequent steps
                logger.success("Video file moved successfully.")
            except Exception as move_e:
                 logger.error(f"Failed to move video file '{self.original_video_path.name}' from '{self.video_path}' to '{target_video_path}': {move_e}.")
                 logger.error("Skipping processing for this file due to move failure.")
                 # Attempt to move back if the target exists and isn't the original? Unlikely edge case, maybe too complex.
                 # For now, just fail processing for this file.
                 return False # Stop processing this file
        else:
            logger.debug("Video file is already in the target output directory.")

        # --- Create Temp Directory ---
        # Do this *after* moving the video, within the final output directory
        try:
             self.temp_dir.mkdir(parents=True, exist_ok=True)
             logger.debug(f"Ensured temporary directory exists: {self.temp_dir}")
        except Exception as e:
             logger.error(f"Failed to create temporary directory {self.temp_dir}: {e}. Aborting processing for this file.")
             return False


        # --- Proceed with Processing using the (potentially updated) self.video_path ---
        if not self._get_metadata():
            logger.error(f"Failed to get metadata for {self.video_path.name}. Aborting processing.")
            # No need to move file back, as failure happened after move attempt
            return False

        video_duration = self.metadata.get("duration", 0)
        if video_duration <= 10:
            logger.error(f"Video duration ({video_duration:.1f}s) is too short (< 10s). Aborting processing.")
            return False

        processing_successful = False
        try:
            # Create output subdirectories inside the main try block
            # (Already created output_dir and temp_dir)

            cut_points_pct = self._generate_cut_points()
            if not cut_points_pct: return False # Abort if cut points fail

            self.cut_points_sec = [p * video_duration for p in cut_points_pct]

            # Generate segments using the potentially moved video file
            self.segment_files, self.timestamped_segment_files = self._generate_segments()
            # Check if segment generation failed (returned empty lists)
            if not self.segment_files and (self.config.CREATE_WEBP_PREVIEW or self.config.CREATE_WEBP_PREVIEW_SHEET or self.config.CREATE_IMAGE_PREVIEW_SHEET):
                logger.error("No valid segments generated. Aborting preview generation.")
                # Temp folder cleanup is handled in finally
                return False

            # Generate requested outputs
            results = []
            if self.config.CREATE_WEBP_PREVIEW:
                results.append(self._generate_webp_preview())

            if self.config.CREATE_WEBP_PREVIEW_SHEET:
                results.append(self._generate_webp_preview_sheet())

            if self.config.CREATE_IMAGE_PREVIEW_SHEET:
                 self.segment_frame_files = self._extract_segment_frames()
                 if self.segment_frame_files:
                      results.append(self._generate_image_preview_sheet())
                 else:
                      logger.error("Failed to extract frames for image sheet generation.")
                      results.append(False)

            # Determine overall success based on whether *any* requested output was generated
            processing_successful = any(r is True for r in results)

            if processing_successful:
                 logger.success(f"Successfully finished processing and generated outputs for: {self.video_path.name}")
            else:
                 # Check if any previews were requested at all
                 any_preview_requested = (self.config.CREATE_WEBP_PREVIEW or
                                          self.config.CREATE_WEBP_PREVIEW_SHEET or
                                          self.config.CREATE_IMAGE_PREVIEW_SHEET)
                 if any_preview_requested:
                     logger.error(f"Processing attempted, but failed to generate any requested outputs for {self.video_path.name}.")
                 else:
                     logger.info(f"No preview outputs were configured for {self.video_path.name}. Processing finished (only moved file).")
                     processing_successful = True # Consider it success if only move was needed and it worked


        except Exception as e:
            logger.exception(f"An unexpected error occurred during processing {self.video_path.name}: {e}")
            processing_successful = False # Ensure failure state on exception
        finally:
            # --- Cleanup ---
            if not self.config.KEEP_TEMP_FILES and self.temp_dir.exists():
                 logger.info(f"Removing temporary folder: {self.temp_dir}")
                 shutil.rmtree(self.temp_dir, ignore_errors=True) # Use ignore_errors for robustness
            sleep(0.1) # Small delay before next file

        return processing_successful


    def _get_metadata(self) -> bool:
        """Extract metadata using ffprobe from self.video_path."""
        # Ensure the video path exists before probing
        if not self.video_path.is_file():
            logger.error(f"Video file not found at expected location for metadata: {self.video_path}")
            return False
        try:
            # Check for rotation metadata
            cmd_rot = f'ffprobe -v error -select_streams v:0 -show_entries stream_tags=rotate -of default=nw=1:nk=1 "{self.video_path}"'
            stdout_rot, _, exit_code_rot = run_command(cmd_rot)
            if exit_code_rot == 0 and stdout_rot and stdout_rot.strip() not in ["0", ""]:
                logger.error(f"Video '{self.video_path.name}' has rotation metadata ({stdout_rot.strip()} degrees). Please fix before processing. Skipping.")
                return False

            # Get format and stream info
            cmd = f'ffprobe -v error -print_format json -show_format -show_streams "{self.video_path}"'
            stdout, stderr, exit_code = run_command(cmd)
            if exit_code != 0:
                logger.error(f"ffprobe failed for {self.video_path.name}. Exit Code: {exit_code}. Stderr: {stderr}")
                return False

            data = json.loads(stdout)
            video_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
            audio_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)
            format_info = data.get("format", {})

            if not video_stream:
                logger.error(f"No video stream found for {self.video_path.name}")
                return False

            # Populate metadata dictionary
            self.metadata["filename"] = self.video_path.name # Use the current name (potentially after move)
            self.metadata["title"] = format_info.get("tags", {}).get("title", "N/A")
            try: self.metadata["duration"] = float(format_info.get("duration", 0))
            except (ValueError, TypeError): logger.warning("Could not parse video duration."); self.metadata["duration"] = 0
            try: self.metadata["size_bytes"] = int(format_info.get("size", 0))
            except (ValueError, TypeError): logger.warning("Could not parse video size."); self.metadata["size_bytes"] = 0
            self.metadata["size_mb"] = f"{self.metadata['size_bytes'] / (1024*1024):.2f} MB" if self.metadata['size_bytes'] else "N/A"

            width = video_stream.get("width"); height = video_stream.get("height")
            if not width or not height:
                logger.error(f"Could not get resolution for {self.video_path.name}")
                return False
            self.metadata["width"] = width; self.metadata["height"] = height
            self.is_vertical = width < height
            self.metadata["resolution"] = f"{width}x{height}"

            self.metadata["video_codec"] = video_stream.get("codec_name", "N/A").upper()
            self.metadata["video_profile"] = video_stream.get("profile", "N/A")
            video_bitrate_str = video_stream.get("bit_rate")
            self.metadata["video_bitrate_kbps"] = round(int(video_bitrate_str) / 1000) if video_bitrate_str and video_bitrate_str.isdigit() else 0

            fps_str = video_stream.get("r_frame_rate", "0/1")
            try:
                num, den = map(int, fps_str.split('/'))
                self.metadata["fps"] = round(num / den, 2) if den else 0
            except ValueError: self.metadata["fps"] = 0
            self.metadata["video_details"] = (f"{self.metadata['video_codec']} ({self.metadata['video_profile']}) @ "
                                             f"{self.metadata['video_bitrate_kbps']} kbps, {self.metadata['fps']} fps")

            if audio_stream:
                self.metadata["audio_codec"] = audio_stream.get("codec_name", "N/A").upper()
                self.metadata["audio_profile"] = audio_stream.get("profile", "N/A")
                self.metadata["audio_channels"] = audio_stream.get("channels", "N/A")
                audio_bitrate_str = audio_stream.get("bit_rate")
                self.metadata["audio_bitrate_kbps"] = round(int(audio_bitrate_str) / 1000) if audio_bitrate_str and audio_bitrate_str.isdigit() else 0
                self.metadata["audio_details"] = (f"{self.metadata['audio_codec']} ({self.metadata['audio_profile']}, "
                                                 f"{self.metadata['audio_channels']}ch) @ {self.metadata['audio_bitrate_kbps']} kbps")
            else:
                self.metadata["audio_details"] = "No Audio Stream"

            # Calculate MD5 of the file at its *current* location (self.video_path)
            if self.config.CALCULATE_MD5:
                 self.metadata["md5"] = get_md5_hash(self.video_path)
            else:
                 self.metadata["md5"] = "N/A (Disabled)"

            # Check for specific unsupported codecs
            if self.metadata["video_codec"] == "MSMPEG4V3":
                 logger.error(f"Video '{self.video_path.name}' uses unsupported codec MSMPEG4V3. Skipping.")
                 return False

            logger.info("Metadata extracted successfully.")
            return True
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse ffprobe JSON output for {self.video_path.name}: {e}")
            return False
        except Exception as e:
            logger.exception(f"Unexpected error getting metadata for {self.video_path.name}: {e}")
            return False

    def _generate_cut_points(self) -> List[float]:
        """Generate evenly spaced cut points as percentages."""
        # Ensure duration is available
        if not self.metadata.get("duration", 0) > 0:
            logger.error("Video duration unknown or zero, cannot generate cut points.")
            return []

        start_pct = 0.05; end_pct = 0.98
        num_points = self.config.NUM_OF_SEGMENTS
        valid_points = []
        retries = 2 # Number of attempts to adjust range if points are blacklisted

        while len(valid_points) < num_points and retries > 0:
            points = set() # Use a set to automatically handle duplicates
            # Add start/end points if not blacklisted
            if start_pct not in self.config.BLACKLISTED_CUT_POINTS: points.add(round(start_pct, 3))
            if end_pct not in self.config.BLACKLISTED_CUT_POINTS: points.add(round(end_pct, 3))

            # Check if start/end points are usable
            if len(points) < 2 and num_points >= 2:
                 logger.warning(f"Start/End points ({start_pct:.3f}/{end_pct:.3f}) blacklisted or identical, adjusting range...")
                 start_pct += 0.01; end_pct -= 0.01
                 if start_pct >= end_pct:
                     logger.error("Cannot generate cut points, range collapsed after adjusting for blacklist.")
                     return []
                 retries -=1; continue # Retry with adjusted range

            current_start = min(points); current_end = max(points)
            num_inner_points = num_points - len(points) # Number of points needed between start and end

            if num_inner_points > 0:
                 if current_end == current_start: # Should not happen if len(points) >= 2 check passed
                      logger.error("Cannot generate inner points, start and end points are identical after blacklisting.")
                      return []
                 # Calculate step for inner points
                 step = (current_end - current_start) / (num_inner_points + 1)
                 for i in range(1, num_inner_points + 1):
                     point = round(current_start + step * i, 3)
                     # Ensure point is strictly within the bounds to avoid duplicates with start/end
                     point = max(current_start + 0.001, min(current_end - 0.001, point))
                     if point not in self.config.BLACKLISTED_CUT_POINTS:
                         points.add(point)

            # Check if enough unique, non-blacklisted points were generated
            if len(points) < num_points:
                logger.warning(f"Could only generate {len(points)}/{num_points} unique non-blacklisted points. Retrying with adjusted range.")
                start_pct += 0.005; end_pct -= 0.005 # Slightly adjust range for retry
                if start_pct >= end_pct:
                    logger.error("Cannot generate required cut points, range collapsed after retries.")
                    return []
                retries -= 1; continue # Retry

            # If enough points generated, sort and break the loop
            valid_points = sorted(list(points))
            break

        # Final check if required number of points was generated
        if len(valid_points) < num_points:
             logger.error(f"Failed to generate the required {num_points} unique cut points after retries.")
             return []

        # Log or confirm points if configured
        if self.config.PRINT_CUT_POINTS or self.config.CONFIRM_CUT_POINTS_REQUIRED:
            logger.info("Generated cut points (percentage and time):")
            for i, pct in enumerate(valid_points):
                time_sec = pct * self.metadata["duration"]
                logger.info(f"  Segment {i+1}: {pct:.3f} ({format_duration(time_sec)})")

        # Require user confirmation if configured
        if self.config.CONFIRM_CUT_POINTS_REQUIRED:
            sleep(0.5) # Allow time for user to read points
            try:
                confirmation = input("Use these cut points? (yes/no): ").strip().lower()
            except EOFError: # Handle running in non-interactive environment
                logger.warning("Cannot prompt for input (EOFError). Assuming NO.")
                confirmation = "no"
            if confirmation not in ["yes", "y"]:
                logger.info("Cut points rejected by user. Aborting processing for this file.")
                return [] # Return empty list to abort

        return valid_points

    def _get_vf_filter(self) -> str:
        """Determine the FFmpeg -vf filter string based on config."""
        target_w, target_h = 480, 270 # Standard 16:9 landscape segment size
        if self.is_vertical:
            if self.config.ADD_BLACK_BARS:
                # Scale down vertically, then pad horizontally to target WxH
                return f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2:color=black"
            else:
                # Scale vertically to target HxW (swapped for vertical)
                return f"scale={target_h}:{target_w}"
        else:
            # Scale landscape to target WxH
            return f"scale={target_w}:{target_h}"

    def _verify_segment(self, segment_path: Path) -> bool:
        """Uses ffprobe to quickly check if a segment file is valid and has duration."""
        if not segment_path.exists() or segment_path.stat().st_size < 1024: # Basic sanity check
            logger.warning(f"Segment file is missing or too small: {segment_path.name}")
            return False

        # Probe for duration
        cmd_verify = (f'ffprobe -v error -select_streams v:0 -show_entries format=duration '
                      f'-of default=noprint_wrappers=1:nokey=1 "{segment_path}"')
        stdout, stderr, exit_code = run_command(cmd_verify)

        if exit_code != 0:
            logger.error(f"ffprobe verification failed for {segment_path.name}. Exit Code: {exit_code}, Stderr: {stderr}")
            return False
        if not stdout or not stdout.strip():
            logger.error(f"ffprobe could not determine duration for {segment_path.name}. Likely invalid.")
            return False
        try:
            duration = float(stdout.strip())
            # Check for non-positive duration, allowing for very small positive values
            if duration <= 0.01:
                logger.error(f"ffprobe reported non-positive or near-zero duration ({duration}s) for {segment_path.name}.")
                return False
        except ValueError:
            logger.error(f"ffprobe returned non-numeric duration '{stdout.strip()}' for {segment_path.name}.")
            return False

        logger.debug(f"Segment verified successfully: {segment_path.name} (Duration: {duration:.2f}s)")
        return True

    def _generate_segments(self) -> Tuple[List[Path], List[Path]]:
        """Generate video segments using ffmpeg from self.video_path and verify them."""
        valid_segment_paths = []
        timestamped_paths_for_sheet = [] # Paths potentially with timestamp overlay
        vf_filter = self._get_vf_filter()
        total_segments_requested = len(self.cut_points_sec)
        segments_generated = 0
        max_duration = self.metadata.get("duration", 0)

        # Ensure video path exists before starting loop
        if not self.video_path.is_file():
            logger.error(f"Input video file not found at {self.video_path}. Cannot generate segments.")
            return [], []


        for i, start_sec in enumerate(self.cut_points_sec):
            segment_index = i + 1
            logger.debug(f"Processing segment {segment_index}/{total_segments_requested} starting at {start_sec:.3f}s")

            # Ensure start time is within video duration
            if start_sec >= max_duration:
                logger.warning(f"Cut point {start_sec:.3f}s is at or beyond video duration ({max_duration:.3f}s). Skipping segment {segment_index}.")
                continue

            # Calculate duration, ensuring it doesn't exceed remaining video length
            cut_duration = min(self.config.SEGMENT_DURATION, max_duration - start_sec)
            # Ensure duration is positive and meaningful
            if cut_duration <= 0.01:
                logger.warning(f"Calculated segment duration ({cut_duration:.3f}s) is too small for segment {segment_index} starting at {start_sec:.3f}s. Skipping.")
                continue

            # Format start time for ffmpeg -ss and filename
            start_time_td = timedelta(seconds=start_sec)
            # Use precise start time for -ss
            start_time_ss = f"{int(start_time_td.total_seconds() // 3600):02d}:{int(start_time_td.seconds // 60 % 60):02d}:{int(start_time_td.seconds % 60):02d}.{start_time_td.microseconds:06d}"
            # Use rounded duration for filename
            start_time_fn = format_duration(start_sec).replace(":",".")

            # Define segment output path in the temp directory
            segment_filename = f"{self.base_filename}_start-{start_time_fn}_seg-{segment_index:02d}.mp4" # Added padding
            segment_path = self.temp_dir / segment_filename

            # Construct ffmpeg command for segment extraction
            # Use -ss before -i for faster seeking (but potentially less accurate start frame)
            # Add -copyts to try and preserve timestamps if needed, but might cause issues; test carefully. Remove if problematic.
            # Use -map 0:v:0 explicitly selects the first video stream.
            ffmpeg_cmd = (
                f'ffmpeg -hide_banner -loglevel error '
                f'-ss {start_time_ss} -i "{self.video_path}" -t {cut_duration:.3f} ' # -t specifies duration to cut
                f'-vf "{vf_filter}" ' # Apply scaling/padding filter
                f'-map 0:v:0 ' # Select video stream
                f'-c:v libx264 -crf 23 -preset medium ' # Video codec options
                f'-an -sn -dn ' # No audio, subs, data
                f'-map_metadata -1 -map_chapters -1 ' # Drop metadata/chapters
                f'-y "{segment_path}"' # Overwrite output
            )
            logger.debug(f"Segment command: {ffmpeg_cmd}")
            _, stderr, exit_code = run_command(ffmpeg_cmd)

            # Verify the generated segment
            if exit_code == 0 and self._verify_segment(segment_path):
                logger.debug(f"Generated and verified segment {segment_index}: {segment_path.name}")
                segments_generated += 1

                # Determine which path to use for previews/sheets based on timestamp mode
                final_segment_path_for_preview = segment_path # Used for standalone preview if mode 0 or 2
                path_for_sheet = segment_path # Used for sheet if mode 0

                # Apply timestamp overlay if required
                if self.config.TIMESTAMPS_MODE in [1, 2]:
                    overlay_path = self._overlay_timestamp(segment_path, start_sec)
                    if overlay_path:
                        if self.config.TIMESTAMPS_MODE == 1:
                            final_segment_path_for_preview = overlay_path # Use timestamped for standalone preview
                            path_for_sheet = overlay_path # Use timestamped for sheet
                        else: # TIMESTAMPS_MODE == 2
                            # Standalone preview uses original (final_segment_path_for_preview = segment_path)
                            path_for_sheet = overlay_path # Sheet uses timestamped
                    else:
                        logger.warning(f"Failed timestamp overlay for segment {segment_index}. Using original segment for previews/sheets.")
                        # Fallback: use original path if overlay failed
                        path_for_sheet = segment_path
                        # final_segment_path_for_preview remains segment_path

                valid_segment_paths.append(final_segment_path_for_preview)
                timestamped_paths_for_sheet.append(path_for_sheet) # Collect paths specifically for sheets

            else:
                logger.error(f"Failed to generate or verify segment {segment_index} (Start: {start_sec:.3f}s). ExitCode: {exit_code}.")
                if stderr: logger.error(f"  FFmpeg stderr: {stderr}")
                # Attempt cleanup of failed segment file
                segment_path.unlink(missing_ok=True)
                ts_path = segment_path.with_name(f"ts_{segment_path.name}")
                ts_path.unlink(missing_ok=True)

        logger.info(f"Finished segment generation. Successfully generated {segments_generated}/{total_segments_requested} segments.")
        # If no segments were successfully generated but some were requested, it's a failure state
        if segments_generated == 0 and total_segments_requested > 0:
             logger.error("Segment generation process completed, but resulted in zero valid segments.")
             return [], [] # Return empty lists explicitly

        return valid_segment_paths, timestamped_paths_for_sheet

    def _overlay_timestamp(self, segment_path: Path, start_sec: float) -> Optional[Path]:
        """Overlays HH:MM:SS timestamp onto a segment."""
        timestamp_text = format_duration(start_sec).replace(":", r"\:") # Escape colons for drawtext
        output_path = segment_path.with_name(f"ts_{segment_path.stem}{segment_path.suffix}") # ts_basename.mp4

        font_path_cfg = self.config.FONT_PATH
        font_path_obj = Path(font_path_cfg)

        # Prepare font path for ffmpeg filtergraph, handling OS differences and escaping
        try:
            if not font_path_obj.is_file():
                logger.error(f"Timestamp overlay font not found at configured path: {font_path_cfg}.")
                return None

            font_path_resolved = str(font_path_obj.resolve())
            if sys.platform == "win32":
                # Windows: Escape backslashes and colons for ffmpeg's filtergraph parser
                font_path_ffmpeg_val = font_path_resolved.replace("\\", "/").replace(":", "\\\\:")
            else:
                # Linux/Mac: Escape single quotes
                font_path_ffmpeg_val = font_path_resolved.replace("'", "'\\''") # replace ' with '\''
            font_path_ffmpeg_filter = f"fontfile='{font_path_ffmpeg_val}':"
            logger.debug(f"Using font filter string: {font_path_ffmpeg_filter}")
        except Exception as e:
             logger.error(f"Error preparing font path '{font_path_cfg}' for ffmpeg: {e}. Cannot overlay timestamp.")
             return None

        # Construct the ffmpeg command with drawtext filter
        ffmpeg_cmd = (
            f'ffmpeg -hide_banner -loglevel error -i "{segment_path}" '
            f'-vf "drawtext=text=\'{timestamp_text}\':{font_path_ffmpeg_filter}' # Include prepared font path filter
            f'fontcolor=white:fontsize=20:x=(w-text_w)-10:y=10:box=1:boxcolor=black@0.4:boxborderw=5" '
            f'-c:v libx264 -crf 23 -preset medium -an -y "{output_path}"' # Encode the output
        )
        logger.debug(f"Timestamp overlay command: {ffmpeg_cmd}")
        _, stderr, exit_code = run_command(ffmpeg_cmd)

        if exit_code == 0 and output_path.exists():
            logger.debug(f"Timestamp overlay successful: {output_path.name}")
            return output_path
        else:
            logger.error(f"Failed timestamp overlay on {segment_path.name}. ExitCode: {exit_code}")
            if stderr: logger.error(f"  FFmpeg stderr: {stderr}")
            output_path.unlink(missing_ok=True) # Clean up failed output
            return None

    def _write_concat_file(self, segment_paths: List[Path], output_filename: str) -> Optional[Path]:
        """Writes a concat list file needed by ffmpeg's concat demuxer."""
        if not segment_paths:
            logger.error("No segment paths provided to write concat file.")
            return None

        concat_path = self.temp_dir / output_filename
        try:
            with concat_path.open("w", encoding='utf-8') as f:
                for path in segment_paths:
                    # Ensure the path is absolute and uses POSIX separators for ffmpeg
                    safe_path = path.resolve().as_posix()
                    # Escape single quotes within the path itself for safety
                    safe_path_escaped = safe_path.replace("'", "'\\''") # replace ' with '\''
                    f.write(f"file '{safe_path_escaped}'\n")
            logger.debug(f"Concat file written: {concat_path}")
            return concat_path
        except Exception as e:
            logger.error(f"Failed to write concat file '{concat_path}': {e}")
            return None

    def _run_ffmpeg_concat(self, concat_file_path: Path, output_video_path: Path) -> bool:
        """Runs ffmpeg -f concat demuxer to join segments without re-encoding."""
        if not concat_file_path or not concat_file_path.exists():
            logger.error(f"Concat file not found or not specified: {concat_file_path}")
            return False

        # Command to concatenate using the list file
        # -safe 0 allows using absolute paths in the concat file
        # -c copy stream copies without re-encoding (fast, preserves quality)
        concat_cmd = (f'ffmpeg -hide_banner -loglevel error -f concat -safe 0 '
                      f'-i "{concat_file_path}" -c copy -y "{output_video_path}"')

        logger.debug(f"Running concat command: {concat_cmd}")
        _, stderr, exit_code = run_command(concat_cmd)

        if exit_code != 0 or not output_video_path.exists() or output_video_path.stat().st_size == 0:
            logger.error(f"Concatenation failed for '{concat_file_path.name}'. Exit Code: {exit_code}")
            if stderr: logger.error(f"  FFmpeg stderr: {stderr}")
            output_video_path.unlink(missing_ok=True) # Clean up failed output
            return False

        logger.debug(f"Concatenation successful: {output_video_path.name}")
        return True

    def _generate_webp_preview(self) -> bool:
        """Generates the standalone animated WebP preview."""
        logger.info("Generating standalone animated WebP preview...")
        # Use segments intended for preview (may or may not have timestamps based on mode)
        segments_for_preview = self.segment_files
        if not segments_for_preview:
            logger.error("No valid segments available for WebP preview.")
            return False

        # Create the concat list file
        concat_file = self._write_concat_file(segments_for_preview, "concat_list_webp_preview.txt")
        if not concat_file: return False # Fail if concat file writing fails

        # Define the intermediate concatenated video path
        concat_video = self.temp_dir / f"{self.base_filename}_concat_webp_preview.mp4"

        # Run ffmpeg concat
        if not self._run_ffmpeg_concat(concat_file, concat_video):
            logger.error("Failed to concatenate segments for WebP preview.")
            return False # Fail if concatenation fails

        # Define the final output WebP path
        output_webp = self.output_dir / f"{self.base_filename}_preview.webp"
        # Determine scaling based on aspect ratio
        scale_filter = "scale=480:-2" if not self.is_vertical or self.config.ADD_BLACK_BARS else "scale=-2:480"

        # Construct the ffmpeg command to convert concatenated video to WebP
        webp_cmd = (f'ffmpeg -hide_banner -loglevel error -y '
                    f'-i "{concat_video}" ' # Input concatenated video
                    f'-vf "fps=24,{scale_filter}:flags=lanczos" ' # Set FPS, scale, use Lanczos filter
                    f'-c:v libwebp -quality 80 -compression_level 6 ' # WebP codec options
                    f'-loop 0 ' # Loop infinitely
                    f'-an ' # No audio
                    f'-vsync 0 ' # Video sync method
                    f'"{output_webp}"')

        logger.debug(f"WebP generation command: {webp_cmd}")
        _, stderr, code = run_command(webp_cmd)

        if code == 0 and output_webp.exists() and output_webp.stat().st_size > 0:
            logger.success(f"Standalone WebP preview created: {output_webp.name}")
            return True
        else:
            logger.error(f"Failed to generate standalone WebP preview. Exit Code: {code}")
            if stderr: logger.error(f"  FFmpeg stderr: {stderr}")
            output_webp.unlink(missing_ok=True) # Clean up failed output
            return False

    def _create_info_image(self) -> Optional[Path]:
        """Creates the metadata image for the sheet header."""
        logger.debug("Creating info image header...")

        # Image and Font settings
        font_size = 16
        line_padding = 5
        side_margin = 20
        key_value_gap = 15
        key_column_width = 110 # Width allocated for "Key:" text

        # Determine image width based on grid configuration and orientation
        # This should match the width of a row of video segments
        if self.config.GRID_WIDTH == 3:
            # 3 segments wide. If vertical segments (270px wide each), width is 3*270=810.
            # If landscape segments (480px wide each), width is 3*480=1440.
            img_width = 810 if self.is_vertical and not self.config.ADD_BLACK_BARS else 1440
        elif self.config.GRID_WIDTH == 4:
            # 4 segments wide. Vertical: 4*270=1080. Landscape: 4*480=1920.
            img_width = 1080 if self.is_vertical and not self.config.ADD_BLACK_BARS else 1920
        else:
            logger.error(f"Unsupported GRID_WIDTH ({self.config.GRID_WIDTH}) for info image generation.")
            return None

        # Load font
        try:
            font = ImageFont.truetype(self.config.FONT_PATH, font_size)
        except IOError:
            logger.warning(f"Font '{self.config.FONT_PATH}' not found or failed to load. Using PIL default.")
            try: font = ImageFont.load_default(size=font_size) # Newer Pillow might need size
            except TypeError: font = ImageFont.load_default() # Older PIL/Pillow or fallback
        except Exception as font_e:
             logger.error(f"Error loading font: {font_e}. Using default.")
             try: font = ImageFont.load_default()
             except Exception: logger.error("Failed to load even default PIL font."); return None # Cannot proceed without a font

        # Calculate available width for the value text (considering margins and gaps)
        value_column_width = img_width - key_column_width - key_value_gap - (2 * side_margin)
        if value_column_width <= 0:
            logger.error("Calculated value column width is zero or negative. Check image width and margins.")
            return None

        # Get text metrics (height, width calculation function) using the loaded font
        try:
             # Use getbbox for more accurate sizing if available (Pillow >= 8.0.0)
             # Draw a sample character to get height properties
             test_char_bbox = font.getbbox("Xy")
             single_line_height = test_char_bbox[3] - test_char_bbox[1] + line_padding # Height + padding
             get_text_width = lambda text: font.getlength(text) if hasattr(font, 'getlength') else font.getbbox(text)[2] - font.getbbox(text)[0] if text else 0

        except AttributeError:
             # Fallback for older PIL/Pillow using getsize
             logger.debug("Using legacy font.getsize() method for text metrics.")
             size_sample = font.getsize("Xy")
             single_line_height = size_sample[1] + line_padding
             get_text_width = lambda text: font.getsize(text)[0] if text else 0
        except Exception as metrics_e:
            logger.error(f"Could not determine text metrics with loaded font: {metrics_e}")
            return None

        # --- Prepare metadata text and calculate required height ---
        prepared_lines = [] # List of tuples: (key_text, [list_of_value_lines])
        total_text_height = 0 # Accumulate height of all text lines

        # Define the metadata rows to display
        metadata_rows = [
            ("File", self.metadata.get("filename", "N/A")),
            ("Title", self.metadata.get("title", "N/A")),
            ("Size", self.metadata.get("size_mb", "N/A")),
            ("Resolution", self.metadata.get("resolution", "N/A")),
            ("Duration", format_duration(self.metadata.get("duration",0))),
            ("Video", self.metadata.get("video_details", "N/A")),
            ("Audio", self.metadata.get("audio_details", "N/A")),
            ("MD5", self.metadata.get("md5", "N/A")),
        ]

        # Process each metadata row for wrapping
        for key, value in metadata_rows:
            if not isinstance(value, str): value = str(value) # Ensure value is a string

            wrapped_value_lines = []
            current_line = ""
            # Simple word wrapping
            value_words = value.split(' ')
            for word in value_words:
                test_line = current_line + (" " if current_line else "") + word
                try:
                    line_width = get_text_width(test_line)
                except Exception as e:
                    logger.warning(f"Could not get width for '{test_line}': {e}. Using rough estimate.")
                    line_width = len(test_line) * font_size * 0.6 # Very rough fallback

                if line_width <= value_column_width:
                    current_line = test_line # Word fits, add to current line
                else:
                    # Word doesn't fit on current line
                    if current_line: # If there was text on the line already, add it
                        wrapped_value_lines.append(current_line)

                    # Handle word longer than the entire line width by breaking it
                    try:
                        word_width = get_text_width(word)
                    except Exception: word_width = len(word) * font_size * 0.6

                    if word_width > value_column_width:
                         logger.debug(f"Wrapping long word: {word}")
                         # Simple character-based breaking for very long words
                         avg_char_width = get_text_width("abc") / 3 if get_text_width("abc") > 0 else font_size * 0.6
                         chars_per_line = max(1, int(value_column_width / avg_char_width)) if avg_char_width > 0 else 10
                         temp_word = word
                         while len(temp_word) > 0:
                             wrapped_value_lines.append(temp_word[:chars_per_line])
                             temp_word = temp_word[chars_per_line:]
                         current_line = "" # Reset current line as the long word was fully processed
                    else:
                         # Start a new line with the current word
                         current_line = word

            # Add the last line if it has content
            if current_line:
                wrapped_value_lines.append(current_line)

            # If wrapping resulted in no lines (e.g., empty value), use "N/A"
            if not wrapped_value_lines: wrapped_value_lines = ["N/A"]

            key_text = f"{key}:" if key else "" # Format key
            prepared_lines.append((key_text, wrapped_value_lines))
            total_text_height += len(wrapped_value_lines) * single_line_height # Add height for these lines

        # Calculate total image height: top padding + total text height + bottom padding
        total_height = 10 + total_text_height + 10

        # --- Draw the image ---
        try:
            img = Image.new("RGB", (img_width, total_height), color=(0, 0, 0)) # Black background
            draw = ImageDraw.Draw(img)

            y = 10 # Starting Y position (below top padding)
            key_x = side_margin
            value_x = side_margin + key_column_width + key_value_gap
            text_color = (230, 230, 230) # Light gray text

            # Draw each prepared line
            for key_text, value_lines in prepared_lines:
                # Store starting Y for this key/value pair to align multi-line values correctly
                pair_start_y = y
                if key_text:
                    # Draw the key text, aligned with the first line of the value
                    draw.text((key_x, pair_start_y), key_text, font=font, fill=text_color)

                # Draw the value lines
                current_line_y = pair_start_y
                for line in value_lines:
                    draw.text((value_x, current_line_y), line, font=font, fill=text_color)
                    current_line_y += single_line_height # Move Y down for the next value line

                # Update the main Y position to the start of the next key/value pair
                y = current_line_y

            # Define output path and save the image
            output_path = self.temp_dir / f"{self.base_filename}_info.png"
            img.save(output_path, format="PNG")
            logger.debug(f"Info image created: {output_path.name} (Dimensions: {img_width}x{total_height})")
            return output_path
        except Exception as e:
            logger.error(f"Error generating or saving info image: {e}")
            if 'img' in locals() and hasattr(img, 'close'): img.close() # Ensure image is closed on error
            return None

    def _stack_videos(self, input_paths: List[Path], output_path: Path, axis: str = 'h') -> bool:
        """Stacks videos horizontally ('h') or vertically ('v') using ffmpeg filtergraph."""
        if not input_paths:
            logger.error("No input paths provided for stacking.")
            return False

        num_inputs = len(input_paths)
        if num_inputs == 0 : return False # Should be caught above, but safety check
        if num_inputs == 1: # No stacking needed, just copy/move? Or re-encode? Let's re-encode for consistency.
             logger.debug(f"Only one input for stacking, re-encoding: {input_paths[0].name} -> {output_path.name}")
             copy_cmd = f'ffmpeg -hide_banner -loglevel error -i "{input_paths[0]}" -c:v libx264 -crf 23 -preset medium -an -y "{output_path}"'
             _, stderr, exit_code = run_command(copy_cmd)
             if exit_code != 0: logger.error(f"Failed to copy single input for stacking: {stderr}"); return False
             return True


        stack_func = "hstack" if axis == 'h' else "vstack"
        inputs_str = ' '.join([f'-i "{p}"' for p in input_paths]) # Prepare '-i path' arguments

        # --- Ensure consistent resolution before stacking ---
        # Get dimensions of the first video as the target
        first_vid_meta_cmd = f'ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0:s=x "{input_paths[0]}"'
        stdout, _, code = run_command(first_vid_meta_cmd)
        target_w, target_h = -1, -1 # Initialize
        if code == 0 and 'x' in stdout:
            try: target_w, target_h = map(int, stdout.strip().split('x'))
            except ValueError: logger.warning("Could not parse dimensions from first video for stacking.")
        else: logger.warning(f"Could not get dimensions of first video '{input_paths[0].name}' for stacking.")

        # Fallback dimensions if probe failed (use typical segment dimensions)
        if target_w <= 0 or target_h <= 0:
             target_w, target_h = (270, 480) if self.is_vertical and not self.config.ADD_BLACK_BARS else (480, 270)
             logger.warning(f"Using fallback dimensions for stacking: {target_w}x{target_h}")

        # Create scale filter parts for each input
        scale_filters = ""
        scaled_inputs_refs = []
        for i in range(num_inputs):
            scaled_ref = f"[scaled{i}]"
            # Scale each input [i:v] to target WxH and assign to [scaled_i]
            scale_filters += f"[{i}:v]scale={target_w}:{target_h}:force_original_aspect_ratio=disable[scaled{i}];"
            scaled_inputs_refs.append(scaled_ref)

        # Concatenate the references to the scaled inputs (e.g., [scaled0][scaled1][scaled2])
        filter_inputs_scaled = ''.join(scaled_inputs_refs)

        # Combine scale filters and the stack filter
        filter_complex = f'"{scale_filters}{filter_inputs_scaled}{stack_func}=inputs={num_inputs}[v]"'

        # Map the final output stream [v]
        map_str = '-map "[v]"'
        # Use a reasonable output FPS
        fps_output = f"-r {self.metadata.get('fps', 24):.2f}" # Use video FPS or default 24

        # Construct the full ffmpeg command
        command = (f'ffmpeg -hide_banner -loglevel error {inputs_str} '
                   f'-filter_complex {filter_complex} {map_str} '
                   f'-c:v libx264 -crf 23 -preset medium ' # Encode output
                   f'{fps_output} -an -y "{output_path}"') # Set FPS, no audio, overwrite

        logger.debug(f"Stacking command ({axis}, {num_inputs} inputs): {command}")
        _, stderr, exit_code = run_command(command)

        if exit_code != 0:
            logger.error(f"Video stacking ({axis}) failed. Exit Code: {exit_code}")
            if stderr: logger.error(f"  FFmpeg stderr: {stderr}")
            output_path.unlink(missing_ok=True) # Clean up failed output
            return False

        logger.debug(f"Stacked video created ({axis}): {output_path.name}")
        return True

    def _generate_webp_preview_sheet(self) -> bool:
        """Generates the animated WebP preview sheet with info header."""
        logger.info("Generating animated WebP preview sheet...")
        # Use segments specifically prepared for the sheet (may have timestamps if mode=2)
        sheet_segments = self.timestamped_segment_files
        if not sheet_segments:
            logger.error("No valid segments available for WebP sheet generation.")
            return False

        # 1. Create the info image header
        info_image_path = self._create_info_image()
        if not info_image_path:
            logger.error("Failed to create info image header. Cannot generate WebP sheet.")
            return False

        # 2. Create a video from the info image
        # Match the duration of the video segments (use config value)
        info_video_duration = self.config.SEGMENT_DURATION
        if not info_video_duration > 0:
             logger.error("Invalid segment duration in config, cannot create info video.")
             return False
        info_video_path = self.temp_dir / f"{self.base_filename}_info_video.mp4"
        cmd_info_vid = (f'ffmpeg -hide_banner -loglevel error -loop 1 ' # Loop the image input
                        f'-framerate {self.metadata.get("fps", 24):.2f} ' # Match video FPS
                        f'-t {info_video_duration:.3f} ' # Set duration
                        f'-i "{info_image_path}" ' # Input image
                        f'-c:v libx264 -pix_fmt yuv420p ' # Encode to common format
                        f'-y "{info_video_path}"')
        logger.debug(f"Info video generation command: {cmd_info_vid}")
        _, stderr, code = run_command(cmd_info_vid)
        if code != 0:
            logger.error(f"Failed to create video from info image. Exit Code: {code}")
            if stderr: logger.error(f"  FFmpeg stderr: {stderr}")
            return False
        logger.debug("Info header video created.")


        # 3. Stack segments horizontally into rows
        grid = self.config.GRID_WIDTH
        h_stacked_videos = [] # List to hold paths of the horizontally stacked row videos
        num_segments = len(sheet_segments)
        num_rows = (num_segments + grid - 1) // grid # Calculate number of rows needed

        for r in range(num_rows):
            row_start_index = r * grid
            row_end_index = min((r + 1) * grid, num_segments)
            group = sheet_segments[row_start_index : row_end_index]

            if not group: continue # Skip if group is empty (shouldn't happen with calculation)

            # If the last row is partial, pad it with black videos
            num_missing = grid - len(group)
            if num_missing > 0:
                 logger.warning(f"Row {r+1} is partial ({len(group)}/{grid} segments). Padding with black videos.")
                 # Create a black video placeholder matching the first segment's properties
                 first_seg_path = group[0]
                 # Get dimensions, duration, FPS from the first segment in the group
                 ffprobe_cmd = (f'ffprobe -v error -select_streams v:0 '
                                f'-show_entries stream=width,height,r_frame_rate -show_entries format=duration '
                                f'-of default=noprint_wrappers=1:nokey=1 "{first_seg_path}"')
                 stdout, _, p_code = run_command(ffprobe_cmd)
                 w, h, fps, dur = 480, 270, f"{self.metadata.get('fps', 24):.2f}", f"{self.config.SEGMENT_DURATION:.3f}" # Defaults
                 if p_code == 0 and stdout:
                    lines = stdout.strip().split('\n')
                    try: # Robust parsing
                        w = int(lines[0]) if len(lines)>0 else w
                        h = int(lines[1]) if len(lines)>1 else h
                        fps_str = lines[2] if len(lines)>2 else fps
                        if '/' in fps_str: num, den = map(int, fps_str.split('/')); fps = f"{num/den:.2f}" if den else fps
                        dur = f"{float(lines[3]):.3f}" if len(lines)>3 else dur
                    except (ValueError, IndexError, ZeroDivisionError) as parse_e:
                        logger.warning(f"Failed parsing segment properties for black placeholder: {parse_e}. Using defaults.")

                 black_vid_path = self.temp_dir / f"black_placeholder_row{r+1}.mp4"
                 cmd_black = (f'ffmpeg -hide_banner -loglevel error -f lavfi '
                              f'-i color=c=black:s={w}x{h}:r={fps}:d={dur} ' # Use detected/default properties
                              f'-c:v libx264 -pix_fmt yuv420p -y "{black_vid_path}"')

                 logger.debug(f"Black placeholder command: {cmd_black}")
                 _, black_stderr, black_code = run_command(cmd_black)
                 if black_code != 0:
                     logger.error(f"Failed to create black placeholder video for row {r+1}. Stderr: {black_stderr}. Aborting sheet generation.")
                     return False
                 # Add the required number of black placeholders to the group
                 group.extend([black_vid_path] * num_missing)

            # Stack the (potentially padded) group horizontally
            h_stack_output = self.temp_dir / f"hstacked_row_{r + 1}.mp4"
            if not self._stack_videos(group, h_stack_output, axis='h'):
                 logger.error(f"Failed to horizontally stack videos for row {r+1}.")
                 return False
            h_stacked_videos.append(h_stack_output)

        if not h_stacked_videos:
             logger.error("Horizontal stacking resulted in no row videos.")
             return False

        # 4. Stack the info video and all horizontal rows vertically
        final_sheet_video_path = self.temp_dir / f"{self.base_filename}_final_sheet_raw.mp4"
        all_v_inputs = [info_video_path] + h_stacked_videos # Info video first, then rows
        if not self._stack_videos(all_v_inputs, final_sheet_video_path, axis='v'):
             logger.error("Failed to vertically stack info header and rows.")
             return False

        # 5. Optional: Downscale the final sheet video if grid=4 and landscape
        final_processed_sheet_path = final_sheet_video_path # Start with the raw stacked path
        # Condition matches original script: Grid=4 AND (video is landscape OR black bars were added to vertical)
        is_landscape_effective = not self.is_vertical or self.config.ADD_BLACK_BARS
        if self.config.GRID_WIDTH == 4 and is_landscape_effective:
             logger.info("Grid=4 and effective landscape orientation detected. Attempting downscale.")
             downscaled_path = self.temp_dir / f"{self.base_filename}_final_sheet_downscaled.mp4"
             # Target width 1280px, maintain aspect ratio (-2)
             scale_filter = "scale=1280:-2"
             cmd_downscale = (f'ffmpeg -hide_banner -loglevel error -i "{final_sheet_video_path}" '
                              f'-vf "{scale_filter}" -c:v libx264 -crf 22 -preset medium -y "{downscaled_path}"')
             logger.debug(f"Downscaling command: {cmd_downscale}")
             _, stderr, code = run_command(cmd_downscale)
             if code == 0 and downscaled_path.exists() and downscaled_path.stat().st_size > 0:
                 logger.info("Downscaled grid=4 sheet video successfully.")
                 final_processed_sheet_path = downscaled_path # Use the downscaled version
                 # Optional: Clean up the larger raw file? Keep it simple for now.
             else:
                 logger.warning(f"Downscaling grid=4 sheet video failed (Exit Code: {code}). Stderr: {stderr}. Using original resolution sheet.")
                 # Keep final_processed_sheet_path as final_sheet_video_path

        # 6. Convert the final processed sheet video to animated WebP
        output_webp = self.output_dir / f"{self.base_filename}_preview_sheet.webp"
        cmd_webp = (f'ffmpeg -hide_banner -loglevel error -y '
                    f'-i "{final_processed_sheet_path}" ' # Input the (potentially downscaled) sheet video
                    f'-vf "fps=24,scale=iw:ih:flags=lanczos" ' # Ensure 24fps, lanczos scaling (iw:ih keeps current size)
                    f'-c:v libwebp -quality 75 -lossless 0 -loop 0 -an -vsync 0 ' # WebP options
                    f'"{output_webp}"')

        logger.debug(f"Final WebP sheet generation command: {cmd_webp}")
        _, stderr, code = run_command(cmd_webp)

        if code == 0 and output_webp.exists() and output_webp.stat().st_size > 0:
            logger.success(f"Animated WebP preview sheet created: {output_webp.name}")
            return True
        else:
            logger.error(f"Failed to generate final WebP sheet. Exit Code: {code}")
            if stderr: logger.error(f"  FFmpeg stderr: {stderr}")
            output_webp.unlink(missing_ok=True) # Clean up failed output
            return False

    def _extract_segment_frames(self) -> List[Path]:
        """Extracts a single frame from near the middle of each base segment video."""
        logger.info("Extracting frames for static image sheet...")
        extracted_frames = []
        # Use the base segments *before* timestamp overlay for frame extraction
        segments_to_frame = self.segment_files
        if not segments_to_frame:
            logger.error("No base segments available to extract frames from.")
            return []

        num_segments = len(segments_to_frame)
        # Try extracting near the middle, fallback to earlier if needed
        mid_point_time = self.config.SEGMENT_DURATION / 2.0
        fallback_seek_time = 0.1 # Time to seek to if midpoint fails

        for i, segment_path in enumerate(segments_to_frame):
            # Generate a unique frame filename based on the segment filename
            frame_filename = f"frame_{segment_path.stem}.png" # Use PNG for lossless frames
            frame_path = self.temp_dir / frame_filename
            frame_extracted = False

            # Ensure segment file exists before trying to extract
            if not segment_path.exists():
                logger.warning(f"Segment file missing, cannot extract frame: {segment_path.name}")
                continue

            # Attempt 1: Extract frame near the middle
            logger.debug(f"Attempting frame extraction (midpoint {mid_point_time:.3f}s) for: {segment_path.name}")
            # Use -ss before -i for faster seeking, -frames:v 1 to grab one frame
            cmd_frame_mid = (f'ffmpeg -hide_banner -loglevel error '
                             f'-ss {mid_point_time:.3f} -i "{segment_path}" '
                             f'-frames:v 1 -q:v 2 "{frame_path}" -y') # -q:v 2 is high quality for JPG/PNG
            _, stderr_mid, code_mid = run_command(cmd_frame_mid)

            if code_mid == 0 and frame_path.exists() and frame_path.stat().st_size > 100: # Check if file exists and has some size
                frame_extracted = True
                logger.debug(f"Extracted frame {i+1}/{num_segments} (midpoint): {frame_path.name}")
            else:
                logger.warning(f"Midpoint frame ({mid_point_time:.3f}s) extraction failed for {segment_path.name}. ExitCode: {code_mid}. Stderr: {stderr_mid}")
                frame_path.unlink(missing_ok=True) # Clean up potentially empty/corrupt file

                # Attempt 2: Extract frame near the beginning (fallback)
                logger.debug(f"Attempting frame extraction (fallback {fallback_seek_time:.3f}s) for: {segment_path.name}")
                cmd_frame_fallback = (f'ffmpeg -hide_banner -loglevel error '
                                      f'-ss {fallback_seek_time:.3f} -i "{segment_path}" '
                                      f'-frames:v 1 -q:v 2 "{frame_path}" -y')
                _, stderr_fallback, code_fallback = run_command(cmd_frame_fallback)

                if code_fallback == 0 and frame_path.exists() and frame_path.stat().st_size > 100:
                    frame_extracted = True
                    logger.debug(f"Extracted frame {i+1}/{num_segments} (fallback {fallback_seek_time:.3f}s): {frame_path.name}")
                else:
                    logger.error(f"Fallback frame ({fallback_seek_time:.3f}s) extraction also failed for {segment_path.name}. ExitCode: {code_fallback}. Stderr: {stderr_fallback}")
                    frame_path.unlink(missing_ok=True) # Clean up failed fallback attempt

            # Add the successfully extracted frame path to the list
            if frame_extracted:
                extracted_frames.append(frame_path)
            else:
                # Log error if both attempts failed for a segment
                logger.error(f"Could not extract a valid frame for segment: {segment_path.name}")

        # Log summary of frame extraction
        if not extracted_frames:
             logger.error("Failed to extract any frames for the image sheet.")
        elif len(extracted_frames) != num_segments:
             logger.warning(f"Extracted {len(extracted_frames)} frames, but expected {num_segments}. Image sheet may be incomplete.")

        return extracted_frames

    def _generate_image_preview_sheet(self) -> bool:
        """Generates the static image preview sheet using PIL."""
        logger.info("Generating static image preview sheet...")
        if not self.segment_frame_files:
            logger.error("No frames were extracted. Cannot generate image sheet.")
            return False

        # 1. Create the info image header
        info_image_path = self._create_info_image()
        if not info_image_path:
            logger.error("Info image header failed, cannot generate image sheet accurately.")
            return False

        sheet_created = False
        final_sheet_img = None # Initialize to None
        try:
            # 2. Open info image and get dimensions
            with Image.open(info_image_path) as info_img:
                info_w, info_h = info_img.size
                logger.debug(f"Using info image dimensions: {info_w}x{info_h}")

                # 3. Open first frame to get segment frame dimensions
                try:
                    # Ensure first frame exists before proceeding
                    if not self.segment_frame_files[0].exists():
                         raise FileNotFoundError(f"First frame image not found: {self.segment_frame_files[0]}")
                    with Image.open(self.segment_frame_files[0]) as first_frame_img:
                        frame_w, frame_h = first_frame_img.size
                        logger.debug(f"Detected frame dimensions: {frame_w}x{frame_h}")
                except FileNotFoundError as e:
                    logger.error(str(e)); return False
                except Exception as e:
                    logger.error(f"Failed to open or get dimensions of first frame '{self.segment_frame_files[0].name}': {e}")
                    return False # Cannot proceed without frame dimensions

                # 4. Calculate sheet dimensions
                grid = self.config.GRID_WIDTH
                num_frames_expected = self.config.NUM_OF_SEGMENTS # Use configured segment count for layout
                num_frames_extracted = len(self.segment_frame_files) # Actual number of frames available
                # Calculate rows based on *expected* number of frames to maintain grid structure
                num_rows = (num_frames_expected + grid - 1) // grid

                # Sheet width matches info image width (which should match grid width * frame width)
                sheet_width = info_w
                # Sheet height is info height + height of all frame rows
                sheet_height = info_h + (num_rows * frame_h)
                logger.debug(f"Calculated sheet dimensions: {sheet_width}x{sheet_height} ({num_rows} rows)")

                # 5. Create blank sheet image
                final_sheet_img = Image.new("RGB", (sheet_width, sheet_height), color=(40, 40, 40)) # Dark gray background
                # 6. Paste info image header at the top
                final_sheet_img.paste(info_img, (0, 0))

            # 7. Paste extracted frames onto the sheet
            for i, frame_path in enumerate(self.segment_frame_files):
                # Calculate position based on index (0-based)
                paste_x = (i % grid) * frame_w
                paste_y = info_h + (i // grid) * frame_h
                try:
                    with Image.open(frame_path) as frame_img:
                         # Optional: Verify frame dimensions and resize if needed (log warning)
                         if frame_img.size != (frame_w, frame_h):
                              logger.warning(f"Frame {frame_path.name} has unexpected dimensions {frame_img.size}, expected {frame_w}x{frame_h}. Resizing.")
                              frame_img = frame_img.resize((frame_w, frame_h), Image.Resampling.LANCZOS) # Use high quality resize
                         # Paste the frame
                         final_sheet_img.paste(frame_img.copy(), (paste_x, paste_y)) # Paste a copy
                except FileNotFoundError:
                    logger.error(f"Frame image not found during pasting: {frame_path.name}")
                    # Draw error placeholder
                    self._draw_placeholder(final_sheet_img, paste_x, paste_y, frame_w, frame_h, f"Error\nMissing\nFrame {i+1}")
                except Exception as e:
                    logger.error(f"Failed to open/paste frame {frame_path.name}: {e}")
                    # Draw error placeholder
                    self._draw_placeholder(final_sheet_img, paste_x, paste_y, frame_w, frame_h, f"Error\nLoad/Paste\nFrame {i+1}")


            # 8. Fill remaining grid slots if fewer frames were extracted than configured
            if num_frames_extracted < num_frames_expected:
                logger.warning(f"Only {num_frames_extracted}/{num_frames_expected} frames available. Filling remaining grid slots with placeholders.")
                for i in range(num_frames_extracted, num_frames_expected):
                    paste_x = (i % grid) * frame_w
                    paste_y = info_h + (i // grid) * frame_h
                    # Draw missing placeholder
                    self._draw_placeholder(final_sheet_img, paste_x, paste_y, frame_w, frame_h, f"Missing\nFrame {i+1}")

            # 9. Save the final sheet image
            output_suffix = f".{self.config.IMAGE_SHEET_FORMAT.lower()}"
            output_path = self.output_dir / f"{self.base_filename}_preview_sheet{output_suffix}"
            save_format = self.config.IMAGE_SHEET_FORMAT.upper()
            save_params = {}
            if save_format in ["JPG", "JPEG"]:
                 save_format = "JPEG"
                 save_params['quality'] = 85 # Good quality for JPEG
            elif save_format == "PNG":
                 save_params['optimize'] = True # Optimize PNG size

            logger.debug(f"Saving image sheet to {output_path} as {save_format} with params {save_params}")
            final_sheet_img.save(output_path, format=save_format, **save_params)
            logger.success(f"Static image preview sheet created: {output_path.name}")
            sheet_created = True

        except Exception as e:
            logger.exception(f"Failed to generate image sheet: {e}")
        finally:
            # Ensure image objects are closed if they exist
             if final_sheet_img:
                 final_sheet_img.close()

        return sheet_created

    def _draw_placeholder(self, image: Image.Image, x: int, y: int, w: int, h: int, text: str):
        """Draws a placeholder rectangle with text on the image."""
        try:
            draw = ImageDraw.Draw(image)
            # Dark red rectangle, slightly inset
            draw.rectangle([x + 2, y + 2, x + w - 2, y + h - 2], fill=(60, 0, 0), outline=(120, 0, 0))
            # Load default font for placeholder text
            try: placeholder_font = ImageFont.load_default(size=10)
            except TypeError: placeholder_font = ImageFont.load_default()
            # Draw text centered (approximately)
            text_bbox = draw.textbbox((x, y), text, font=placeholder_font)
            text_w = text_bbox[2] - text_bbox[0]
            text_h = text_bbox[3] - text_bbox[1]
            text_x = x + (w - text_w) / 2
            text_y = y + (h - text_h) / 2
            draw.text((text_x, text_y), text, fill=(180, 180, 180), font=placeholder_font, align="center")
        except Exception as draw_e:
            logger.error(f"Failed drawing placeholder box: {draw_e}")


# --- Main Execution ---
def main():
    """Main function to find videos and process them."""
    # --- GUI CODE START ---
    root = tk.Tk()
    root.withdraw()  # Hide the main Tkinter window
    logger.info("Prompting user to select input folder via GUI...")
    selected_folder = filedialog.askdirectory(title="Select Folder Containing Videos")

    # Explicitly destroy the root window *after* the dialog is closed
    try:
        root.destroy()
    except tk.TclError:
        pass # Ignore error if window already destroyed (e.g., user closed it manually)

    if not selected_folder:
        logger.error("No folder selected. Exiting.")
        sys.exit(1)

    # Update the Config class variable *before* validation
    Config.INPUT_FOLDER = selected_folder
    logger.info(f"User selected folder: {Config.INPUT_FOLDER}")
    # --- GUI CODE END ---

    # --- SCRIPT INITIALIZATION ---
    start_time = datetime.now()
    log_file_name = f"VideoPreviewer_{start_time:%Y%m%d_%H%M%S}.log"
    # Determine log directory robustly (relative to script or CWD)
    try:
        script_dir = Path(__file__).parent
    except NameError: # Fallback if running interactively, frozen, or __file__ not defined
        script_dir = Path.cwd()
    log_dir = script_dir / "logs"
    try:
        log_dir.mkdir(exist_ok=True)
        log_file_path = log_dir / log_file_name
    except OSError as e:
        print(f"Error: Could not create log directory {log_dir}: {e}. Logging to current directory.")
        log_file_path = Path.cwd() / log_file_name


    # Setup logging configuration
    logger.remove() # Remove default handler
    # Console handler (INFO level)
    logger.add(sys.stderr, level="INFO", format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>")
    # File handler (DEBUG level)
    try:
        logger.add(log_file_path, level="DEBUG", rotation="10 MB", retention="7 days", encoding='utf-8',
                   format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}")
        logger.info(f"Logging DEBUG information to: {log_file_path.resolve()}")
    except Exception as log_e:
        logger.error(f"Failed to configure file logging to {log_file_path}: {log_e}")


    logger.info("="*20 + " Starting Video Previewer Script " + "="*20)
    logger.info(f"Using input folder: {Config.INPUT_FOLDER}") # Log the folder being used

    # Validate configuration after potential updates (GUI, font fallback)
    if not Config.validate():
        logger.error("Configuration validation failed. Please check settings. Exiting.")
        sys.exit(1)

    # --- FILE SCANNING ---
    input_folder = Path(Config.INPUT_FOLDER) # Use the validated path
    excluded_lower = [f.lower() for f in Config.EXCLUDED_FILES if f] # Prepare lowercase list for efficient checking
    video_files_found = []
    try:
        logger.info(f"Scanning input folder for videos: {input_folder}")
        items_in_folder = list(input_folder.iterdir())
        logger.debug(f"Found {len(items_in_folder)} items in the folder.")

        for item in items_in_folder:
            # Check if it's a file and has a valid video extension
            if item.is_file() and item.suffix.lower() in Config.VALID_VIDEO_EXTENSIONS:
                # Check if it's in the exclusion list
                if item.name.lower() not in excluded_lower:
                    video_files_found.append(item)
                    logger.debug(f"  Found video: {item.name}")
                else:
                    logger.info(f"Skipping excluded file: {item.name}")
            # Log reasons for skipping other items (optional, for debugging)
            elif item.is_dir():
                 logger.debug(f"Skipping directory: {item.name}")
            elif not item.is_file():
                 logger.debug(f"Skipping non-file item: {item.name}")
            elif item.suffix.lower() not in Config.VALID_VIDEO_EXTENSIONS:
                 logger.debug(f"Skipping file with non-video extension '{item.suffix}': {item.name}")

    except FileNotFoundError:
        # This should ideally be caught by Config.validate() after GUI selection
        logger.error(f"Input folder not found during scan: {input_folder}")
        sys.exit(1)
    except PermissionError:
        logger.error(f"Permission denied reading folder: {input_folder}")
        sys.exit(1)
    except Exception as scan_e:
        logger.exception(f"An error occurred while scanning the input folder: {scan_e}")
        sys.exit(1)

    # --- PROCESSING LOOP ---
    if not video_files_found:
        logger.warning(f"No valid, non-excluded video files found in '{input_folder}'. Nothing to process.")
    else:
        total_files = len(video_files_found)
        logger.info(f"Found {total_files} video file(s) to process.")
        processed_count = 0
        success_count = 0
        failure_count = 0

        for i, video_file in enumerate(video_files_found):
            current_file_num = i + 1
            logger.info(f"--- [{current_file_num}/{total_files}] Starting: {video_file.name} ---")
            processed_count += 1
            try:
                # Create processor instance for the video
                processor = VideoProcessor(video_file, Config)
                # Run the processing workflow
                result = processor.run()

                if result:
                     success_count += 1
                     logger.info(f"--- [{current_file_num}/{total_files}] Completed: {processor.video_path.name} ---") # Log final name
                else:
                     failure_count += 1
                     # Specific error logged within processor.run() or _check_existing_outputs()
                     logger.error(f"--- [{current_file_num}/{total_files}] Failed/Skipped: {video_file.name} ---")

            except KeyboardInterrupt:
                 logger.warning("--- Processing interrupted by user (Ctrl+C) ---")
                 # Log which file was being processed when interrupted
                 logger.warning(f"Interrupted while processing: {video_file.name}")
                 failure_count += (total_files - i) # Count remaining files as failed/skipped due to interrupt
                 break # Exit the loop immediately
            except Exception as e:
                # Catch unexpected errors during the processing of a single file
                logger.exception(f"Unhandled exception processing {video_file.name}: {e}")
                failure_count += 1
                # Continue to the next file instead of exiting the script

    # --- SCRIPT COMPLETION ---
    end_time = datetime.now()
    logger.info("="*20 + " Processing complete " + "="*20)
    logger.info(f"Total videos found: {len(video_files_found)}")
    if video_files_found: # Only show processing stats if files were found/attempted
        logger.info(f"Successfully processed (outputs generated/moved): {success_count}")
        logger.info(f"Failed or skipped: {failure_count}")
    logger.info(f"Total time taken: {end_time - start_time}")
    logger.info(f"Log file saved to: {log_file_path.resolve()}")
    logger.info("="*57)


# --- Entry Point ---
if __name__ == "__main__":
    # Ensure dependencies like ffmpeg/ffprobe are likely available (optional check)
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        print("ERROR: ffmpeg or ffprobe not found in system PATH.")
        print("Please install FFmpeg (which includes ffprobe) and ensure it's accessible.")
        # Log this error as well
        logger.error("ffmpeg or ffprobe not found in system PATH. Cannot proceed.")
        # Optionally exit here, or let the script fail later when commands are run
        # sys.exit(1) # Uncomment to exit immediately if FFmpeg is missing

    main()
