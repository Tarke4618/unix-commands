#!/usr/bin/env python3

import os
import sys
import json
import shutil
import requests
import mimetypes
import subprocess
import unicodedata
import re
import hashlib
import random
import tkinter as tk
from tkinter import messagebox, filedialog
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

try:
    import tkinter
except ImportError:
    logger.error("tkinter is not installed. Please ensure it is available (usually included with Python).")
    sys.exit(1)

import configparser

# --- Configuration ---
class Config:
    # Paths
    CUSTOM_OUTPUT_PATH: Optional[str] = None  # e.g., r"/home/user/previews"

    # --- Load from config.ini ---
    config = configparser.ConfigParser()
    config.read(os.path.join(os.path.dirname(__file__), 'config.ini'))

    # Metadata Extraction Settings
    API_URL = config.get('Western', 'api_url', fallback='https://theporndb.net/graphql')
    API_TOKEN = config.get('Western', 'api_token')

    if API_TOKEN == 'YOUR_API_TOKEN_HERE' or not API_TOKEN:
        print("API token is not configured. Please edit config.ini and set your ThePornDB API token.")
        exit(1)

    QUERY = """
    query GetSceneMetadata($term: String!) {
      searchScene(term: $term) {
        title
        date
        images {
          url
        }
        performers {
          performer {
            name
          }
        }
        studio {
          name
        }
        details
        tags {
          name
        }
      }
    }
    """

    # Preview Generation Settings
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
    TIMESTAMPS_MODE = 2  # 1=ON Everywhere, 2=ON Only Animated Sheet, 3=OFF
    IMAGE_SHEET_FORMAT = "PNG"
    CALCULATE_MD5 = False
    KEEP_TEMP_FILES = False
    IGNORE_EXISTING = True
    PRINT_CUT_POINTS = False
    CONFIRM_CUT_POINTS_REQUIRED = False
    BLACKLISTED_CUT_POINTS = []
    EXCLUDED_FILES = [""]
    FONT_PATH = config.get('General', 'font_path', fallback='/usr/share/fonts/liberation/LiberationSans-Regular.ttf')

    VALID_VIDEO_EXTENSIONS = (".mp4", ".mkv", ".m2ts", ".m4v", ".avi", ".ts", ".wmv", ".mov")

    @classmethod
    def validate(cls):
        input_path = Path(cls.INPUT_FOLDER)
        if not input_path.is_dir():
            logger.error(f"Input folder '{cls.INPUT_FOLDER}' not found.")
            return False

        if cls.CUSTOM_OUTPUT_PATH:
            output_path = Path(cls.CUSTOM_OUTPUT_PATH)
            output_path.mkdir(parents=True, exist_ok=True)
            cls.CUSTOM_OUTPUT_PATH = str(output_path)

        if cls.CREATE_WEBP_PREVIEW_SHEET:
            if cls.GRID_WIDTH not in [3, 4]:
                logger.error(f"Invalid GRID_WIDTH ({cls.GRID_WIDTH}). Must be 3 or 4.")
                return False
            min_segments = 9 if cls.GRID_WIDTH == 3 else 12
            max_segments = 30 if cls.GRID_WIDTH == 3 else 28
            if not (min_segments <= cls.NUM_OF_SEGMENTS <= max_segments and cls.NUM_OF_SEGMENTS % cls.GRID_WIDTH == 0):
                logger.error(f"NUM_OF_SEGMENTS ({cls.NUM_OF_SEGMENTS}) invalid for GRID_WIDTH {cls.GRID_WIDTH}.")
                return False

        if not Path(cls.FONT_PATH).is_file():
            logger.warning(f"Font not found at '{cls.FONT_PATH}'. Text overlays may fail.")
        
        if cls.IMAGE_SHEET_FORMAT.upper() not in ["PNG", "JPG", "JPEG"]:
            logger.warning(f"Invalid IMAGE_SHEET_FORMAT '{cls.IMAGE_SHEET_FORMAT}'. Defaulting to PNG.")
            cls.IMAGE_SHEET_FORMAT = "PNG"

        logger.info("Configuration validated.")
        return True

# --- Utility Functions ---
def run_command(command: str, cwd: Optional[str] = None) -> Tuple[str, str, int]:
    try:
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
    try:
        td = timedelta(seconds=int(seconds))
        hours, remainder = divmod(td.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if td.days > 0:
            hours += td.days * 24
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    except Exception:
        return "00:00:00"

def sanitize_filename(filename: str) -> str:
    normalized = unicodedata.normalize('NFKD', filename).encode('ascii', 'ignore').decode('ascii')
    sanitized = re.sub(r'[<>:"/\\|?*\'\s]+', '_', normalized)
    sanitized = re.sub(r'_+', '_', sanitized).strip('_')
    return sanitized if sanitized else f"sanitized_{random.randint(1000, 9999)}"

def get_md5_hash(file_path: Path) -> str:
    hash_md5 = hashlib.md5()
    try:
        with file_path.open("rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception as e:
        logger.error(f"Error computing MD5 hash for {file_path.name}: {e}")
        return "N/A"

# --- Metadata Extraction Functions ---
def format_tags(tags):
    return " ".join(tag["name"].lower().replace(" ", ".") for tag in tags)

def generate_title_from_filename(filename):
    base_name = os.path.splitext(filename)[0]
    resolution = ""
    if "[" in base_name and "]" in base_name:
        start = base_name.rfind("[")
        end = base_name.rfind("]")
        if start < end:
            resolution = base_name[start:end+1]
            base_name = base_name[:start].strip()
    title = base_name.replace(".", " ").strip()
    return f"[{title}] {resolution}".strip()

def search_video_metadata(filename):
    search_term = os.path.splitext(filename)[0]
    headers = {"Authorization": f"Bearer {Config.API_TOKEN}"}
    variables = {"term": search_term}
    response = requests.post(Config.API_URL, headers=headers, json={"query": Config.QUERY, "variables": variables})
    if response.status_code == 200:
        data = response.json()
        if "data" in data and data["data"]["searchScene"]:
            return data["data"]["searchScene"][0]
        else:
            logger.info(f"No metadata found for {filename}")
            return None
    else:
        logger.error(f"API Error: {response.status_code} - {response.text}")
        return None

def download_cover_image(image_url, base_output_path):
    try:
        response = requests.get(image_url, stream=True)
        if response.status_code == 200:
            content_type = response.headers.get('content-type', '')
            extension = mimetypes.guess_extension(content_type) or '.webp'
            output_path = f"{base_output_path}{extension}"
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            logger.debug(f"Cover image saved: {output_path}")
            return True, os.path.basename(output_path)
        else:
            logger.error(f"Failed to download image from {image_url}: Status {response.status_code}")
            return False, None
    except Exception as e:
        logger.error(f"Error downloading image from {image_url}: {str(e)}")
        return False, None

def create_text_file(file_path, metadata, filename, output_dir):
    title = metadata.get("title", "Unknown Title")
    date = metadata.get("date", "Unknown Date")
    performers = metadata.get("performers", [])
    studio = metadata.get("studio", {}).get("name", "Unknown Studio")
    details = metadata.get("details", "No Plot Available")
    tags = metadata.get("tags", [])
    images = metadata.get("images", [])

    cast_list = "\n".join(f"[*] {p['performer']['name']}" for p in performers)
    tags_list = format_tags(tags)
    formatted_title = generate_title_from_filename(filename)

    cover_field = "[No cover available]"
    if images and isinstance(images, list) and 'url' in images[0]:
        image_url = images[0]['url']
        base_cover_filename = f"{os.path.splitext(filename)[0]}_cover"
        base_cover_path = os.path.join(output_dir, base_cover_filename)
        success, cover_filename = download_cover_image(image_url, base_cover_path)
        if success and cover_filename:
            cover_field = cover_filename
        else:
            cover_field = "[Failed to download cover]"

    content = f"""[details]
{studio} - {date}
{title}

[hr]
[cast]
{cast_list}

[hr]
[plot]
{details}

[hr]
[screens]
[img][/img]

[hr]
[info]

[tags]
{tags_list}

[title]
{formatted_title}

[cover]
{cover_field}
"""
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    logger.debug(f"Text file saved: {file_path}")

def process_metadata_extraction(video_files):
    processed = 0
    successes = 0
    for video_file in video_files:
        filename = video_file.name
        if filename.lower().endswith(Config.VALID_VIDEO_EXTENSIONS):
            logger.info(f"Processing metadata for: {filename}")
            processed += 1
            metadata = search_video_metadata(filename)
            if metadata:
                base_filename = sanitize_filename(os.path.splitext(filename)[0])
                output_dir = Path(Config.INPUT_FOLDER) / base_filename
                output_dir.mkdir(parents=True, exist_ok=True)
                file_path = output_dir / f"{base_filename}.txt"
                create_text_file(file_path, metadata, filename, output_dir)
                logger.success(f"Text file created: {file_path}")
                successes += 1
            else:
                logger.info(f"Metadata not found for: {filename}")
    return processed, successes

# --- Video Processor Class ---
class VideoProcessor:
    def __init__(self, video_path: Path, config: Config):
        self.video_path = video_path
        self.config = config
        self.base_filename = sanitize_filename(video_path.stem)
        if self.config.ADD_BLACK_BARS:
            self.base_filename += "_black_bars"
        base_output_dir = Path(config.CUSTOM_OUTPUT_PATH or config.INPUT_FOLDER)
        self.output_dir = base_output_dir / self.base_filename
        self.temp_dir = self.output_dir / f"{self.base_filename}-temp"
        self.metadata: Dict[str, Any] = {}
        self.cut_points_sec: List[float] = []
        self.segment_files: List[Path] = []
        self.timestamped_segment_files: List[Path] = []
        self.segment_frame_files: List[Path] = []
        self.is_vertical = False

    def run(self):
        should_process = self._check_existing_outputs()
        if not should_process:
            logger.info(f"Skipping {self.video_path.name}: Outputs exist and IGNORE_EXISTING={self.config.IGNORE_EXISTING}")
            return False

        logger.info(f"--- Processing: {self.video_path.name} ---")
        logger.info(f"Target output directory: {self.output_dir}")
        sleep(0.2)

        if not self._get_metadata():
            logger.error(f"Failed to get metadata for {self.video_path.name}. Aborting.")
            return False

        video_duration = self.metadata.get("duration", 0)
        if video_duration <= 10:
            logger.error(f"Video duration ({video_duration:.1f}s) is too short (< 10s). Aborting.")
            return False

        processing_successful = False
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            self.temp_dir.mkdir(parents=True, exist_ok=True)
            cut_points_pct = self._generate_cut_points()
            if not cut_points_pct:
                logger.error("No valid cut points generated. Aborting.")
                return False
            self.cut_points_sec = [p * video_duration for p in cut_points_pct]
            self.segment_files, self.timestamped_segment_files = self._generate_segments()
            if not self.segment_files:
                logger.error("No valid segments generated. Aborting.")
                return False

            results = []
            if self.config.CREATE_WEBP_PREVIEW:
                logger.info("Attempting WebP preview generation")
                results.append(self._generate_webp_preview())
            if self.config.CREATE_WEBP_PREVIEW_SHEET:
                logger.info("Attempting WebP preview sheet generation")
                results.append(self._generate_webp_preview_sheet())
            if self.config.CREATE_IMAGE_PREVIEW_SHEET:
                logger.info("Attempting image preview sheet generation")
                self.segment_frame_files = self._extract_segment_frames()
                if self.segment_frame_files:
                    results.append(self._generate_image_preview_sheet())
                else:
                    logger.error("Failed to extract frames for image sheet.")
                    results.append(False)

            processing_successful = any(r is True for r in results)
            if processing_successful:
                logger.success(f"Finished processing: {self.video_path.name}")
                # Move the original video file to output_dir
                new_video_path = self.output_dir / self.video_path.name
                if new_video_path.exists():
                    logger.warning(f"Video already exists at {new_video_path}. Skipping move to avoid overwrite.")
                else:
                    try:
                        shutil.move(str(self.video_path), str(new_video_path))
                        logger.info(f"Moved video to: {new_video_path}")
                    except Exception as e:
                        logger.error(f"Failed to move video {self.video_path.name} to {new_video_path}: {e}")
            else:
                logger.error(f"Processing failed to generate any outputs for {self.video_path.name}.")

        except Exception as e:
            logger.exception(f"Error processing {self.video_path.name}: {e}")
            processing_successful = False
        finally:
            if not self.config.KEEP_TEMP_FILES and self.temp_dir.exists():
                logger.info(f"Removing temp folder: {self.temp_dir}")
                shutil.rmtree(self.temp_dir, ignore_errors=True)
            sleep(0.1)
        return processing_successful

    def _check_existing_outputs(self) -> bool:
        img_sheet_suffix = f".{self.config.IMAGE_SHEET_FORMAT.lower()}"
        output_files_config = {
            "WebP Preview": (self.output_dir / f"{self.base_filename}_preview.webp", self.config.CREATE_WEBP_PREVIEW),
            "WebP Sheet": (self.output_dir / f"{self.base_filename}_preview_sheet.webp", self.config.CREATE_WEBP_PREVIEW_SHEET),
            "Image Sheet": (self.output_dir / f"{self.base_filename}_preview_sheet{img_sheet_suffix}", self.config.CREATE_IMAGE_PREVIEW_SHEET),
        }

        required_files_exist = []
        required_files_missing = []
        files_to_delete = []

        for name, (file_path, create_flag) in output_files_config.items():
            if create_flag:
                if file_path.exists():
                    required_files_exist.append(name)
                else:
                    required_files_missing.append(name)

        if not required_files_missing and not self.config.IGNORE_EXISTING:
            logger.info(f"All required outputs exist for '{self.base_filename}'. Skipping.")
            return False

        if required_files_exist and self.config.IGNORE_EXISTING:
            logger.info(f"IGNORE_EXISTING is True. Deleting existing outputs for '{self.base_filename}'...")
            for name, file_path in [(n, p) for n, (p, f) in output_files_config.items() if f and p.exists()]:
                logger.info(f"  Deleting: {file_path.name}")
                try:
                    file_path.unlink()
                except OSError as e:
                    logger.error(f"  Failed to delete {file_path.name}: {e}")
                    return False
                sleep(0.05)
        elif required_files_exist:
            logger.warning(f"Some outputs exist for '{self.base_filename}': {required_files_exist}")
            for name in required_files_exist:
                logger.warning(f"  Existing: {name}")
            logger.info("Proceeding to generate missing outputs.")
        return True

    def _get_metadata(self) -> bool:
        cmd = f'ffprobe -v error -print_format json -show_format -show_streams "{self.video_path}"'
        stdout, stderr, exit_code = run_command(cmd)
        if exit_code != 0:
            logger.error(f"ffprobe failed: {stderr}")
            return False
        try:
            data = json.loads(stdout)
            video_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
            audio_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)
            format_info = data.get("format", {})
            if not video_stream:
                logger.error(f"No video stream found for {self.video_path.name}")
                return False

            self.metadata["filename"] = self.video_path.name
            self.metadata["title"] = format_info.get("tags", {}).get("title", "N/A")
            self.metadata["duration"] = float(format_info.get("duration", 0))
            self.metadata["size_bytes"] = int(format_info.get("size", 0))
            self.metadata["size_mb"] = f"{self.metadata['size_bytes'] / (1024*1024):.2f} MB"
            width = video_stream.get("width")
            height = video_stream.get("height")
            if not width or not height:
                logger.error(f"Could not get resolution")
                return False
            self.metadata["width"] = width
            self.metadata["height"] = height
            self.is_vertical = width < height
            self.metadata["resolution"] = f"{width}x{height}"
            self.metadata["video_codec"] = video_stream.get("codec_name", "N/A").upper()
            self.metadata["video_profile"] = video_stream.get("profile", "N/A")
            video_bitrate_str = video_stream.get("bit_rate")
            self.metadata["video_bitrate_kbps"] = round(int(video_bitrate_str) / 1000) if video_bitrate_str else 0
            fps_str = video_stream.get("r_frame_rate", "0/1")
            try:
                num, den = map(int, fps_str.split('/'))
                self.metadata["fps"] = round(num / den, 2) if den else 0
            except ValueError:
                self.metadata["fps"] = 0
            self.metadata["video_details"] = (f"{self.metadata['video_codec']} ({self.metadata['video_profile']}) @ "
                                            f"{self.metadata['video_bitrate_kbps']} kbps, {self.metadata['fps']} fps")
            if audio_stream:
                self.metadata["audio_codec"] = audio_stream.get("codec_name", "N/A").upper()
                self.metadata["audio_profile"] = audio_stream.get("profile", "N/A")
                self.metadata["audio_channels"] = audio_stream.get("channels", "N/A")
                audio_bitrate_str = audio_stream.get("bit_rate")
                self.metadata["audio_bitrate_kbps"] = round(int(audio_bitrate_str) / 1000) if audio_bitrate_str else 0
                self.metadata["audio_details"] = (f"{self.metadata['audio_codec']} ({self.metadata['audio_profile']}, "
                                                f"{self.metadata['audio_channels']}ch) @ {self.metadata['audio_bitrate_kbps']} kbps")
            else:
                self.metadata["audio_details"] = "No Audio Stream"
            if self.config.CALCULATE_MD5:
                self.metadata["md5"] = get_md5_hash(self.video_path)
            else:
                self.metadata["md5"] = "N/A (Disabled)"
            logger.info("Metadata extracted successfully.")
            return True
        except Exception as e:
            logger.error(f"Error parsing ffprobe output: {e}")
            return False

    def _generate_cut_points(self) -> List[float]:
        start_pct = 0.05
        end_pct = 0.98
        num_points = self.config.NUM_OF_SEGMENTS
        valid_points = []
        retries = 2
        while len(valid_points) < num_points and retries > 0:
            points = set()
            if start_pct not in self.config.BLACKLISTED_CUT_POINTS:
                points.add(round(start_pct, 3))
            if end_pct not in self.config.BLACKLISTED_CUT_POINTS:
                points.add(round(end_pct, 3))
            if len(points) < 2 and num_points >= 2:
                logger.warning(f"Start/End points blacklisted, adjusting...")
                start_pct += 0.01
                end_pct -= 0.01
                if start_pct >= end_pct:
                    logger.error("Cannot generate cut points range.")
                    return []
                retries -= 1
                continue
            current_start = min(points)
            current_end = max(points)
            num_inner_points = num_points - len(points)
            if num_inner_points > 0:
                if current_end == current_start:
                    logger.error("Start and end points identical.")
                    return []
                step = (current_end - current_start) / (num_inner_points + 1)
                for i in range(1, num_inner_points + 1):
                    point = round(current_start + step * i, 3)
                    point = max(current_start + 0.001, min(current_end - 0.001, point))
                    if point not in self.config.BLACKLISTED_CUT_POINTS:
                        points.add(point)
            if len(points) < num_points:
                logger.warning(f"Generated {len(points)}/{num_points} points. Retrying...")
                start_pct += 0.005
                end_pct -= 0.005
                if start_pct >= end_pct:
                    logger.error("Range collapsed.")
                    return []
                retries -= 1
                continue
            valid_points = sorted(list(points))
            break
        if len(valid_points) < num_points:
            logger.error(f"Failed to generate {num_points} cut points.")
            return []
        if self.config.PRINT_CUT_POINTS or self.config.CONFIRM_CUT_POINTS_REQUIRED:
            logger.info("Generated cut points:")
            for i, pct in enumerate(valid_points):
                time_sec = pct * self.metadata["duration"]
                logger.info(f"  Segment {i+1}: {pct:.3f} ({format_duration(time_sec)})")
        if self.config.CONFIRM_CUT_POINTS_REQUIRED:
            sleep(0.5)
            try:
                confirmation = input("Use these cut points? (yes/no): ").strip().lower()
            except EOFError:
                logger.warning("Cannot prompt for input. Assuming NO.")
                confirmation = "no"
            if confirmation not in ["yes", "y"]:
                logger.info("Cut points rejected. Aborting.")
                return []
        return valid_points

    def _get_vf_filter(self) -> str:
        if self.is_vertical:
            return "scale=480:270:force_original_aspect_ratio=decrease,pad=480:270:(ow-iw)/2:(oh-ih)/2" if self.config.ADD_BLACK_BARS else "scale=270:480"
        else:
            return "scale=480:270"

    def _verify_segment(self, segment_path: Path) -> bool:
        if not segment_path.exists():
            logger.error(f"Segment file missing: {segment_path.name}")
            return False
        file_size = segment_path.stat().st_size
        if file_size < 1024:
            logger.warning(f"Segment file too small ({file_size} bytes): {segment_path.name}")
            return False
        cmd_verify = (f'ffprobe -v error -select_streams v:0 -show_entries format=duration '
                    f'-of default=noprint_wrappers=1:nokey=1 "{segment_path}"')
        stdout, stderr, exit_code = run_command(cmd_verify)
        if exit_code != 0:
            logger.error(f"ffprobe verification failed for {segment_path.name}: {stderr}")
            return False
        if not stdout or not stdout.strip():
            logger.error(f"ffprobe could not determine duration for {segment_path.name}")
            return False
        try:
            duration = float(stdout.strip())
            if duration <= 0:
                logger.error(f"Non-positive duration ({duration}s) for {segment_path.name}")
                return False
            logger.debug(f"Segment verified: {segment_path.name} (Duration: {duration:.2f}s, Size: {file_size} bytes)")
            return True
        except ValueError:
            logger.error(f"Non-numeric duration '{stdout.strip()}' for {segment_path.name}")
            return False

    def _generate_segments(self) -> Tuple[List[Path], List[Path]]:
        valid_segment_paths = []
        timestamped_paths_for_sheet = []
        vf_filter = self._get_vf_filter()
        total_segments_requested = len(self.cut_points_sec)
        segments_generated = 0
        for i, start_sec in enumerate(self.cut_points_sec):
            segment_index = i + 1
            logger.debug(f"Processing segment {segment_index}/{total_segments_requested} at {start_sec:.3f}s")
            if start_sec >= self.metadata["duration"]:
                logger.warning(f"Cut point {start_sec:.3f}s beyond duration ({self.metadata['duration']:.1f}s). Skipping segment {segment_index}.")
                continue
            cut_duration = min(self.config.SEGMENT_DURATION, self.metadata["duration"] - start_sec)
            if cut_duration <= 0.01:
                logger.warning(f"Duration too small ({cut_duration:.3f}s) for segment {segment_index}. Skipping.")
                continue
            start_time_td = timedelta(seconds=start_sec)
            start_time_ss = f"{int(start_time_td.total_seconds() // 3600):02d}:{int(start_time_td.seconds // 60 % 60):02d}:{int(start_time_td.seconds % 60):02d}.{start_time_td.microseconds:06d}"
            start_time_fn = format_duration(start_sec).replace(":", ".")
            segment_filename = f"{self.base_filename}_start-{start_time_fn}_seg-{segment_index}.mp4"
            segment_path = self.temp_dir / segment_filename
            ffmpeg_cmd = (
                f'ffmpeg -hide_banner -loglevel error -ss {start_time_ss} -i "{self.video_path}" -t {cut_duration:.3f} '
                f'-vf "{vf_filter}" -map 0:v:0 -c:v libx264 -crf 23 -preset medium -an -sn -dn '
                f'-map_metadata -1 -map_chapters -1 -y "{segment_path}"'
            )
            logger.debug(f"Running ffmpeg for segment {segment_index}: {ffmpeg_cmd}")
            _, stderr, exit_code = run_command(ffmpeg_cmd)
            if exit_code == 0 and self._verify_segment(segment_path):
                logger.debug(f"Generated segment {segment_index}: {segment_path.name}")
                segments_generated += 1
                final_segment_path_for_preview = segment_path
                path_for_mode2_sheet = segment_path
                if self.config.TIMESTAMPS_MODE in [1, 2]:
                    overlay_path = self._overlay_timestamp(segment_path, start_sec)
                    if overlay_path:
                        if self.config.TIMESTAMPS_MODE == 1:
                            final_segment_path_for_preview = overlay_path
                        path_for_mode2_sheet = overlay_path
                    else:
                        logger.warning(f"Failed timestamp overlay for segment {segment_index}. Using original segment.")
                valid_segment_paths.append(final_segment_path_for_preview)
                if self.config.TIMESTAMPS_MODE == 2:
                    timestamped_paths_for_sheet.append(path_for_mode2_sheet)
            else:
                logger.error(f"Failed to generate segment {segment_index}: {stderr}")
                segment_path.unlink(missing_ok=True)
                ts_path = segment_path.with_name(f"ts_{segment_path.name}")
                ts_path.unlink(missing_ok=True)
        logger.info(f"Generated {segments_generated}/{total_segments_requested} segments.")
        if segments_generated == 0:
            logger.error("No segments generated successfully.")
        return valid_segment_paths, timestamped_paths_for_sheet

    def _overlay_timestamp(self, segment_path: Path, start_sec: float) -> Optional[Path]:
        timestamp_text = format_duration(start_sec).replace(":", r"\:")
        output_path = segment_path.with_name(f"ts_{segment_path.name}")
        font_path_obj = Path(self.config.FONT_PATH)
        try:
            font_path_resolved = str(font_path_obj.resolve())
            font_path_ffmpeg = f"fontfile='{font_path_resolved.replace('\\', '/').replace(':', '\\:')}':"
        except Exception as e:
            logger.error(f"Font path error '{self.config.FONT_PATH}': {e}")
            return None
        ffmpeg_cmd = (
            f'ffmpeg -hide_banner -loglevel error -i "{segment_path}" '
            f'-vf "drawtext=text=\'{timestamp_text}\':{font_path_ffmpeg}'
            f'fontcolor=white:fontsize=20:x=(w-text_w)-10:y=10:box=1:boxcolor=black@0.4:boxborderw=5" '
            f'-c:v libx264 -crf 23 -preset medium -an -y "{output_path}"'
        )
        _, stderr, exit_code = run_command(ffmpeg_cmd)
        if exit_code == 0 and output_path.exists():
            logger.debug(f"Timestamp overlay created: {output_path.name}")
            return output_path
        logger.error(f"Failed timestamp overlay: {stderr}")
        return None

    def _write_concat_file(self, segment_paths: List[Path], output_filename: str) -> Path:
        concat_path = self.temp_dir / output_filename
        with concat_path.open("w", encoding='utf-8') as f:
            for path in segment_paths:
                f.write(f"file '{path.resolve().as_posix()}'\n")
        logger.debug(f"Concat file written: {concat_path}")
        return concat_path

    def _run_ffmpeg_concat(self, concat_file_path: Path, output_video_path: Path) -> bool:
        concat_cmd = f'ffmpeg -hide_banner -loglevel error -f concat -safe 0 -i "{concat_file_path}" -c copy -y "{output_video_path}"'
        _, stderr, exit_code = run_command(concat_cmd)
        if exit_code != 0 or not output_video_path.exists():
            logger.error(f"Concat failed: {stderr}")
            return False
        logger.debug(f"Concat video created: {output_video_path}")
        return True

    def _generate_webp_preview(self) -> bool:
        logger.info("Generating WebP preview...")
        if not self.segment_files:
            logger.error("No segments available for WebP preview.")
            return False
        concat_file = self._write_concat_file(self.segment_files, "concat_list_webp_preview.txt")
        concat_video = self.temp_dir / f"{self.base_filename}_concat_webp_preview.mp4"
        if not self._run_ffmpeg_concat(concat_file, concat_video):
            return False
        output_webp = self.output_dir / f"{self.base_filename}_preview.webp"
        scale_filter = "scale=480:-2" if not self.is_vertical or self.config.ADD_BLACK_BARS else "scale=-2:480"
        webp_cmd = (f'ffmpeg -hide_banner -loglevel error -y -i "{concat_video}" '
                    f'-vf "fps=24,{scale_filter}:flags=lanczos" '
                    f'-c:v libwebp -quality 80 -compression_level 6 -loop 0 -an -vsync 0 "{output_webp}"')
        _, stderr, code = run_command(webp_cmd)
        if code == 0 and output_webp.exists():
            logger.success(f"WebP preview created: {output_webp.name}")
            return True
        logger.error(f"Failed WebP preview: {stderr}")
        return False

    def _create_info_image(self) -> Optional[Path]:
        logger.debug("Creating info image...")
        font_size = 16
        line_padding = 5
        side_margin = 20
        key_value_gap = 15
        key_column_width = 110
        img_width = 1920 if self.config.GRID_WIDTH == 4 and (not self.is_vertical or self.config.ADD_BLACK_BARS) else 1440
        try:
            font = ImageFont.truetype(self.config.FONT_PATH, font_size)
        except Exception:
            logger.warning(f"Font '{self.config.FONT_PATH}' not found. Using default.")
            font = ImageFont.load_default()
        value_column_width = img_width - key_column_width - key_value_gap - (2 * side_margin)
        total_height = 10
        prepared_lines = []
        metadata_rows = [
            ("File", self.metadata.get("filename", "N/A")),
            ("Title", self.metadata.get("title", "N/A")),
            ("Size", self.metadata.get("size_mb", "N/A")),
            ("Resolution", self.metadata.get("resolution", "N/A")),
            ("Duration", format_duration(self.metadata.get("duration", 0))),
            ("Video", self.metadata.get("video_details", "N/A")),
            ("Audio", self.metadata.get("audio_details", "N/A")),
            ("MD5", self.metadata.get("md5", "N/A")),
        ]
        for key, value in metadata_rows:
            if not isinstance(value, str):
                value = "N/A"
            wrapped_value_lines = []
            current_line = ""
            value_words = value.split(' ')
            for word in value_words:
                test_line = current_line + (" " if current_line else "") + word
                try:
                    bbox = font.getbbox(test_line)
                    line_width = bbox[2] - bbox[0]
                except AttributeError:
                    line_width = font.getsize(test_line)[0]
                if line_width <= value_column_width:
                    current_line = test_line
                else:
                    if current_line:
                        wrapped_value_lines.append(current_line)
                    if len(word) > int(value_column_width / (font_size * 0.5)):
                        break_point = int(value_column_width / (font_size * 0.5))
                        wrapped_value_lines.append(word[:break_point])
                        current_line = word[break_point:]
                    else:
                        current_line = word
            if current_line:
                wrapped_value_lines.append(current_line)
            if not wrapped_value_lines:
                wrapped_value_lines = ["N/A"]
            key_text = f"{key}:" if key else ""
            prepared_lines.append((key_text, wrapped_value_lines))
            try:
                line_bbox = font.getbbox("Xp")
                single_line_height = line_bbox[3] - line_bbox[1] + line_padding
            except AttributeError:
                single_line_height = font.getsize("Xp")[1] + line_padding
            total_height += len(wrapped_value_lines) * single_line_height
        total_height += 10
        img = Image.new("RGB", (img_width, total_height), color=(0, 0, 0))
        draw = ImageDraw.Draw(img)
        y = 10
        key_x = side_margin
        value_x = side_margin + key_column_width + key_value_gap
        text_color = (230, 230, 230)
        for key_text, value_lines in prepared_lines:
            if key_text:
                draw.text((key_x, y), key_text, font=font, fill=text_color)
            current_line_y = y
            for line in value_lines:
                draw.text((value_x, current_line_y), line, font=font, fill=text_color)
                try:
                    line_bbox = font.getbbox("Xp")
                    single_line_height = line_bbox[3] - line_bbox[1] + line_padding
                except AttributeError:
                    single_line_height = font.getsize("Xp")[1] + line_padding
                current_line_y += single_line_height
            y = current_line_y
        output_path = self.temp_dir / f"{self.base_filename}_info.png"
        try:
            img.save(output_path)
            logger.debug(f"Info image created: {output_path.name}")
            return output_path
        except Exception as e:
            logger.error(f"Error saving info image: {e}")
            return None

    def _stack_videos(self, input_paths: List[Path], output_path: Path, axis: str = 'h') -> bool:
        if not input_paths:
            logger.error(f"No input paths provided for {axis}-stacking.")
            return False
        stack_func = "hstack" if axis == 'h' else "vstack"
        inputs_str = ' '.join([f'-i "{p}"' for p in input_paths])
        filter_inputs = ''.join([f'[{i}:v]' for i in range(len(input_paths))])
        filter_complex = f'"{filter_inputs}{stack_func}=inputs={len(input_paths)}[v]"'
        map_str = '-map "[v]"'
        fps_output = f"-r {self.metadata.get('fps', 24)}"
        command = f'ffmpeg -hide_banner -loglevel error {inputs_str} -filter_complex {filter_complex} {map_str} {fps_output} -y "{output_path}"'
        logger.debug(f"Stacking ({axis}) command: {command}")
        _, stderr, exit_code = run_command(command)
        if exit_code != 0:
            logger.error(f"Stacking ({axis}) failed: {stderr}")
            return False
        logger.debug(f"Stacked ({axis}): {output_path.name}")
        return True

    def _generate_webp_preview_sheet(self) -> bool:
        logger.info("Generating animated WebP preview sheet...")
        sheet_segments = self.timestamped_segment_files if self.config.TIMESTAMPS_MODE == 2 else self.segment_files
        if not sheet_segments:
            logger.error("No segments available for WebP preview sheet.")
            return False
        logger.debug(f"Using {len(sheet_segments)} segments for WebP sheet")
        info_image_path = self._create_info_image()
        if not info_image_path:
            logger.error("Failed to create info image for WebP sheet.")
            return False
        info_video_path = self.temp_dir / f"{self.base_filename}_info_video.mp4"
        cmd_info_vid = (f'ffmpeg -hide_banner -loglevel error -loop 1 -framerate {self.metadata.get("fps", 24)} '
                        f'-t {self.config.SEGMENT_DURATION} -i "{info_image_path}" '
                        f'-c:v libx264 -pix_fmt yuv420p -y "{info_video_path}"')
        _, stderr, code = run_command(cmd_info_vid)
        if code != 0:
            logger.error(f"Failed to create info video: {stderr}")
            return False
        grid = self.config.GRID_WIDTH
        h_stacked_videos = []
        for i in range(0, len(sheet_segments), grid):
            group = sheet_segments[i: i + grid]
            if not group:
                logger.warning(f"Empty group at index {i} for WebP sheet.")
                continue
            if len(group) != grid:
                logger.error(f"Incorrect segments ({len(group)}) for grid {grid} at index {i}. Expected {grid}.")
                return False
            h_stack_output = self.temp_dir / f"hstacked_{i//grid + 1}.mp4"
            if not self._stack_videos(group, h_stack_output, axis='h'):
                logger.error(f"Horizontal stacking failed for group {i//grid + 1}.")
                return False
            h_stacked_videos.append(h_stack_output)
        if not h_stacked_videos:
            logger.error("No horizontally stacked videos generated for WebP sheet.")
            return False
        final_sheet_video_path = self.temp_dir / f"{self.base_filename}_final_sheet_raw.mp4"
        all_v_inputs = [info_video_path] + h_stacked_videos
        if not self._stack_videos(all_v_inputs, final_sheet_video_path, axis='v'):
            logger.error("Vertical stacking failed for WebP sheet.")
            return False
        final_processed_sheet_path = final_sheet_video_path
        if self.config.GRID_WIDTH == 4 and (not self.is_vertical or self.config.ADD_BLACK_BARS):
            downscaled_path = self.temp_dir / f"{self.base_filename}_final_sheet_downscaled.mp4"
            scale_filter = "scale=1280:-2"
            cmd_downscale = f'ffmpeg -hide_banner -loglevel error -i "{final_sheet_video_path}" -vf "{scale_filter}" -c:v libx264 -crf 22 -preset medium -y "{downscaled_path}"'
            _, stderr, code = run_command(cmd_downscale)
            if code == 0:
                logger.info("Downscaled grid=4 sheet video.")
                try:
                    og_path = final_sheet_video_path.with_name(f"{final_sheet_video_path.stem}_og.mp4")
                    if og_path.exists():
                        og_path.unlink()
                    final_sheet_video_path.rename(og_path)
                    downscaled_path.rename(final_sheet_video_path)
                    final_processed_sheet_path = final_sheet_video_path
                except OSError as e:
                    logger.error(f"Error renaming sheet videos: {e}")
            else:
                logger.warning(f"Downscaling failed: {stderr}")
        output_webp = self.output_dir / f"{self.base_filename}_preview_sheet.webp"
        cmd_webp = (f'ffmpeg -hide_banner -loglevel error -y -i "{final_processed_sheet_path}" -vf "fps=24,scale=iw:ih:flags=lanczos" '
                    f'-c:v libwebp -quality 75 -lossless 0 -loop 0 -an -vsync 0 "{output_webp}"')
        _, stderr, code = run_command(cmd_webp)
        if code == 0 and output_webp.exists():
            logger.success(f"WebP preview sheet created: {output_webp.name}")
            return True
        logger.error(f"Failed to create WebP preview sheet: {stderr}")
        return False

    def _extract_segment_frames(self) -> List[Path]:
        logger.info("Extracting frames for image preview sheet...")
        extracted_frames = []
        segments_to_frame = self.segment_files
        if not segments_to_frame:
            logger.error("No segments available for frame extraction.")
            return []
        mid_point_time = self.config.SEGMENT_DURATION / 2.0
        fallback_seek_time = 0.1
        for i, segment_path in enumerate(segments_to_frame):
            frame_filename = segment_path.with_name(f"frame_{segment_path.stem}.png")
            frame_path = self.temp_dir / frame_filename
            frame_extracted = False
            logger.debug(f"Extracting frame (midpoint {mid_point_time:.3f}s) for: {segment_path.name}")
            cmd_frame_mid = (f'ffmpeg -hide_banner -loglevel error -copyts -ss {mid_point_time:.3f} -i "{segment_path}" '
                            f'-vf "select=eq(n\\,0)" -vframes 1 -q:v 2 "{frame_path}" -y')
            _, stderr_mid, code_mid = run_command(cmd_frame_mid)
            if code_mid == 0 and frame_path.exists() and frame_path.stat().st_size > 100:
                frame_extracted = True
                logger.debug(f"Extracted frame {i+1} (midpoint): {frame_path.name}")
            else:
                logger.warning(f"Midpoint frame extraction failed: {stderr_mid}")
                frame_path.unlink(missing_ok=True)
                logger.debug(f"Attempting fallback ({fallback_seek_time:.3f}s) for: {segment_path.name}")
                cmd_frame_fallback = (f'ffmpeg -hide_banner -loglevel error -copyts -ss {fallback_seek_time:.3f} -i "{segment_path}" '
                                    f'-vf "select=eq(n\\,0)" -vframes 1 -q:v 2 "{frame_path}" -y')
                _, stderr_fallback, code_fallback = run_command(cmd_frame_fallback)
                if code_fallback == 0 and frame_path.exists() and frame_path.stat().st_size > 100:
                    frame_extracted = True
                    logger.debug(f"Extracted frame {i+1} (fallback): {frame_path.name}")
                else:
                    logger.error(f"Fallback frame extraction failed: {stderr_fallback}")
                    frame_path.unlink(missing_ok=True)
            if frame_extracted:
                extracted_frames.append(frame_path)
            else:
                logger.error(f"Could not extract frame for: {segment_path.name}")
        if not extracted_frames:
            logger.error("Failed to extract any frames for image sheet.")
        else:
            logger.info(f"Extracted {len(extracted_frames)} frames for image sheet.")
        return extracted_frames

    def _generate_image_preview_sheet(self) -> bool:
        logger.info("Generating static image preview sheet...")
        if not self.segment_frame_files:
            logger.error("No frames extracted for image preview sheet.")
            return False
        info_image_path = self._create_info_image()
        if not info_image_path:
            logger.error("Failed to create info image for image sheet.")
            return False
        sheet_created = False
        try:
            info_img = Image.open(info_image_path)
            info_w, info_h = info_img.size
            logger.debug(f"Info image dimensions: {info_w}x{info_h}")
            try:
                first_frame_img = Image.open(self.segment_frame_files[0])
                frame_w, frame_h = first_frame_img.size
                first_frame_img.close()
            except Exception as e:
                logger.error(f"Failed to open first frame: {e}")
                info_img.close()
                return False
            grid = self.config.GRID_WIDTH
            num_frames_extracted = len(self.segment_frame_files)
            num_rows = (num_frames_extracted + grid - 1) // grid
            sheet_width = info_w
            sheet_height = info_h + (num_rows * frame_h)
            logger.debug(f"Image sheet dimensions: {sheet_width}x{sheet_height}")
            final_sheet_img = Image.new("RGB", (sheet_width, sheet_height), color=(40, 40, 40))
            final_sheet_img.paste(info_img, (0, 0))
            for i, frame_path in enumerate(self.segment_frame_files):
                paste_x = (i % grid) * frame_w
                paste_y = info_h + (i // grid) * frame_h
                try:
                    with Image.open(frame_path) as frame_img:
                        final_sheet_img.paste(frame_img, (paste_x, paste_y))
                    logger.debug(f"Pasted frame {i+1}: {frame_path.name}")
                except Exception as e:
                    logger.error(f"Failed to paste frame {frame_path.name}: {e}")
                    try:
                        draw = ImageDraw.Draw(final_sheet_img)
                        draw.rectangle([paste_x, paste_y, paste_x + frame_w, paste_y + frame_h], fill="darkred", outline="red")
                        err_font = ImageFont.load_default()
                        draw.text((paste_x + 5, paste_y + 5), f"Error\nFrame {i+1}", fill="white", font=err_font)
                    except Exception as draw_e:
                        logger.error(f"Failed to draw placeholder: {draw_e}")
            output_suffix = f".{self.config.IMAGE_SHEET_FORMAT.lower()}"
            output_path = self.output_dir / f"{self.base_filename}_preview_sheet{output_suffix}"
            save_format = self.config.IMAGE_SHEET_FORMAT.upper()
            save_params = {}
            if save_format in ["JPG", "JPEG"]:
                save_format = "JPEG"
                save_params['quality'] = 85
            elif save_format == "PNG":
                save_params['optimize'] = True
            final_sheet_img.save(output_path, format=save_format, **save_params)
            logger.success(f"Image preview sheet created: {output_path.name}")
            sheet_created = True
        except Exception as e:
            logger.exception(f"Failed to generate image preview sheet: {e}")
        finally:
            if 'info_img' in locals():
                info_img.close()
        return sheet_created

# --- Mode Selection Popup ---
def select_mode():
    root = tk.Tk()
    root.title("Select Processing Mode")
    root.geometry("300x200")
    root.eval('tk::PlaceWindow . center')

    selected_mode = tk.StringVar(value="both")

    tk.Label(root, text="Choose mode:", font=("Arial", 12)).pack(pady=10)
    tk.Radiobutton(root, text="Metadata Extraction", variable=selected_mode, value="metadata", font=("Arial", 10)).pack(anchor="w", padx=20)
    tk.Radiobutton(root, text="Preview Generation", variable=selected_mode, value="preview", font=("Arial", 10)).pack(anchor="w", padx=20)
    tk.Radiobutton(root, text="Both", variable=selected_mode, value="both", font=("Arial", 10)).pack(anchor="w", padx=20)

    def on_submit():
        root.quit()

    tk.Button(root, text="Start", command=on_submit, font=("Arial", 10)).pack(pady=20)

    root.mainloop()
    mode = selected_mode.get()
    root.destroy()
    return mode

# --- Folder Selection Popup ---
def select_folder():
    root = tk.Tk()
    root.withdraw()
    folder_path = filedialog.askdirectory(title="Select Input Folder")
    root.destroy()
    if not folder_path:
        logger.error("No folder selected. Exiting.")
        sys.exit(1)
    return folder_path

# --- Main Execution ---
def main():
    start_time = datetime.now()
    log_dir = Path.cwd() / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file_name = f"VideoProcessor_{start_time:%Y%m%d_%H%M%S}.log"
    log_file_path = log_dir / log_file_name
    logger.remove()
    logger.add(sys.stderr, level="INFO", format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>")
    logger.add(log_file_path, level="DEBUG", rotation="10 MB", retention="7 days", encoding='utf-8')
    logger.info("Starting Video Processor Script")

    Config.INPUT_FOLDER = select_folder()
    logger.info(f"Selected input folder: {Config.INPUT_FOLDER}")

    if not Config.validate():
        logger.error("Configuration validation failed.")
        sys.exit(1)

    mode = select_mode()
    logger.info(f"Selected mode: {mode}")

    input_folder = Path(Config.INPUT_FOLDER)
    excluded_lower = [f.lower() for f in Config.EXCLUDED_FILES if f]
    video_files_found = []
    try:
        logger.info(f"Scanning folder: {input_folder}")
        for item in input_folder.iterdir():
            if item.is_file() and item.suffix.lower() in Config.VALID_VIDEO_EXTENSIONS:
                if item.name.lower() not in excluded_lower:
                    video_files_found.append(item)
                else:
                    logger.info(f"Skipping excluded file: {item.name}")
    except Exception as scan_e:
        logger.error(f"Error scanning folder: {scan_e}")
        sys.exit(1)

    if not video_files_found:
        logger.warning(f"No valid video files found in '{input_folder}'.")
        return

    logger.info(f"Found {len(video_files_found)} video files to process.")
    processed_count = 0
    success_count = 0

    if mode in ["metadata", "both"]:
        logger.info("--- Starting Metadata Extraction ---")
        meta_processed, meta_successes = process_metadata_extraction(video_files_found)
        processed_count += meta_processed
        success_count += meta_successes
        logger.info(f"Metadata processed: {meta_processed}, Successes: {meta_successes}")

    if mode in ["preview", "both"]:
        logger.info("--- Starting Preview Generation ---")
        for video_file in video_files_found:
            processed_count += 1
            logger.info(f"--- [{processed_count}/{len(video_files_found)}] Starting: {video_file.name} ---")
            try:
                processor = VideoProcessor(video_file, Config)
                if processor.run():
                    success_count += 1
            except KeyboardInterrupt:
                logger.warning("Processing interrupted by user.")
                break
            except Exception as e:
                logger.exception(f"Error processing {video_file.name}: {e}")

    end_time = datetime.now()
    logger.info(f"--- Processing complete ---")
    logger.info(f"Total videos found: {len(video_files_found)}")
    logger.info(f"Total processing attempts: {processed_count}")
    logger.info(f"Successful operations: {success_count}")
    logger.info(f"Total time taken: {end_time - start_time}")
    logger.info(f"Log file saved to: {log_file_path.resolve()}")

if __name__ == "__main__":
    main()