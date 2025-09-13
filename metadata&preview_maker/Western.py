import os
import requests
import json
import mimetypes
import configparser

# --- Configuration ---
config = configparser.ConfigParser()
config.read(os.path.join(os.path.dirname(__file__), 'config.ini'))

API_URL = config.get('Western', 'api_url', fallback='https://theporndb.net/graphql')
API_TOKEN = config.get('Western', 'api_token')
VIDEO_DIR = config.get('General', 'video_dir', fallback='/home/s/Videos/')

if API_TOKEN == 'YOUR_API_TOKEN_HERE' or not API_TOKEN:
    print("API token is not configured. Please edit config.ini and set your ThePornDB API token.")
    exit(1)

# Query Template
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

# Folder Configuration
folder_path = VIDEO_DIR

def format_tags(tags):
    """Format tags to lowercase with dots for spaces and spaces between tags."""
    return " ".join(tag["name"].lower().replace(" ", ".") for tag in tags)

def generate_title_from_filename(filename):
    """Generate a formatted title string from the filename."""
    # Remove extension and split by dots
    base_name = os.path.splitext(filename)[0]
    # Try to extract resolution (e.g., [1080p]) if present
    resolution = ""
    if "[" in base_name and "]" in base_name:
        start = base_name.rfind("[")
        end = base_name.rfind("]")
        if start < end:
            resolution = base_name[start:end+1]
            base_name = base_name[:start].strip()
    # Use the base name as the title, clean up if needed
    title = base_name.replace(".", " ").strip()
    # Return formatted title (e.g., [title] [resolution])
    return f"[{title}] {resolution}".strip()

def search_video_metadata(filename):
    """Search for video metadata using the filename as the search term."""
    search_term = os.path.splitext(filename)[0]

    headers = {"Authorization": f"Bearer {API_TOKEN}"}
    variables = {"term": search_term}
    response = requests.post(API_URL, headers=headers, json={"query": QUERY, "variables": variables})

    if response.status_code == 200:
        data = response.json()
        if "data" in data and data["data"]["searchScene"]:
            return data["data"]["searchScene"][0]  # Return the first result
        else:
            print(f"No results found for {filename}")
            return None
    else:
        print(f"API Error: {response.status_code} - {response.text}")
        return None

def download_cover_image(image_url, base_output_path):
    """Download the cover image from the URL and save it with the correct extension."""
    try:
        response = requests.get(image_url, stream=True)
        if response.status_code == 200:
            # Determine file extension from content-type
            content_type = response.headers.get('content-type', '')
            extension = mimetypes.guess_extension(content_type)
            if not extension:
                # Fallback to .webp if content-type is unknown or unsupported
                extension = '.webp'
            # Append the extension to the base output path
            output_path = f"{base_output_path}{extension}"

            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            return True, os.path.basename(output_path)  # Return success and the filename
        else:
            print(f"Failed to download image from {image_url}: Status {response.status_code}")
            return False, None
    except Exception as e:
        print(f"Error downloading image from {image_url}: {str(e)}")
        return False, None

def create_text_file(file_path, metadata, filename):
    """Create a text file with formatted metadata and download the cover image."""
    title = metadata.get("title", "Unknown Title")
    date = metadata.get("date", "Unknown Date")
    performers = metadata.get("performers", [])
    studio = metadata.get("studio", {}).get("name", "Unknown Studio")
    details = metadata.get("details", "No Plot Available")
    tags = metadata.get("tags", [])
    images = metadata.get("images", [])

    # Format metadata fields
    cast_list = "\n".join(f"[*] {p['performer']['name']}" for p in performers)
    tags_list = format_tags(tags)
    formatted_title = generate_title_from_filename(filename)

    # Handle cover image
    cover_field = "[No cover available]"
    if images and isinstance(images, list) and 'url' in images[0]:
        image_url = images[0]['url']
        # Generate base cover image filename (without extension)
        base_cover_filename = f"{os.path.splitext(filename)[0]}_cover"
        base_cover_path = os.path.join(folder_path, base_cover_filename)

        # Download the cover image and get the actual filename
        success, cover_filename = download_cover_image(image_url, base_cover_path)
        if success and cover_filename:
            cover_field = cover_filename  # Use the downloaded filename (e.g., video_cover.webp)
        else:
            cover_field = "[Failed to download cover]"

    # Format text content
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
    # Write to file
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

def main():
    """Process video files in the folder and create metadata text files."""
    if not os.path.exists(folder_path):
        print(f"Folder not found: {folder_path}")
        return

    for filename in os.listdir(folder_path):
        if filename.endswith((".mp4", ".mkv", ".avi")):  # Adjust for video file extensions
            print(f"Processing: {filename}")

            metadata = search_video_metadata(filename)
            if metadata:
                file_path = os.path.join(folder_path, f"{os.path.splitext(filename)[0]}.txt")
                create_text_file(file_path, metadata, filename)
                print(f"Text file created: {file_path}")
            else:
                print(f"Metadata not found for: {filename}")

if __name__ == "__main__":
    main()
