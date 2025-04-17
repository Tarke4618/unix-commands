#!/usr/bin/env python3
import os
import re
import requests
from bs4 import BeautifulSoup, NavigableString # Import NavigableString
import logging
from urllib.parse import urljoin, urlparse
import sys
import time

# --- Configuration ---
VIDEO_DIR = "/home/s/Videos/" # Make sure this exists and is writable
BASE_URL = "https://www.javdatabase.com/"
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': BASE_URL,
}
IMG_HEADERS = HEADERS.copy()
IMG_HEADERS['Accept'] = 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8'

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Regex for JAV Code ---
JAV_CODE_REGEX = re.compile(r'([A-Za-z]{2,5})-?(\d{2,5})', re.IGNORECASE)

# --- Helper Functions ---
def extract_jav_code(filename):
    name_part = os.path.splitext(filename)[0]
    match = JAV_CODE_REGEX.search(name_part)
    if match:
        prefix = match.group(1).upper()
        number = match.group(2)
        return f"{prefix}-{number}"
    return None

def download_image(url, filepath, referer=None):
    try:
        dl_headers = IMG_HEADERS.copy()
        if referer:
            dl_headers['Referer'] = referer
        logging.info(f"Attempting to download image: {url}")
        time.sleep(0.3)
        response = requests.get(url, headers=dl_headers, stream=True, timeout=45)
        response.raise_for_status()
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        logging.info(f"Successfully downloaded: {filepath}")
        os.chmod(filepath, 0o664) # Set permissions after successful download
        return True
    except requests.exceptions.Timeout:
        logging.error(f"Timeout occurred while downloading {url}")
        if os.path.exists(filepath): os.remove(filepath)
        return False
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to download {url}: {e}")
        if os.path.exists(filepath): os.remove(filepath)
        return False
    except Exception as e:
        logging.error(f"An unexpected error occurred during download of {url}: {e}")
        if os.path.exists(filepath): os.remove(filepath)
        return False

def create_metadata_file(filepath, data):
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f"[title]\n{data.get('title_long', 'N/A')}\n\n")
            f.write("[details]\n")
            f.write(f"ID: {data.get('id', 'N/A')}\n")
            f.write(f"Content ID: {data.get('content_id', 'N/A')}\n")
            f.write(f"Release Date: {data.get('release_date', 'N/A')}\n")
            f.write(f"Runtime: {data.get('runtime', 'N/A')}\n")
            f.write(f"Studio: {data.get('studio', 'N/A')}\n")
            f.write(f"Director: {data.get('director', 'N/A')}\n\n")
            f.write("[cast]\n")
            cast_list = data.get('cast', [])
            f.write('\n'.join(cast_list if cast_list else ['N/A']) + '\n\n')
            f.write("[plot]\n")
            plot_text = data.get('plot', 'N/A')
            f.write(plot_text if plot_text else 'N/A') # Write plot, handle None
            f.write('\n\n') # Add newline after plot regardless
            f.write("[tags]\n")
            f.write(', '.join(data.get('genres', ['N/A'])) + '\n\n')
            f.write("[cover]\n")
            f.write(f"{data.get('cover_filename', 'N/A')}\n\n")
            f.write("[screens]\n")
            f.write('\n'.join(f"[img]{s}[/img]" for s in data.get('screenshot_filenames', [])))
            f.write('\n')
        logging.info(f"Metadata file created: {filepath}")
        os.chmod(filepath, 0o664) # Set permissions after writing
    except Exception as e:
        logging.error(f"Failed to write metadata file {filepath}: {e}")

# --- Main Processing Logic ---
def process_video(filepath):
    filename = os.path.basename(filepath)
    jav_code = extract_jav_code(filename)
    if not jav_code:
        logging.warning(f"Could not extract JAV code from: {filename}")
        return

    logging.info(f"--- Processing: {filename} (Code: {jav_code}) ---")
    jav_code_lower = jav_code.lower()
    # Define potential output path FIRST for the offline check
    output_dir = os.path.join(VIDEO_DIR, jav_code_lower)
    metadata_filepath = os.path.join(output_dir, f"{jav_code_lower}.txt")
    cover_filename_base = f"{jav_code_lower}_cover" # Needed for checking cover existence later

    # --- *** OFFLINE CHECK *** ---
    # Check if the metadata TXT file already exists.
    if os.path.exists(metadata_filepath):
        logging.info(f"Metadata file '{metadata_filepath}' already exists. Skipping online scrape for {jav_code}.")
        # Optional: Check if images exist and log that too?
        # cover_exists = any(os.path.exists(os.path.join(output_dir, f"{cover_filename_base}{ext}")) for ext in ['.webp', '.jpg', '.jpeg', '.png'])
        # screenshots_exist = any(f.startswith(f"{jav_code_lower}_screenshot_") for f in os.listdir(output_dir)) if os.path.exists(output_dir) else False
        # if cover_exists and screenshots_exist:
        #     logging.info(f"Cover and screenshots likely already exist for {jav_code}.")
        # else:
        #      logging.warning(f"Metadata file exists, but cover/screenshots might be missing for {jav_code}. Re-run script without this file to redownload.")
        return # <<<< EXIT HERE if file exists

    # --- If metadata file doesn't exist, proceed with online scraping ---
    movie_url = urljoin(BASE_URL, f"movies/{jav_code_lower}/")

    # Create directory (only if we are actually going to scrape)
    try:
        os.makedirs(output_dir, exist_ok=True)
        os.chmod(output_dir, 0o775)
    except OSError as e:
        logging.error(f"Failed to create directory {output_dir}: {e}")
        return
    except PermissionError:
         logging.error(f"Permission denied creating or setting permissions for {output_dir}")
         return

    # Fetch HTML
    logging.info(f"Fetching HTML for {jav_code} from {movie_url}")
    try:
        page_response = requests.get(movie_url, headers=HEADERS, timeout=30)
        page_response.raise_for_status()
        # Check content AFTER successful status code
        temp_soup = BeautifulSoup(page_response.content, 'lxml')
        if not temp_soup.title or "Page not found" in temp_soup.title.string or "Nothing Found" in temp_soup.text:
             logging.error(f"Movie page not found or invalid for {jav_code} at {movie_url}")
             # Clean up empty directory if created? Optional.
             # try:
             #     if not os.listdir(output_dir): os.rmdir(output_dir)
             # except OSError: pass
             return
        soup = temp_soup
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to fetch page {movie_url}: {e}")
        return
    except Exception as e:
         logging.error(f"An unexpected error occurred fetching {movie_url}: {e}")
         return

    metadata = {'id': jav_code, 'cast': [], 'genres': [], 'plot': 'N/A'}

    try:
        # Title
        title_h1 = soup.select_one('header.entry-header h1')
        metadata['title_long'] = title_h1.get_text(strip=True) if title_h1 else jav_code

        # Details, Cast, Genres
        details_container = soup.select_one('div.entry-content div.row')
        if details_container:
            details_column = details_container.select_one('div.col-md-10, div.col-lg-10, div.col-8')
            if details_column:
                logging.info(f"Parsing details section for {jav_code}...")
                # Find all direct child paragraphs of the details column
                details_paragraphs = details_column.find_all('p', class_='mb-1', recursive=False)
                for p in details_paragraphs:
                    strong_tag = p.find('b')
                    if not strong_tag: continue
                    label = strong_tag.get_text(strip=True).replace(':', '').strip()
                    links = p.find_all('a')
                    link_texts = [a.get_text(strip=True) for a in links if a.get_text(strip=True)]
                    value_text = ''.join(node.strip() + ' ' for node in strong_tag.find_next_siblings(string=True)).strip()

                    if label == "Content ID": metadata['content_id'] = value_text or 'N/A'
                    elif label == "Release Date": metadata['release_date'] = value_text or 'N/A'
                    elif label == "Runtime": metadata['runtime'] = value_text or 'N/A'
                    elif label == "Studio": metadata['studio'] = link_texts[0] if link_texts else (value_text or 'N/A')
                    elif label == "Director": metadata['director'] = link_texts[0] if link_texts else (value_text or 'N/A')
                    elif label == "Genre(s)": metadata['genres'] = sorted(list(set(link_texts))) if link_texts else []
                    elif label == "Idol(s)/Actress(es)":
                        metadata['cast'] = sorted(list(set(link_texts))) if link_texts else []
                        logging.info(f"Extracted Cast: {metadata['cast']}")

        if not metadata.get('cast'): # Fallback
            fallback_cast_links = soup.select('div.entry-content a[href*="/idols/"]')
            metadata['cast'] = sorted(list(set(a.get_text(strip=True) for a in fallback_cast_links if a.get_text(strip=True))))
            if metadata['cast']: logging.info(f"Found cast via fallback: {metadata['cast']}")
            else: logging.warning(f"Failed to find cast for {jav_code} via primary or fallback.")


        # --- Plot (Extract from Parent Div Content & Clean) ---
        plot_heading_regex = re.compile(r'About\s+' + re.escape(jav_code) + r'\s+JAV Movie', re.IGNORECASE)
        plot_heading = soup.find('h4', class_='subhead', string=plot_heading_regex)
        metadata['plot'] = 'N/A' # Reset default

        if plot_heading:
            logging.info(f"Found plot heading for {jav_code}.")
            plot_parent_div = plot_heading.parent
            if plot_parent_div:
                logging.debug(f"Scanning contents of plot parent div: {plot_parent_div.name} ({plot_parent_div.get('class', '')})")
                plot_text_parts = []
                stop_extracting = False
                # Iterate through the direct children/contents of the parent div
                for content in plot_parent_div.contents:
                    if stop_extracting: break

                    if content == plot_heading: continue # Skip the H4 heading itself

                    # Check for stop conditions BEFORE extracting text
                    if content.name == 'div' and content.find(id=lambda x: x and x.startswith('post-ratings')):
                        logging.debug("Stopping plot extraction at ratings div.")
                        stop_extracting = True; break
                    if isinstance(content, NavigableString) and "JAV Database only provides" in content:
                        logging.debug("Stopping plot extraction at disclaimer text.")
                        text_part = content.strip().split("JAV Database only provides")[0].strip()
                        if text_part: plot_text_parts.append(text_part)
                        stop_extracting = True; break
                    if content.name == 'p' and "JAV Database only provides" in content.get_text():
                         logging.debug("Stopping plot extraction at disclaimer text within <p>.")
                         text_part = content.get_text(strip=True).split("JAV Database only provides")[0].strip()
                         if text_part: plot_text_parts.append(text_part)
                         stop_extracting = True; break

                    # Extract text based on node type (get raw text chunks)
                    text_chunk = None
                    if isinstance(content, NavigableString):
                        text_chunk = content.string # Get raw string content, including spaces
                    elif content.name == 'p':
                        text_chunk = content.get_text() # Get text from paragraphs
                    # elif content.name == 'br': # Ignore <br> for now, handle with whitespace collapse
                    #     pass # Or maybe add a space: text_chunk = ' '
                    # Can add handling for other tags if needed, e.g., content.get_text()

                    if text_chunk:
                        # Append the raw chunk - cleaning happens after joining
                        plot_text_parts.append(text_chunk)
                        # Optional: Log the raw chunk for debugging
                        # logging.debug(f"Added raw plot chunk: '{text_chunk[:50]}...'")


                # --- ** CLEANING STEP ** ---
                # Join collected parts with a single space initially to separate words from different nodes
                raw_joined_plot = ' '.join(plot_text_parts).strip()

                if raw_joined_plot:
                    # Collapse multiple whitespace chars (including newlines, tabs, etc.) into a single space
                    cleaned_plot = re.sub(r'\s+', ' ', raw_joined_plot).strip()

                    # Optional: Remove specific repeated phrases if needed (example)
                    # cleaned_plot = cleaned_plot.replace("PRED-745 is a JAV movie starring Karen Yuzuriha.", "") # Be careful with this

                    metadata['plot'] = cleaned_plot
                    logging.info(f"Extracted cleaned plot (length {len(metadata['plot'])}): {metadata['plot'][:100]}...")
                else:
                    logging.warning(f"Found plot parent div but extracted no plot text for {jav_code}.")
            else:
                 logging.warning(f"Found plot heading but could not get its parent div for {jav_code}.")
        else:
            logging.warning(f"Could not find plot heading for {jav_code}")

        # --- (Rest of the scraping logic: Cover Image, Screenshots, Create Metadata File) ---
        # --- Cover Image ---
        cover_img_tag = soup.select_one('#poster-container img')
        cover_filename = "N/A"
        if cover_img_tag and cover_img_tag.get('src'):
            cover_url_relative = cover_img_tag['src']
            cover_url_absolute = urljoin(movie_url, cover_url_relative)
            cover_path = urlparse(cover_url_absolute).path
            cover_ext = os.path.splitext(cover_path)[1] if os.path.splitext(cover_path)[1] else '.webp'
            # cover_filename_base defined earlier for offline check
            cover_filename = f"{cover_filename_base}{cover_ext}"
            cover_filepath = os.path.join(output_dir, cover_filename)
            existing_cover = None
            for ext_try in ['.webp', '.jpg', '.jpeg', '.png']:
                potential_path = os.path.join(output_dir, f"{cover_filename_base}{ext_try}")
                if os.path.exists(potential_path):
                    existing_cover = potential_path
                    cover_filename = os.path.basename(existing_cover)
                    break
            if not existing_cover:
                 logging.info(f"Attempting download of cover: {cover_url_absolute}")
                 if not download_image(cover_url_absolute, cover_filepath, referer=movie_url):
                      cover_filename = "N/A (Download Failed)"
                 # Permissions set in download_image on success
            else: logging.info(f"Cover image already exists: {existing_cover}")
        else: logging.warning(f"Could not find cover image tag for {jav_code}")
        metadata['cover_filename'] = cover_filename

        # --- Screenshots ---
        logging.info(f"Looking for screenshots for {jav_code}...")
        screenshot_filenames = []
        count = 0
        screenshot_heading = soup.find('h4', class_='subhead', string=re.compile(f'{jav_code}.* Images', re.IGNORECASE))
        if screenshot_heading:
            screenshot_container = screenshot_heading.find_next_sibling('div', class_='container')
            if screenshot_container:
                screenshot_links = screenshot_container.select('div.row.g-3 a[data-image-href]')
                logging.info(f"Found {len(screenshot_links)} screenshot links.")
                for i, link_tag in enumerate(screenshot_links):
                    full_size_url = link_tag.get('data-image-href')
                    if not full_size_url: continue
                    logging.debug(f"Processing screenshot URL {count + 1}: {full_size_url}") # Debug level for URL
                    ss_path = urlparse(full_size_url).path
                    ss_ext = os.path.splitext(ss_path)[1] if os.path.splitext(ss_path)[1] else '.jpg'
                    screenshot_filename_base = f"{jav_code_lower}_screenshot_{count + 1:02d}"
                    screenshot_filename = f"{screenshot_filename_base}{ss_ext}"
                    screenshot_filepath = os.path.join(output_dir, screenshot_filename)
                    existing_screenshot = None
                    for ext_try in ['.jpg', '.jpeg', '.png', '.webp']:
                        potential_path = os.path.join(output_dir, f"{screenshot_filename_base}{ext_try}")
                        if os.path.exists(potential_path):
                            existing_screenshot = potential_path
                            screenshot_filename = os.path.basename(existing_screenshot)
                            break
                    if not existing_screenshot:
                        if download_image(full_size_url, screenshot_filepath, referer=movie_url):
                            screenshot_filenames.append(screenshot_filename)
                            count += 1
                        else: logging.warning(f"Failed download screenshot {count + 1}")
                    else:
                        logging.info(f"Screenshot {count + 1} already exists: {existing_screenshot}")
                        screenshot_filenames.append(screenshot_filename)
                        count += 1
            else: logging.warning(f"Found screenshot heading, but no container div for {jav_code}")
        else: logging.warning(f"Could not find screenshot heading for {jav_code}")
        logging.info(f"Finished processing screenshots. Got {len(screenshot_filenames)} images.")
        metadata['screenshot_filenames'] = screenshot_filenames

        # --- Create Metadata File ---
        # Check if we actually got *any* useful metadata beyond the ID
        if metadata.get('title_long', jav_code) != jav_code or metadata.get('cast') or metadata.get('plot', 'N/A') != 'N/A':
             create_metadata_file(metadata_filepath, metadata)
        else:
             logging.warning(f"Failed to scrape significant metadata for {jav_code}. Not creating text file.")
             # Clean up directory? Only if no images were downloaded.
             if not metadata.get('cover_filename', 'N/A').startswith(jav_code_lower) and not metadata.get('screenshot_filenames'):
                 logging.info(f"Cleaning up empty directory {output_dir} due to failed scrape.")
                 try:
                     os.rmdir(output_dir)
                 except OSError as e:
                     logging.error(f"Failed to remove empty directory {output_dir}: {e}")


    except Exception as e:
        logging.exception(f"An critical error occurred during scraping/processing for {jav_code}: {e}")
        # Also attempt cleanup if a critical error occurs during scraping
        if not os.path.exists(metadata_filepath):
             try:
                  # Check if directory is empty besides maybe a failed partial download
                  if not any(f.startswith(jav_code_lower) for f in os.listdir(output_dir)):
                      logging.info(f"Cleaning up potentially empty directory {output_dir} due to scraping error.")
                      os.rmdir(output_dir)
             except Exception as cleanup_e:
                  logging.error(f"Error during cleanup for {output_dir}: {cleanup_e}")


# --- Main Execution ---
if __name__ == "__main__":
    if not os.path.isdir(VIDEO_DIR):
        logging.error(f"Video directory not found or is not a directory: {VIDEO_DIR}")
        sys.exit(1)
    if not os.access(VIDEO_DIR, os.W_OK):
        logging.error(f"No write permissions for video directory: {VIDEO_DIR}")
        sys.exit(1)

    found_videos = 0
    processed_videos = 0 # Count actual attempts to process
    skipped_videos = 0

    logging.info(f"Scanning directory: {VIDEO_DIR}")
    try:
        all_items = os.listdir(VIDEO_DIR)
        video_files = [f for f in all_items
                       if os.path.isfile(os.path.join(VIDEO_DIR, f)) and
                       f.lower().endswith(('.mp4', '.mkv', '.avi', '.wmv', '.mov'))]
        found_videos = len(video_files)
        logging.info(f"Found {found_videos} potential video files.")

        for item in video_files:
            # Check offline status *before* calling process_video
            jav_code_check = extract_jav_code(item)
            if jav_code_check:
                metadata_path_check = os.path.join(VIDEO_DIR, jav_code_check.lower(), f"{jav_code_check.lower()}.txt")
                if os.path.exists(metadata_path_check):
                    logging.info(f"Offline check: Metadata exists for '{item}' ({jav_code_check}). Skipping.")
                    skipped_videos += 1
                    continue # Skip to next video file

            # If offline check passes (no file exists), proceed to process
            processed_videos +=1
            item_path = os.path.join(VIDEO_DIR, item)
            process_video(item_path) # process_video now contains the main logic

    except Exception as e:
        logging.error(f"An unexpected error occurred while scanning directory: {e}")

    logging.info(f"--- Script finished ---")
    logging.info(f"Found video files: {found_videos}")
    logging.info(f"Skipped (already processed offline): {skipped_videos}")
    logging.info(f"Attempted processing (online): {processed_videos}")
    if found_videos == 0:
        logging.warning(f"No video files (.mp4, .mkv, .avi, etc.) found in {VIDEO_DIR}")
