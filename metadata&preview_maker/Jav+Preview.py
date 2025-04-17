#!/usr/bin/env python3

import os
import re
import requests
from bs4 import BeautifulSoup, NavigableString
from urllib.parse import urljoin, urlparse
import sys
import time
import subprocess
import shutil
import random
import unicodedata
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any
import tkinter as tk
from tkinter import messagebox, ttk, filedialog

# --- Dependency Check/Installation ---
try:
    from loguru import logger
except ImportError:
    print("Loguru not found, attempting to install...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "loguru"])
    from loguru import logger
    print("Loguru installed successfully.")

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("Pillow (PIL) not found, attempting to install...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow"])
    from PIL import Image, ImageDraw, ImageFont
    print("Pillow installed successfully.")

# --- Logging Setup ---
start_time = datetime.now()
log_dir = Path.cwd() / "logs"
log_dir.mkdir(exist_ok=True)
log_file_name = f"MediaProcessor_{start_time:%Y%m%d_%H%M%S}.log"
log_file_path = log_dir / log_file_name

logger.remove()
logger.add(sys.stderr, level="INFO", format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>")
logger.add(log_file_path, level="DEBUG", rotation="10 MB", retention="7 days", encoding='utf-8',
           format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}")

# --- Configuration ---
class Config:
    VIDEO_DIR = "/home/user/Videos/"  # Default, overridden by popup
    PREVIEW_INPUT_FOLDER = "/home/user/Videos/"  # Default, overridden by popup
    PREVIEW_OUTPUT_PATH: Optional[str] = None  # Ignored for previews; kept for compatibility

    # Metadata Config
    BASE_URL = "https://www.javdatabase.com/"
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': BASE_URL,
    }
    IMG_HEADERS = HEADERS.copy()
    IMG_HEADERS['Accept'] = 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8'
    JAV_CODE_REGEX = re.compile(r'([A-Za-z]{2,5})-?(\d{2,5})', re.IGNORECASE)

    # Preview Config
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
    FONT_PATH = "/usr/share/fonts/liberation/LiberationSans-Regular.ttf"
    VALID_VIDEO_EXTENSIONS = (".mp4", ".mkv", ".m2ts", ".m4v", ".avi", ".ts", ".wmv", ".mov")

    @classmethod
    def validate(cls):
        for dir_path, name in [
            (cls.VIDEO_DIR, "Video directory"),
            (cls.PREVIEW_INPUT_FOLDER, "Preview input folder")
        ]:
            input_path = Path(dir_path)
            if not input_path.is_dir():
                logger.error(f"{name} not found: {dir_path}")
                return False
            if not os.access(dir_path, os.W_OK):
                logger.error(f"No write permissions for {name}: {dir_path}")
                return False
        return True

# --- Utility Functions ---
def run_command(command: str, cwd: Optional[str] = None) -> Tuple[str, str, int]:
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, encoding='utf-8', errors='surrogateescape', cwd=cwd)
        return result.stdout.strip(), result.stderr.strip(), result.returncode
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

# --- Metadata Scraper ---
class MetadataScraper:
    def __init__(self, config: Config):
        self.config = config

    def extract_jav_code(self, filename):
        name_part = os.path.splitext(filename)[0]
        match = self.config.JAV_CODE_REGEX.search(name_part)
        if match:
            prefix = match.group(1).upper()
            number = match.group(2)
            return f"{prefix}-{number}"
        return None

    def download_image(self, url, filepath, referer=None):
        try:
            dl_headers = self.config.IMG_HEADERS.copy()
            if referer:
                dl_headers['Referer'] = referer
            logger.info(f"Attempting to download image: {url}")
            time.sleep(0.3)
            response = requests.get(url, headers=dl_headers, stream=True, timeout=45)
            response.raise_for_status()
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            logger.info(f"Successfully downloaded: {filepath}")
            os.chmod(filepath, 0o664)
            return True
        except Exception as e:
            logger.error(f"Failed to download {url}: {e}")
            if os.path.exists(filepath):
                os.remove(filepath)
            return False

    def create_metadata_file(self, filepath, data):
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"[title]\n{data.get('title_long', 'N/A')}\n\n")
                f.write("[details]\n")
                for key in ['id', 'content_id', 'release_date', 'runtime', 'studio', 'director']:
                    f.write(f"{key.capitalize()}: {data.get(key, 'N/A')}\n")
                f.write("\n[cast]\n")
                f.write('\n'.join(data.get('cast', ['N/A'])) + '\n\n')
                f.write("[plot]\n")
                f.write(data.get('plot', 'N/A') + '\n\n')
                f.write("[tags]\n")
                f.write(', '.join(data.get('genres', ['N/A'])) + '\n\n')
                f.write("[cover]\n")
                f.write(f"{data.get('cover_filename', 'N/A')}\n\n")
                f.write("[screens]\n")
                f.write('\n'.join(f"[img]{s}[/img]" for s in data.get('screenshot_filenames', [])) + '\n')
            logger.info(f"Metadata file created: {filepath}")
            os.chmod(filepath, 0o664)
        except Exception as e:
            logger.error(f"Failed to write metadata file {filepath}: {e}")

    def process_video(self, filepath):
        filename = os.path.basename(filepath)
        jav_code = self.extract_jav_code(filename)
        if not jav_code:
            logger.warning(f"Could not extract JAV code from: {filename}")
            return

        logger.info(f"--- Processing: {filename} (Code: {jav_code}) ---")
        jav_code_lower = jav_code.lower()
        output_dir = os.path.join(self.config.VIDEO_DIR, jav_code_lower)
        metadata_filepath = os.path.join(output_dir, f"{jav_code_lower}.txt")
        cover_filename_base = f"{jav_code_lower}_cover"

        if os.path.exists(metadata_filepath):
            logger.info(f"Metadata file '{metadata_filepath}' already exists. Skipping.")
            return

        movie_url = urljoin(self.config.BASE_URL, f"movies/{jav_code_lower}/")
        try:
            os.makedirs(output_dir, exist_ok=True)
            os.chmod(output_dir, 0o775)
        except Exception as e:
            logger.error(f"Failed to create directory {output_dir}: {e}")
            return

        try:
            response = requests.get(movie_url, headers=self.config.HEADERS, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'lxml')
            if not soup.title or "Page not found" in soup.title.string or "Nothing Found" in soup.text:
                logger.error(f"Movie page not found for {jav_code} at {movie_url}")
                return
        except Exception as e:
            logger.error(f"Failed to fetch page {movie_url}: {e}")
            return

        metadata = {'id': jav_code, 'cast': [], 'genres': [], 'plot': 'N/A'}
        try:
            title_h1 = soup.select_one('header.entry-header h1')
            metadata['title_long'] = title_h1.get_text(strip=True) if title_h1 else jav_code

            details_container = soup.select_one('div.entry-content div.row')
            if details_container:
                details_column = details_container.select_one('div.col-md-10, div.col-lg-10, div.col-8')
                if details_column:
                    for p in details_column.find_all('p', class_='mb-1', recursive=False):
                        strong_tag = p.find('b')
                        if not strong_tag:
                            continue
                        label = strong_tag.get_text(strip=True).replace(':', '').strip()
                        links = p.find_all('a')
                        link_texts = [a.get_text(strip=True) for a in links if a.get_text(strip=True)]
                        value_text = ''.join(node.strip() + ' ' for node in strong_tag.find_next_siblings(string=True)).strip()

                        if label == "Content ID":
                            metadata['content_id'] = value_text or 'N/A'
                        elif label == "Release Date":
                            metadata['release_date'] = value_text or 'N/A'
                        elif label == "Runtime":
                            metadata['runtime'] = value_text or 'N/A'
                        elif label == "Studio":
                            metadata['studio'] = link_texts[0] if link_texts else (value_text or 'N/A')
                        elif label == "Director":
                            metadata['director'] = link_texts[0] if link_texts else (value_text or 'N/A')
                        elif label == "Genre(s)":
                            metadata['genres'] = sorted(list(set(link_texts))) if link_texts else []
                        elif label == "Idol(s)/Actress(es)":
                            metadata['cast'] = sorted(list(set(link_texts))) if link_texts else []

            if not metadata.get('cast'):
                fallback_cast_links = soup.select('div.entry-content a[href*="/idols/"]')
                metadata['cast'] = sorted(list(set(a.get_text(strip=True) for a in fallback_cast_links if a.get_text(strip=True))))

            plot_heading_regex = re.compile(r'About\s+' + re.escape(jav_code) + r'\s+JAV Movie', re.IGNORECASE)
            plot_heading = soup.find('h4', class_='subhead', string=plot_heading_regex)
            if plot_heading:
                plot_parent_div = plot_heading.parent
                if plot_parent_div:
                    plot_text_parts = []
                    stop_extracting = False
                    for content in plot_parent_div.contents:
                        if stop_extracting:
                            break
                        if content == plot_heading:
                            continue
                        if content.name == 'div' and content.find(id=lambda x: x and x.startswith('post-ratings')):
                            stop_extracting = True
                            break
                        if isinstance(content, NavigableString) and "JAV Database only provides" in content:
                            text_part = content.strip().split("JAV Database only provides")[0].strip()
                            if text_part:
                                plot_text_parts.append(text_part)
                            stop_extracting = True
                            break
                        if content.name == 'p' and "JAV Database only provides" in content.get_text():
                            text_part = content.get_text(strip=True).split("JAV Database only provides")[0].strip()
                            if text_part:
                                plot_text_parts.append(text_part)
                            stop_extracting = True
                            break
                        text_chunk = None
                        if isinstance(content, NavigableString):
                            text_chunk = content.string
                        elif content.name == 'p':
                            text_chunk = content.get_text()
                        if text_chunk:
                            plot_text_parts.append(text_chunk)
                    raw_joined_plot = ' '.join(plot_text_parts).strip()
                    if raw_joined_plot:
                        metadata['plot'] = re.sub(r'\s+', ' ', raw_joined_plot).strip()

            cover_img_tag = soup.select_one('#poster-container img')
            cover_filename = "N/A"
            if cover_img_tag and cover_img_tag.get('src'):
                cover_url = urljoin(movie_url, cover_img_tag['src'])
                cover_ext = os.path.splitext(urlparse(cover_url).path)[1] or '.webp'
                cover_filename = f"{cover_filename_base}{cover_ext}"
                cover_filepath = os.path.join(output_dir, cover_filename)
                existing_cover = any(os.path.exists(os.path.join(output_dir, f"{cover_filename_base}{ext}"))
                                    for ext in ['.webp', '.jpg', '.jpeg', '.png'])
                if not existing_cover:
                    if not self.download_image(cover_url, cover_filepath, referer=movie_url):
                        cover_filename = "N/A (Download Failed)"
                else:
                    cover_filename = next((f"{cover_filename_base}{ext}" for ext in ['.webp', '.jpg', '.jpeg', '.png']
                                          if os.path.exists(os.path.join(output_dir, f"{cover_filename_base}{ext}"))), "N/A")
            metadata['cover_filename'] = cover_filename

            screenshot_filenames = []
            count = 0
            screenshot_heading = soup.find('h4', class_='subhead', string=re.compile(f'{jav_code}.* Images', re.IGNORECASE))
            if screenshot_heading:
                screenshot_container = screenshot_heading.find_next_sibling('div', class_='container')
                if screenshot_container:
                    screenshot_links = screenshot_container.select('div.row.g-3 a[data-image-href]')
                    for i, link_tag in enumerate(screenshot_links):
                        full_size_url = link_tag.get('data-image-href')
                        if not full_size_url:
                            continue
                        ss_ext = os.path.splitext(urlparse(full_size_url).path)[1] or '.jpg'
                        screenshot_filename_base = f"{jav_code_lower}_screenshot_{count + 1:02d}"
                        screenshot_filename = f"{screenshot_filename_base}{ss_ext}"
                        screenshot_filepath = os.path.join(output_dir, screenshot_filename)
                        existing_screenshot = any(os.path.exists(os.path.join(output_dir, f"{screenshot_filename_base}{ext}"))
                                                 for ext in ['.jpg', '.jpeg', '.png', '.webp'])
                        if not existing_screenshot:
                            if self.download_image(full_size_url, screenshot_filepath, referer=movie_url):
                                screenshot_filenames.append(screenshot_filename)
                                count += 1
                        else:
                            screenshot_filename = next((f"{screenshot_filename_base}{ext}" for ext in ['.jpg', '.jpeg', '.png', '.webp']
                                                       if os.path.exists(os.path.join(output_dir, f"{screenshot_filename_base}{ext}"))), None)
                            if screenshot_filename:
                                screenshot_filenames.append(screenshot_filename)
                                count += 1
            metadata['screenshot_filenames'] = screenshot_filenames

            if metadata.get('title_long', jav_code) != jav_code or metadata.get('cast') or metadata.get('plot', 'N/A') != 'N/A':
                self.create_metadata_file(metadata_filepath, metadata)
            else:
                logger.warning(f"Failed to scrape significant metadata for {jav_code}. Not creating text file.")
                if not metadata.get('cover_filename', 'N/A').startswith(jav_code_lower) and not metadata.get('screenshot_filenames'):
                    try:
                        os.rmdir(output_dir)
                    except OSError:
                        pass

        except Exception as e:
            logger.exception(f"Critical error processing {jav_code}: {e}")
            if not os.path.exists(metadata_filepath):
                try:
                    if not any(f.startswith(jav_code_lower) for f in os.listdir(output_dir)):
                        os.rmdir(output_dir)
                except Exception:
                    pass

    def run(self):
        if not os.path.isdir(self.config.VIDEO_DIR):
            logger.error(f"Video directory not found: {self.config.VIDEO_DIR}")
            return False
        video_files = [f for f in os.listdir(self.config.VIDEO_DIR)
                       if os.path.isfile(os.path.join(self.config.VIDEO_DIR, f)) and
                       f.lower().endswith(('.mp4', '.mkv', '.avi', '.wmv', '.mov'))]
        if not video_files:
            logger.warning(f"No video files found in {self.config.VIDEO_DIR}")
            return False
        found_videos = len(video_files)
        processed_videos = 0
        skipped_videos = 0
        logger.info(f"Found {found_videos} video files.")
        for item in video_files:
            jav_code = self.extract_jav_code(item)
            if jav_code:
                metadata_path = os.path.join(self.config.VIDEO_DIR, jav_code.lower(), f"{jav_code.lower()}.txt")
                if os.path.exists(metadata_path):
                    logger.info(f"Metadata exists for '{item}' ({jav_code}). Skipping.")
                    skipped_videos += 1
                    continue
            processed_videos += 1
            self.process_video(os.path.join(self.config.VIDEO_DIR, item))
        logger.info(f"Metadata processing complete: {found_videos} found, {processed_videos} processed, {skipped_videos} skipped.")
        return True

# --- Video Preview Generator ---
class VideoPreviewGenerator:
    def __init__(self, config: Config):
        self.config = config

    def extract_jav_code(self, filename):
        name_part = os.path.splitext(filename)[0]
        match = self.config.JAV_CODE_REGEX.search(name_part)
        if match:
            prefix = match.group(1).upper()
            number = match.group(2)
            return f"{prefix}-{number}"
        return None

    def run(self):
        input_folder = Path(self.config.PREVIEW_INPUT_FOLDER)
        excluded_lower = [f.lower() for f in self.config.EXCLUDED_FILES if f]
        video_files = []
        try:
            logger.debug(f"Scanning folder: {input_folder}")
            for item in input_folder.iterdir():
                if item.is_file() and item.suffix.lower() in self.config.VALID_VIDEO_EXTENSIONS:
                    if item.name.lower() not in excluded_lower:
                        video_files.append(item)
                        logger.debug(f"Found video file: {item}")
        except Exception as e:
            logger.error(f"Error scanning folder {input_folder}: {e}")
            return False
        if not video_files:
            logger.warning(f"No valid video files found in '{input_folder}'.")
            return False
        logger.info(f"Found {len(video_files)} video files to process.")
        processed_count = 0
        success_count = 0
        for video_file in video_files:
            processed_count += 1
            logger.info(f"--- [{processed_count}/{len(video_files)}] Starting: {video_file.name} ---")
            try:
                jav_code = self.extract_jav_code(video_file.name)
                logger.debug(f"Extracted JAV code: {jav_code} for file: {video_file.name}")
                if not jav_code:
                    logger.warning(f"Could not extract JAV code from: {video_file.name}. Skipping preview and move.")
                    continue
                processor = VideoProcessor(video_file, self.config, jav_code)
                preview_success = processor.run()
                if preview_success:
                    success_count += 1
                    logger.info(f"Preview generation successful for {video_file.name}")
                else:
                    logger.warning(f"Preview generation failed for {video_file.name}, but attempting to move file")
                # Move the original video file to the JAV code folder
                try:
                    target_dir = Path(self.config.VIDEO_DIR) / jav_code.lower()
                    logger.debug(f"Target directory: {target_dir}")
                    target_dir.mkdir(parents=True, exist_ok=True)
                    target_path = target_dir / video_file.name
                    logger.debug(f"Target path: {target_path}")
                    logger.debug(f"Source file exists: {video_file.exists()}")
                    logger.debug(f"Target path exists: {target_path.exists()}")
                    if not video_file.exists():
                        logger.error(f"Source file {video_file} does not exist. Cannot move.")
                        continue
                    if target_path.exists():
                        logger.warning(f"Target file {target_path} already exists. Skipping move for {video_file.name}.")
                        continue
                    logger.info(f"Moving {video_file} to {target_path}")
                    shutil.move(str(video_file), str(target_path))
                    logger.info(f"Successfully moved video file to: {target_path}")
                    if not target_path.exists():
                        logger.error(f"Move reported success, but {target_path} does not exist!")
                except Exception as e:
                    logger.error(f"Failed to move video file {video_file.name} to {target_path}: {e}")
            except Exception as e:
                logger.exception(f"Error processing {video_file.name}: {e}")
        logger.info(f"Preview processing complete: {len(video_files)} found, {processed_count} processed, {success_count} successful.")
        return True

class VideoProcessor:
    def __init__(self, video_path: Path, config: Config, jav_code: str):
        self.video_path = video_path
        self.config = config
        self.jav_code = jav_code
        self.base_filename = sanitize_filename(video_path.stem)
        if self.config.ADD_BLACK_BARS:
            self.base_filename += "_black_bars"
        self.output_dir = Path(self.config.VIDEO_DIR) / jav_code.lower()
        self.temp_dir = self.output_dir / f"{self.base_filename}-temp"
        self.metadata: Dict[str, Any] = {}
        self.cut_points_sec: List[float] = []
        self.segment_files: List[Path] = []
        self.timestamped_segment_files: List[Path] = []
        self.segment_frame_files: List[Path] = []
        self.is_vertical = False

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
                    files_to_delete.append((name, file_path))
                else:
                    required_files_missing.append(name)
        all_required_exist = not required_files_missing
        if all_required_exist and not self.config.IGNORE_EXISTING:
            logger.info(f"All required outputs exist for '{self.base_filename}'. Skipping.")
            return False
        if self.config.IGNORE_EXISTING:
            for name, file_path in files_to_delete:
                logger.info(f"Deleting: {file_path.name}")
                file_path.unlink(missing_ok=True)
            return True
        else:
            if files_to_delete:
                logger.warning(f"Some outputs missing, but others exist for '{self.base_filename}'.")
                return False
            return True

    def _get_metadata(self) -> bool:
        logger.debug(f"Extracting metadata for {self.video_path.name}")
        cmd_rot = f'ffprobe -v error -select_streams v:0 -show_entries stream_tags=rotate -of default=nw=1:nk=1 "{self.video_path}"'
        stdout_rot, stderr_rot, exit_code_rot = run_command(cmd_rot)
        if exit_code_rot != 0:
            logger.error(f"ffprobe rotation check failed: {stderr_rot}")
            return False
        if stdout_rot and stdout_rot.strip() not in ["0", ""]:
            logger.error(f"Video has rotation metadata ({stdout_rot.strip()} degrees). Skipping.")
            return False
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
            self.metadata.update({
                "filename": self.video_path.name,
                "title": format_info.get("tags", {}).get("title", "N/A"),
                "duration": float(format_info.get("duration", 0)),
                "size_bytes": int(format_info.get("size", 0)),
                "size_mb": f"{int(format_info.get('size', 0)) / (1024*1024):.2f} MB",
                "width": video_stream.get("width"),
                "height": video_stream.get("height"),
                "video_codec": video_stream.get("codec_name", "N/A").upper(),
                "video_profile": video_stream.get("profile", "N/A"),
                "video_bitrate_kbps": round(int(video_stream.get("bit_rate", 0)) / 1000) if video_stream.get("bit_rate") else 0,
                "fps": round(int(video_stream.get("r_frame_rate", "0/1").split('/')[0]) / int(video_stream.get("r_frame_rate", "0/1").split('/')[1]), 2) if '/' in video_stream.get("r_frame_rate", "0/1") else 0,
            })
            self.is_vertical = self.metadata["width"] < self.metadata["height"]
            self.metadata["resolution"] = f"{self.metadata['width']}x{self.metadata['height']}"
            self.metadata["video_details"] = (f"{self.metadata['video_codec']} ({self.metadata['video_profile']}) @ "
                                             f"{self.metadata['video_bitrate_kbps']} kbps, {self.metadata['fps']} fps")
            self.metadata.update({
                "audio_codec": "N/A",
                "audio_profile": "N/A",
                "audio_channels": "N/A",
                "audio_bitrate_kbps": 0,
                "audio_details": "No Audio Stream"
            })
            if audio_stream:
                self.metadata.update({
                    "audio_codec": audio_stream.get("codec_name", "N/A").upper(),
                    "audio_profile": audio_stream.get("profile", "N/A"),
                    "audio_channels": audio_stream.get("channels", "N/A"),
                    "audio_bitrate_kbps": round(int(audio_stream.get("bit_rate", 0)) / 1000) if audio_stream.get("bit_rate") else 0,
                })
                self.metadata["audio_details"] = (f"{self.metadata['audio_codec']} ({self.metadata['audio_profile']}, "
                                                 f"{self.metadata['audio_channels']}ch) @ {self.metadata['audio_bitrate_kbps']} kbps")
            if self.config.CALCULATE_MD5:
                self.metadata["md5"] = get_md5_hash(self.video_path)
            else:
                self.metadata["md5"] = "N/A (Disabled)"
            if self.metadata["video_codec"] == "MSMPEG4V3":
                logger.error(f"Unsupported codec MSMPEG4V3. Skipping.")
                return False
            logger.info("Metadata extracted successfully.")
            return True
        except Exception as e:
            logger.error(f"Error getting metadata: {e}")
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
            current_start = min(points, default=start_pct)
            current_end = max(points, default=end_pct)
            num_inner_points = num_points - len(points)
            if num_inner_points > 0:
                step = (current_end - current_start) / (num_inner_points + 1)
                for i in range(1, num_inner_points + 1):
                    point = round(current_start + step * i, 3)
                    if point not in self.config.BLACKLISTED_CUT_POINTS:
                        points.add(point)
            if len(points) < num_points:
                start_pct += 0.005
                end_pct -= 0.005
                retries -= 1
                continue
            valid_points = sorted(list(points))
            break
        if len(valid_points) < num_points:
            logger.error(f"Failed to generate {num_points} cut points.")
            return []
        if self.config.PRINT_CUT_POINTS:
            logger.info("Generated cut points:")
            for i, pct in enumerate(valid_points):
                logger.info(f"Segment {i+1}: {pct:.3f} ({format_duration(pct * self.metadata['duration'])})")
        return valid_points

    def _get_vf_filter(self) -> str:
        if self.is_vertical:
            return "scale=480:270:force_original_aspect_ratio=decrease,pad=480:270:(ow-iw)/2:(oh-ih)/2" if self.config.ADD_BLACK_BARS else "scale=270:480"
        return "scale=480:270"

    def _verify_segment(self, segment_path: Path) -> bool:
        if not segment_path.exists() or segment_path.stat().st_size < 1024:
            logger.warning(f"Segment file is missing or too small: {segment_path.name}")
            return False
        cmd_verify = f'ffprobe -v error -select_streams v:0 -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "{segment_path}"'
        stdout, stderr, exit_code = run_command(cmd_verify)
        if exit_code != 0 or not stdout.strip():
            logger.error(f"ffprobe verification failed for {segment_path.name}: {stderr}")
            return False
        try:
            duration = float(stdout.strip())
            if duration <= 0:
                logger.error(f"Invalid duration ({duration}s) for {segment_path.name}.")
                return False
        except ValueError:
            logger.error(f"Non-numeric duration '{stdout.strip()}' for {segment_path.name}.")
            return False
        return True

    def _generate_segments(self) -> Tuple[List[Path], List[Path]]:
        logger.debug(f"Starting segment generation for {self.video_path.name}")
        valid_segment_paths = []
        timestamped_paths_for_sheet = []
        vf_filter = self._get_vf_filter()
        logger.debug(f"Video filter: {vf_filter}")
        total_segments = len(self.cut_points_sec)
        logger.debug(f"Total cut points: {total_segments}")
        for i, start_sec in enumerate(self.cut_points_sec):
            segment_index = i + 1
            if start_sec >= self.metadata["duration"]:
                logger.warning(f"Cut point {start_sec:.3f}s beyond duration. Skipping segment {segment_index}.")
                continue
            cut_duration = min(self.config.SEGMENT_DURATION, self.metadata["duration"] - start_sec)
            if cut_duration <= 0.01:
                logger.warning(f"Segment duration ({cut_duration:.3f}s) too small for segment {segment_index}.")
                continue
            start_time_td = timedelta(seconds=start_sec)
            start_time_ss = f"{int(start_time_td.total_seconds() // 3600):02d}:{int(start_time_td.seconds // 60 % 60):02d}:{int(start_time_td.seconds % 60):02d}.{start_time_td.microseconds:06d}"
            start_time_fn = format_duration(start_sec).replace(":", ".")
            segment_filename = f"{self.base_filename}_start-{start_time_fn}_seg-{segment_index}.mp4"
            segment_path = self.temp_dir / segment_filename
            logger.debug(f"Segment {segment_index} path: {segment_path}")
            ffmpeg_cmd = (
                f'ffmpeg -hide_banner -loglevel error -ss {start_time_ss} -i "{self.video_path}" -t {cut_duration:.3f} '
                f'-vf "{vf_filter}" -map 0:v:0 -c:v libx264 -crf 23 -preset medium -an -sn -dn -map_metadata -1 -map_chapters -1 -y "{segment_path}"'
            )
            logger.debug(f"Running ffmpeg command for segment {segment_index}: {ffmpeg_cmd}")
            stdout, stderr, exit_code = run_command(ffmpeg_cmd)
            if exit_code == 0:
                logger.debug(f"ffmpeg stdout: {stdout}")
                logger.debug(f"ffmpeg stderr: {stderr}")
            if exit_code == 0 and self._verify_segment(segment_path):
                logger.info(f"Generated segment {segment_index}: {segment_path.name}")
                final_segment_path = segment_path
                path_for_mode2_sheet = segment_path
                if self.config.TIMESTAMPS_MODE in [1, 2]:
                    overlay_path = self._overlay_timestamp(segment_path, start_sec)
                    if overlay_path:
                        logger.info(f"Timestamped segment {segment_index}: {overlay_path.name}")
                        if self.config.TIMESTAMPS_MODE == 1:
                            final_segment_path = overlay_path
                        path_for_mode2_sheet = overlay_path
                    else:
                        logger.warning(f"Timestamp overlay failed for segment {segment_index}")
                valid_segment_paths.append(final_segment_path)
                if self.config.TIMESTAMPS_MODE == 2:
                    timestamped_paths_for_sheet.append(path_for_mode2_sheet)
            else:
                logger.error(f"Failed to generate segment {segment_index}: {stderr}")
                segment_path.unlink(missing_ok=True)
        logger.info(f"Generated {len(valid_segment_paths)}/{total_segments} segments.")
        return valid_segment_paths, timestamped_paths_for_sheet

    def _overlay_timestamp(self, segment_path: Path, start_sec: float) -> Optional[Path]:
        logger.debug(f"Overlaying timestamp on {segment_path.name}")
        timestamp_text = format_duration(start_sec).replace(":", r"\:")
        output_path = segment_path.with_name(f"ts_{segment_path.name}")
        font_path = str(Path(self.config.FONT_PATH).resolve()).replace("\\", "/").replace(":", "\\:") if sys.platform == "win32" else str(Path(self.config.FONT_PATH).resolve())
        if not Path(self.config.FONT_PATH).exists():
            logger.warning(f"Font file {self.config.FONT_PATH} not found. Skipping timestamp overlay.")
            return None
        ffmpeg_cmd = (
            f'ffmpeg -hide_banner -loglevel error -i "{segment_path}" '
            f'-vf "drawtext=text=\'{timestamp_text}\':fontfile=\'{font_path}\':fontcolor=white:fontsize=20:x=(w-text_w)-10:y=10:box=1:boxcolor=black@0.4:boxborderw=5" '
            f'-c:v libx264 -crf 23 -preset medium -an -y "{output_path}"'
        )
        logger.debug(f"Running timestamp overlay command: {ffmpeg_cmd}")
        stdout, stderr, exit_code = run_command(ffmpeg_cmd)
        if exit_code == 0 and output_path.exists():
            logger.debug(f"Timestamp overlay successful: {output_path}")
            return output_path
        logger.error(f"Failed timestamp overlay on {segment_path.name}: {stderr}")
        output_path.unlink(missing_ok=True)
        return None

    def _write_concat_file(self, segment_paths: List[Path], output_filename: str) -> Path:
        concat_path = self.temp_dir / output_filename
        with concat_path.open("w", encoding='utf-8') as f:
            for path in segment_paths:
                f.write(f"file '{path.resolve().as_posix()}'\n")
        return concat_path

    def _run_ffmpeg_concat(self, concat_file_path: Path, output_video_path: Path) -> bool:
        concat_cmd = f'ffmpeg -hide_banner -loglevel error -f concat -safe 0 -i "{concat_file_path}" -c copy -y "{output_video_path}"'
        logger.debug(f"Running concat command: {concat_cmd}")
        stdout, stderr, exit_code = run_command(concat_cmd)
        if exit_code != 0 or not output_video_path.exists():
            logger.error(f"Concat failed for {concat_file_path.name}: {stderr}")
            return False
        logger.debug(f"Concat successful: {output_video_path}")
        return True

    def _generate_webp_preview(self) -> bool:
        logger.info("Generating WebP preview...")
        if not self.segment_files:
            logger.error("No segments for WebP preview.")
            return False
        concat_file = self._write_concat_file(self.segment_files, "concat_list_webp_preview.txt")
        logger.debug(f"Concat file for WebP preview: {concat_file}")
        concat_video = self.temp_dir / f"{self.base_filename}_concat_webp_preview.mp4"
        if not self._run_ffmpeg_concat(concat_file, concat_video):
            return False
        output_webp = self.output_dir / f"{self.base_filename}_preview.webp"
        scale_filter = "scale=480:-2" if not self.is_vertical or self.config.ADD_BLACK_BARS else "scale=-2:480"
        webp_cmd = (
            f'ffmpeg -hide_banner -loglevel error -y -i "{concat_video}" '
            f'-vf "fps=24,{scale_filter}:flags=lanczos" '
            f'-c:v libwebp -quality 80 -compression_level 6 -loop 0 -an -vsync 0 "{output_webp}"'
        )
        logger.debug(f"Running WebP preview command: {webp_cmd}")
        stdout, stderr, code = run_command(webp_cmd)
        if code == 0 and output_webp.exists():
            logger.info(f"WebP preview created: {output_webp}")
            return True
        logger.error(f"Failed WebP preview: {stderr}")
        output_webp.unlink(missing_ok=True)
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
            logger.warning("Font not found, using default.")
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
            wrapped_value_lines = []
            current_line = ""
            for word in str(value).split():
                test_line = current_line + (" " if current_line else "") + word
                line_width = font.getbbox(test_line)[2] - font.getbbox(test_line)[0] if hasattr(font, 'getbbox') else font.getsize(test_line)[0]
                if line_width <= value_column_width:
                    current_line = test_line
                else:
                    if current_line:
                        wrapped_value_lines.append(current_line)
                    current_line = word
            if current_line:
                wrapped_value_lines.append(current_line)
            if not wrapped_value_lines:
                wrapped_value_lines = ["N/A"]
            prepared_lines.append((f"{key}:", wrapped_value_lines))
            single_line_height = (font.getbbox("Xp")[3] - font.getbbox("Xp")[1] + line_padding) if hasattr(font, 'getbbox') else font.getsize("Xp")[1] + line_padding
            total_height += len(wrapped_value_lines) * single_line_height
        total_height += 10
        img = Image.new("RGB", (img_width, total_height), color=(0, 0, 0))
        draw = ImageDraw.Draw(img)
        y = 10
        key_x = side_margin
        value_x = side_margin + key_column_width + key_value_gap
        for key_text, value_lines in prepared_lines:
            if key_text:
                draw.text((key_x, y), key_text, font=font, fill=(230, 230, 230))
            current_line_y = y
            for line in value_lines:
                draw.text((value_x, current_line_y), line, font=font, fill=(230, 230, 230))
                single_line_height = (font.getbbox("Xp")[3] - font.getbbox("Xp")[1] + line_padding) if hasattr(font, 'getbbox') else font.getsize("Xp")[1] + line_padding
                current_line_y += single_line_height
            y = current_line_y
        output_path = self.temp_dir / f"{self.base_filename}_info.png"
        try:
            img.save(output_path)
            logger.debug(f"Info image created: {output_path}")
            return output_path
        except Exception as e:
            logger.error(f"Error saving info image: {e}")
            return None

    def _stack_videos(self, input_paths: List[Path], output_path: Path, axis: str = 'h') -> bool:
        if not input_paths:
            logger.error("No input paths for stacking.")
            return False
        stack_func = "hstack" if axis == 'h' else "vstack"
        inputs_str = ' '.join([f'-i "{p}"' for p in input_paths])
        filter_inputs = ''.join([f'[{i}:v]' for i in range(len(input_paths))])
        filter_complex = f'"{filter_inputs}{stack_func}=inputs={len(input_paths)}[v]"'
        map_str = '-map "[v]"'
        fps_output = f"-r {self.metadata.get('fps', 24)}"
        command = f'ffmpeg -hide_banner -loglevel error {inputs_str} -filter_complex {filter_complex} {map_str} {fps_output} -y "{output_path}"'
        logger.debug(f"Running stack command: {command}")
        stdout, stderr, exit_code = run_command(command)
        if exit_code != 0:
            logger.error(f"Stacking ({axis}) failed: {stderr}")
            return False
        if not output_path.exists():
            logger.error(f"Stacking ({axis}) succeeded but output {output_path} not found.")
            return False
        logger.debug(f"Stacking ({axis}) successful: {output_path}")
        return True

    def _generate_webp_preview_sheet(self) -> bool:
        logger.info("Generating animated WebP preview sheet...")
        sheet_segments = self.timestamped_segment_files if self.config.TIMESTAMPS_MODE == 2 else self.segment_files
        if not sheet_segments:
            logger.error("No segments for WebP sheet.")
            return False
        info_image_path = self._create_info_image()
        if not info_image_path:
            logger.error("Failed to create info image for WebP sheet.")
            return False
        info_video_path = self.temp_dir / f"{self.base_filename}_info_video.mp4"
        cmd_info_vid = (
            f'ffmpeg -hide_banner -loglevel error -loop 1 -framerate {self.metadata.get("fps", 24)} '
            f'-t {self.config.SEGMENT_DURATION} -i "{info_image_path}" '
            f'-c:v libx264 -pix_fmt yuv420p -y "{info_video_path}"'
        )
        logger.debug(f"Running info video command: {cmd_info_vid}")
        stdout, stderr, code = run_command(cmd_info_vid)
        if code != 0 or not info_video_path.exists():
            logger.error(f"Failed info video: {stderr}")
            return False
        grid = self.config.GRID_WIDTH
        h_stacked_videos = []
        for i in range(0, len(sheet_segments), grid):
            group = sheet_segments[i:i + grid]
            if len(group) != grid:
                logger.error(f"Incorrect number of segments ({len(group)}) for grid {grid}.")
                return False
            h_stack_output = self.temp_dir / f"hstacked_{i//grid + 1}.mp4"
            if not self._stack_videos(group, h_stack_output, axis='h'):
                logger.error(f"Horizontal stacking failed for group {i//grid + 1}.")
                return False
            h_stacked_videos.append(h_stack_output)
        if not h_stacked_videos:
            logger.error("No horizontally stacked videos created.")
            return False
        final_sheet_video_path = self.temp_dir / f"{self.base_filename}_final_sheet_raw.mp4"
        all_v_inputs = [info_video_path] + h_stacked_videos
        if not self._stack_videos(all_v_inputs, final_sheet_video_path, axis='v'):
            logger.error("Vertical stacking failed.")
            return False
        final_processed_sheet_path = final_sheet_video_path
        if self.config.GRID_WIDTH == 4 and (not self.is_vertical or self.config.ADD_BLACK_BARS):
            downscaled_path = self.temp_dir / f"{self.base_filename}_final_sheet_downscaled.mp4"
            cmd_downscale = (
                f'ffmpeg -hide_banner -loglevel error -i "{final_sheet_video_path}" '
                f'-vf "scale=1280:-2" -c:v libx264 -crf 22 -preset medium -y "{downscaled_path}"'
            )
            logger.debug(f"Running downscale command: {cmd_downscale}")
            stdout, stderr, code = run_command(cmd_downscale)
            if code == 0 and downscaled_path.exists():
                try:
                    og_path = final_sheet_video_path.with_name(final_sheet_video_path.stem + "_og.mp4")
                    if og_path.exists():
                        og_path.unlink()
                    final_sheet_video_path.rename(og_path)
                    downscaled_path.rename(final_sheet_video_path)
                    final_processed_sheet_path = final_sheet_video_path
                except OSError as e:
                    logger.error(f"Error renaming sheet videos: {e}")
            else:
                logger.error(f"Downscaling failed: {stderr}")
        output_webp = self.output_dir / f"{self.base_filename}_preview_sheet.webp"
        cmd_webp = (
            f'ffmpeg -hide_banner -loglevel error -y -i "{final_processed_sheet_path}" '
            f'-vf "fps=24,scale=iw:ih:flags=lanczos" -c:v libwebp -quality 75 -lossless 0 -loop 0 -an -vsync 0 "{output_webp}"'
        )
        logger.debug(f"Running WebP sheet command: {cmd_webp}")
        stdout, stderr, code = run_command(cmd_webp)
        if code == 0 and output_webp.exists():
            logger.info(f"WebP sheet created: {output_webp}")
            return True
        logger.error(f"Failed WebP sheet: {stderr}")
        output_webp.unlink(missing_ok=True)
        return False

    def _extract_segment_frames(self) -> List[Path]:
        logger.info("Extracting frames for image sheet...")
        extracted_frames = []
        segments_to_frame = self.segment_files
        if not segments_to_frame:
            logger.error("No segments available to extract frames.")
            return []
        mid_point_time = self.config.SEGMENT_DURATION / 2.0
        fallback_seek_time = 0.1
        for i, segment_path in enumerate(segments_to_frame):
            frame_filename = segment_path.with_name(f"frame_{segment_path.stem}.png")
            frame_path = self.temp_dir / frame_filename
            cmd_frame_mid = (
                f'ffmpeg -hide_banner -loglevel error -copyts -ss {mid_point_time:.3f} -i "{segment_path}" '
                f'-vf "select=eq(n\\,0)" -vframes 1 -q:v 2 "{frame_path}" -y'
            )
            logger.debug(f"Running frame extraction command: {cmd_frame_mid}")
            stdout, stderr_mid, code_mid = run_command(cmd_frame_mid)
            if code_mid == 0 and frame_path.exists() and frame_path.stat().st_size > 100:
                extracted_frames.append(frame_path)
            else:
                frame_path.unlink(missing_ok=True)
                cmd_frame_fallback = (
                    f'ffmpeg -hide_banner -loglevel error -copyts -ss {fallback_seek_time:.3f} -i "{segment_path}" '
                    f'-vf "select=eq(n\\,0)" -vframes 1 -q:v 2 "{frame_path}" -y'
                )
                logger.debug(f"Running fallback frame extraction command: {cmd_frame_fallback}")
                stdout, stderr_fallback, code_fallback = run_command(cmd_frame_fallback)
                if code_fallback == 0 and frame_path.exists() and frame_path.stat().st_size > 100:
                    extracted_frames.append(frame_path)
                else:
                    logger.error(f"Failed to extract frame for {segment_path.name}: {stderr_fallback}")
                    frame_path.unlink(missing_ok=True)
        if not extracted_frames:
            logger.error("Failed to extract any frames.")
        else:
            logger.info(f"Extracted {len(extracted_frames)} frames.")
        return extracted_frames

    def _generate_image_preview_sheet(self) -> bool:
        logger.info("Generating static image preview sheet...")
        if not self.segment_frame_files:
            logger.error("No frames extracted.")
            return False
        info_image_path = self._create_info_image()
        if not info_image_path:
            logger.error("Info image failed.")
            return False
        sheet_created = False
        try:
            info_img = Image.open(info_image_path)
            info_w, info_h = info_img.size
            first_frame_img = Image.open(self.segment_frame_files[0])
            frame_w, frame_h = first_frame_img.size
            first_frame_img.close()
            grid = self.config.GRID_WIDTH
            num_rows = (len(self.segment_frame_files) + grid - 1) // grid
            sheet_width = info_w
            sheet_height = info_h + (num_rows * frame_h)
            final_sheet_img = Image.new("RGB", (sheet_width, sheet_height), color=(40, 40, 40))
            final_sheet_img.paste(info_img, (0, 0))
            info_img.close()
            for i, frame_path in enumerate(self.segment_frame_files):
                paste_x = (i % grid) * frame_w
                paste_y = info_h + (i // grid) * frame_h
                try:
                    with Image.open(frame_path) as frame_img:
                        final_sheet_img.paste(frame_img, (paste_x, paste_y))
                except Exception as e:
                    logger.error(f"Failed to paste frame {frame_path.name}: {e}")
            output_suffix = f".{self.config.IMAGE_SHEET_FORMAT.lower()}"
            output_path = self.output_dir / f"{self.base_filename}_preview_sheet{output_suffix}"
            save_format = self.config.IMAGE_SHEET_FORMAT.upper()
            save_params = {"quality": 85} if save_format in ["JPG", "JPEG"] else {"optimize": True}
            if save_format in ["JPG", "JPEG"]:
                save_format = "JPEG"
            final_sheet_img.save(output_path, format=save_format, **save_params)
            logger.info(f"Image sheet created: {output_path}")
            sheet_created = True
        except Exception as e:
            logger.error(f"Failed to generate image sheet: {e}")
        return sheet_created

    def run(self):
        logger.info(f"Starting VideoProcessor for {self.video_path.name}")
        logger.debug(f"Config: CREATE_WEBP_PREVIEW={self.config.CREATE_WEBP_PREVIEW}, "
                     f"CREATE_WEBP_PREVIEW_SHEET={self.config.CREATE_WEBP_PREVIEW_SHEET}, "
                     f"CREATE_IMAGE_PREVIEW_SHEET={self.config.CREATE_IMAGE_PREVIEW_SHEET}")
        if not self._check_existing_outputs():
            logger.info(f"Skipping processing for {self.video_path.name} due to existing outputs.")
            return False
        logger.info(f"Processing video: {self.video_path.name}")
        logger.debug(f"Output directory: {self.output_dir}")
        logger.debug(f"Temporary directory: {self.temp_dir}")
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            self.temp_dir.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Created directories: output={self.output_dir}, temp={self.temp_dir}")
        except Exception as e:
            logger.error(f"Failed to create directories: {e}")
            return False
        if not self._get_metadata():
            logger.error(f"Failed to get metadata for {self.video_path.name}.")
            return False
        logger.debug(f"Metadata: {self.metadata}")
        if self.metadata.get("duration", 0) <= 10:
            logger.error(f"Video duration too short (< 10s).")
            return False
        processing_successful = False
        try:
            cut_points_pct = self._generate_cut_points()
            logger.debug(f"Cut points (percent): {cut_points_pct}")
            if not cut_points_pct:
                logger.error("No cut points generated.")
                return False
            self.cut_points_sec = [p * self.metadata["duration"] for p in cut_points_pct]
            logger.debug(f"Cut points (seconds): {self.cut_points_sec}")
            self.segment_files, self.timestamped_segment_files = self._generate_segments()
            logger.debug(f"Segment files: {[p.name for p in self.segment_files]}")
            logger.debug(f"Timestamped segment files: {[p.name for p in self.timestamped_segment_files]}")
            if not self.segment_files:
                logger.error("No valid segments generated.")
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
                logger.debug(f"Extracted frames: {[p.name for p in self.segment_frame_files]}")
                if self.segment_frame_files:
                    results.append(self._generate_image_preview_sheet())
                else:
                    logger.error("No frames extracted for image sheet.")
                    results.append(False)
            processing_successful = any(r is True for r in results)
            if processing_successful:
                logger.info(f"Successfully generated previews for {self.video_path.name}")
            else:
                logger.error(f"Failed to generate any previews for {self.video_path.name}")
        except Exception as e:
            logger.exception(f"Critical error processing {self.video_path.name}: {e}")
        finally:
            if not self.config.KEEP_TEMP_FILES and self.temp_dir.exists():
                logger.debug(f"Cleaning up temporary directory: {self.temp_dir}")
                try:
                    shutil.rmtree(self.temp_dir, ignore_errors=True)
                except Exception as e:
                    logger.error(f"Failed to clean up temp directory: {e}")
        logger.info(f"VideoProcessor completed for {self.video_path.name}. Success: {processing_successful}")
        return processing_successful

# --- GUI for Mode and Directory Selection ---
def select_mode_popup():
    root = tk.Tk()
    root.title("Media Processor Configuration")
    root.geometry("600x400")
    root.resizable(False, False)

    tk.Label(root, text="Processing Mode:", font=("Arial", 12)).pack(anchor="w", padx=10, pady=5)
    mode_var = tk.StringVar(value="both")
    modes = [
        ("Both (Metadata & Preview)", "both"),
        ("Metadata Scraper Only", "metadata"),
        ("Video Preview Only", "preview")
    ]
    for text, mode in modes:
        tk.Radiobutton(root, text=text, value=mode, variable=mode_var, font=("Arial", 10)).pack(anchor="w", padx=20)

    tk.Label(root, text="Directory Selection:", font=("Arial", 12)).pack(anchor="w", padx=10, pady=10)

    tk.Label(root, text="Metadata Input/Output Directory:", font=("Arial", 10)).pack(anchor="w", padx=20)
    metadata_dir_var = tk.StringVar(value=Config.VIDEO_DIR)
    metadata_entry = tk.Entry(root, textvariable=metadata_dir_var, width=50)
    metadata_entry.pack(anchor="w", padx=20, pady=2)
    tk.Button(root, text="Browse", command=lambda: browse_directory(metadata_dir_var)).pack(anchor="w", padx=20, pady=2)

    tk.Label(root, text="Preview Input Directory:", font=("Arial", 10)).pack(anchor="w", padx=20)
    preview_input_var = tk.StringVar(value=Config.PREVIEW_INPUT_FOLDER)
    preview_input_entry = tk.Entry(root, textvariable=preview_input_var, width=50)
    preview_input_entry.pack(anchor="w", padx=20, pady=2)
    tk.Button(root, text="Browse", command=lambda: browse_directory(preview_input_var)).pack(anchor="w", padx=20, pady=2)

    def on_submit():
        Config.VIDEO_DIR = metadata_dir_var.get().strip()
        Config.PREVIEW_INPUT_FOLDER = preview_input_var.get().strip()
        if not Config.VIDEO_DIR or not os.path.isdir(Config.VIDEO_DIR):
            messagebox.showerror("Error", "Invalid Metadata Input/Output Directory.")
            return
        if not Config.PREVIEW_INPUT_FOLDER or not os.path.isdir(Config.PREVIEW_INPUT_FOLDER):
            messagebox.showerror("Error", "Invalid Preview Input Directory.")
            return
        root.quit()

    def browse_directory(var):
        directory = filedialog.askdirectory(initialdir=var.get() or os.getcwd(), title="Select Directory")
        if directory:
            var.set(directory)

    tk.Button(root, text="Run", command=on_submit, font=("Arial", 12), width=10).pack(pady=20)
    root.mainloop()
    selected_mode = mode_var.get()
    root.destroy()
    return selected_mode

# --- Main Execution ---
def main():
    logger.info("Starting Media Processor")
    mode = select_mode_popup()
    if not mode:
        logger.info("No mode selected. Exiting.")
        sys.exit(0)
    logger.info(f"Selected mode: {mode}")
    logger.info(f"Metadata directory: {Config.VIDEO_DIR}")
    logger.info(f"Preview input directory: {Config.PREVIEW_INPUT_FOLDER}")
    if not Config.validate():
        logger.error("Configuration validation failed.")
        sys.exit(1)
    success = False
    if mode in ["both", "metadata"]:
        logger.info("Starting metadata scraper")
        scraper = MetadataScraper(Config)
        success |= scraper.run()
    if mode in ["both", "preview"]:
        logger.info("Starting video preview generator")
        previewer = VideoPreviewGenerator(Config)
        success |= previewer.run()
    end_time = datetime.now()
    logger.info(f"--- Processing complete ---")
    logger.info(f"Total time taken: {end_time - start_time}")
    logger.info(f"Log file: {log_file_path.resolve()}")
    return success

if __name__ == "__main__":
    main()
