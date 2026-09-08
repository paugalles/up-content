#!/usr/bin/env python3
import json
import logging
import os
import random
import re
import sys
import tempfile
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.auth import default

# Ensure imports work when run from project root
sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.common.publishers import youtube

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

def load_env():
    env_file = Path(".env")
    if env_file.exists():
        with open(env_file, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    if "=" in line:
                        key, value = line.split("=", 1)
                        os.environ.setdefault(key.strip(), value.strip().strip("'\""))

def parse_metadata(md_content):
    parts = re.split(r'##\s*(?:Para LinkedIn|LinkedIn Post|Para LinkedIn:|LinkedIn Post:).*', md_content, flags=re.IGNORECASE)
    yt_part = parts[0]
    
    title_match = re.search(r'\*\*(?:Título|Título del Video|Title|Video Title).*?\*\*\s*(.*)', yt_part, re.IGNORECASE)
    title = title_match.group(1).strip() if title_match else ""
    
    desc_match = re.search(r'\*\*(?:Descripción|Description).*?\*\*\s*(.*?)(?=\n---|\*\*Capítulos|\*\*Hashtags|\*\*#Hashtags|\Z)', yt_part, re.IGNORECASE | re.DOTALL)
    description = desc_match.group(1).strip() if desc_match else ""
    
    chapters_match = re.search(r'\*\*(?:Capítulos|Capítulos del Video|Chapters).*?\*\*\s*(.*?)(?=\n---|\*\*Hashtags|\*\*#Hashtags|\Z)', yt_part, re.IGNORECASE | re.DOTALL)
    if chapters_match:
        description += "\n\nCapítulos:\n" + chapters_match.group(1).strip()
    
    hashtags_match = re.search(r'\*\*(?:Hashtags|#Hashtags).*?\*\*\s*(.*?)(?=\n---|\Z)', yt_part, re.IGNORECASE | re.DOTALL)
    hashtags_text = hashtags_match.group(1).strip() if hashtags_match else ""
    hashtags = [tag.strip() for tag in hashtags_text.split() if tag.startswith("#")]
    
    return {
        "title": title,
        "caption": description,
        "hashtags": hashtags
    }

def main():
    load_env()
    
    # 1. Initialize Drive API
    folder_url = os.environ.get("YOUTUBE_MEDIA_FOLDER")
    if not folder_url:
        logging.error("YOUTUBE_MEDIA_FOLDER not found in environment")
        sys.exit(1)
        
    folder_id = folder_url.split("folders/")[1].split("?")[0]
    
    try:
        credentials, _ = default(scopes=["https://www.googleapis.com/auth/drive"])
        drive = build("drive", "v3", credentials=credentials)
        logging.info("Successfully initialized Google Drive API.")
    except Exception as e:
        logging.error(f"Failed to initialize Google Drive API: {e}")
        sys.exit(1)
        
    # 2. Pick a random language
    lang = random.choice(["es", "en"])
    logging.info(f"Selected language: {lang}")
    
    # Find the language folder ID
    results = drive.files().list(
        q=f"'{folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and name='{lang}'",
        fields="files(id, name)"
    ).execute()
    
    if not results.get("files"):
        logging.error(f"Could not find folder for language '{lang}' in Drive.")
        sys.exit(1)
        
    lang_folder_id = results["files"][0]["id"]
    logging.info(f"Found {lang} folder with ID: {lang_folder_id}")
    
    # List all subfolders in the language folder
    page_token = None
    subfolders = []
    while True:
        res = drive.files().list(
            q=f"'{lang_folder_id}' in parents and mimeType='application/vnd.google-apps.folder'",
            fields="nextPageToken, files(id, name)",
            pageToken=page_token
        ).execute()
        subfolders.extend(res.get("files", []))
        page_token = res.get("nextPageToken")
        if not page_token:
            break
            
    if not subfolders:
        logging.error(f"No subfolders found in the {lang} folder.")
        sys.exit(1)
        
    # Shuffle subfolders to pick randomly
    random.shuffle(subfolders)
    
    target_video_id = None
    target_metadata_id = None
    target_subfolder = None
    
    # Find a subfolder that has both youtube.mp4 and metadata.md
    for subfolder in subfolders:
        res = drive.files().list(
            q=f"'{subfolder['id']}' in parents",
            fields="files(id, name)"
        ).execute()
        files = res.get("files", [])
        
        video_id = next((f["id"] for f in files if f["name"] == "youtube.mp4"), None)
        meta_id = next((f["id"] for f in files if f["name"] == "metadata.md"), None)
        
        if video_id and meta_id:
            target_video_id = video_id
            target_metadata_id = meta_id
            target_subfolder = subfolder
            break
            
    if not target_video_id or not target_metadata_id:
        logging.error("Could not find any subfolder with both 'youtube.mp4' and 'metadata.md'.")
        sys.exit(1)
        
    logging.info(f"Selected subfolder '{target_subfolder['name']}' with video and metadata.")
    
    # 3. Download the pair
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        video_path = tmp_path / "youtube.mp4"
        meta_path = tmp_path / "metadata.md"
        
        for name, file_id, path in [("youtube.mp4", target_video_id, video_path), 
                                    ("metadata.md", target_metadata_id, meta_path)]:
            logging.info(f"Downloading {name}...")
            try:
                request = drive.files().get_media(fileId=file_id)
                with open(path, "wb") as f:
                    downloader = MediaIoBaseDownload(f, request)
                    done = False
                    while not done:
                        status, done = downloader.next_chunk()
                logging.info(f"Successfully downloaded {name}.")
            except Exception as e:
                logging.error(f"Failed to download {name}: {e}")
                sys.exit(1)
                
        # Parse metadata
        with open(meta_path, "r", encoding="utf-8") as f:
            md_content = f.read()
            
        content = parse_metadata(md_content)
        
        if not content["title"] or not content["caption"]:
            logging.error("Failed to parse 'title' or 'caption' from metadata.md.")
            sys.exit(1)
            
        logging.info(f"Parsed metadata. Title: '{content['title'][:50]}...'")
        
        # 4. Upload to YouTube
        logging.info("Uploading to YouTube...")
        yt_success = False
        try:
            yt_id = youtube(video_path, content)
            logging.info(f"Successfully uploaded to YouTube! Video ID: {yt_id}")
            yt_success = True
        except Exception as e:
            logging.error(f"Failed to upload to YouTube: {e}")
            
        # 5. Delete video from Google Drive ONLY if upload was successful
        if yt_success:
            logging.info("Upload was successful. Deleting 'youtube.mp4' from Google Drive...")
            try:
                drive.files().delete(fileId=target_video_id).execute()
                logging.info("Successfully deleted 'youtube.mp4' from Drive.")
            except Exception as e:
                logging.error(f"Failed to delete 'youtube.mp4' from Drive: {e}")
        else:
            logging.warning("YouTube upload failed. Video will NOT be deleted from Google Drive.")

if __name__ == "__main__":
    main()
