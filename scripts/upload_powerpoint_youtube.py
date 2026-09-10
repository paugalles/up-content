#!/usr/bin/env python3
import json
import logging
import os
import random
import sys
import tempfile
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
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
    target_json_data = None
    
    # 3. Find a subfolder that has both youtube.mp4 and metadata.json AND hasn't been uploaded yet
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        for subfolder in subfolders:
            res = drive.files().list(
                q=f"'{subfolder['id']}' in parents",
                fields="files(id, name)"
            ).execute()
            files = res.get("files", [])
            
            video_id = next((f["id"] for f in files if f["name"] == "youtube.mp4"), None)
            meta_id = next((f["id"] for f in files if f["name"] == "metadata.json"), None)
            
            if video_id and meta_id:
                # Download JSON to check if it's already uploaded
                json_path = tmp_path / f"{subfolder['id']}_metadata.json"
                try:
                    request = drive.files().get_media(fileId=meta_id)
                    with open(json_path, "wb") as f:
                        downloader = MediaIoBaseDownload(f, request)
                        done = False
                        while not done:
                            status, done = downloader.next_chunk()
                            
                    with open(json_path, "r", encoding="utf-8") as f:
                        meta_json = json.load(f)
                        
                    if not meta_json.get("youtube_uploaded"):
                        target_video_id = video_id
                        target_metadata_id = meta_id
                        target_subfolder = subfolder
                        target_json_data = meta_json
                        break
                except Exception as e:
                    logging.error(f"Failed to process metadata for {subfolder['name']}: {e}")
                    continue
                
        if not target_video_id or not target_metadata_id:
            logging.info(f"Could not find any unprocessed subfolder in {lang} with 'youtube.mp4' and 'metadata.json'.")
            sys.exit(0)
            
        logging.info(f"Selected subfolder '{target_subfolder['name']}' with video and metadata.")
        
        video_path = tmp_path / "youtube.mp4"
        
        logging.info("Downloading youtube.mp4...")
        try:
            request = drive.files().get_media(fileId=target_video_id)
            with open(video_path, "wb") as f:
                downloader = MediaIoBaseDownload(f, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
            logging.info("Successfully downloaded youtube.mp4.")
        except Exception as e:
            logging.error(f"Failed to download youtube.mp4: {e}")
            sys.exit(1)
            
        yt_meta = target_json_data.get("youtube", {})
        content = {
            "title": yt_meta.get("title", ""),
            "caption": yt_meta.get("description", ""),
            "hashtags": yt_meta.get("tags", [])
        }
        
        if not content["title"] or not content["caption"]:
            logging.error("Failed to parse 'title' or 'description' from metadata.json.")
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
            
        # 5. Mark as uploaded in Google Drive instead of deleting
        if yt_success:
            logging.info("Upload was successful. Writing 'youtube_uploaded' key into JSON metadata...")
            try:
                target_json_data["youtube_uploaded"] = True
                updated_json_path = tmp_path / "updated_metadata.json"
                with open(updated_json_path, "w", encoding="utf-8") as f:
                    json.dump(target_json_data, f, indent=4, ensure_ascii=False)
                    
                media = MediaFileUpload(str(updated_json_path), mimetype="application/json")
                drive.files().update(
                    fileId=target_metadata_id,
                    media_body=media
                ).execute()
                logging.info("Successfully updated 'metadata.json' on Drive.")
            except Exception as e:
                logging.error(f"Failed to update 'metadata.json' on Drive: {e}")
        else:
            logging.warning("YouTube upload failed. Metadata will NOT be updated.")

if __name__ == "__main__":
    main()
