#!/usr/bin/env python3
import json
import logging
import os
import random
import sys
import tempfile
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.auth import default

# Ensure imports work when run from project root
sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.common.publishers import instagram, facebook

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
    folder_url = os.environ.get("INSTAGRAM_AND_FACEBOOK_MEDIA_FOLDER")
    if not folder_url:
        logging.error("INSTAGRAM_AND_FACEBOOK_MEDIA_FOLDER not found in .env")
        sys.exit(1)
        
    folder_id = folder_url.split("folders/")[1].split("?")[0]
    
    try:
        credentials, _ = default(scopes=["https://www.googleapis.com/auth/drive"])
        drive = build("drive", "v3", credentials=credentials)
    except Exception as e:
        logging.error(f"Failed to initialize Google Drive API: {e}")
        sys.exit(1)
        
    # 2. Pick a language
    lang = random.choice(["es", "en"])
    logging.info(f"Selected language: {lang}")
    
    # Find the language folder ID
    results = drive.files().list(
        q=f"'{folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and name='{lang}'",
        fields="files(id, name)"
    ).execute()
    
    if not results.get("files"):
        logging.error(f"Could not find folder for language {lang}")
        sys.exit(1)
        
    lang_folder_id = results["files"][0]["id"]
    
    # List all files in the language folder
    page_token = None
    files = []
    while True:
        res = drive.files().list(
            q=f"'{lang_folder_id}' in parents",
            fields="nextPageToken, files(id, name)",
            pageToken=page_token
        ).execute()
        files.extend(res.get("files", []))
        page_token = res.get("nextPageToken")
        if not page_token:
            break
            
    if not files:
        logging.error(f"No files found in the {lang} folder.")
        sys.exit(1)
        
    # Group by prefix
    groups = {}
    for f in files:
        name = f["name"]
        if name.endswith("_poster.jpg"):
            prefix = name[:-11]
            groups.setdefault(prefix, {})["poster"] = f
        elif name.endswith("_social_copy.json"):
            prefix = name[:-17]
            groups.setdefault(prefix, {})["json"] = f
        elif name.endswith("_illustration.jpg"):
            prefix = name[:-17]
            groups.setdefault(prefix, {})["illustration"] = f
            
    valid_prefixes = [p for p, g in groups.items() if "poster" in g and "json" in g]
    
    if not valid_prefixes:
        logging.error("No valid content pairs found (poster + json).")
        sys.exit(1)
        
    chosen_prefix = random.choice(valid_prefixes)
    logging.info(f"Selected content prefix: {chosen_prefix}")
    
    group = groups[chosen_prefix]
    
    # 3. Download the pair (and illustration to delete it later)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        poster_path = tmp_path / group["poster"]["name"]
        json_path = tmp_path / group["json"]["name"]
        
        for k, filepath in [("poster", poster_path), ("json", json_path)]:
            file_id = group[k]["id"]
            logging.info(f"Downloading {group[k]['name']}...")
            request = drive.files().get_media(fileId=file_id)
            with open(filepath, "wb") as f:
                downloader = MediaIoBaseDownload(f, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                    
        # Load JSON
        with open(json_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)
            
        tags = metadata.get("tags", "")
        
        # 4. Upload to Instagram
        caption_ig = metadata.get("instagram", metadata.get("caption", ""))
        if tags and tags not in caption_ig:
            caption_ig += f"\n\n{tags}"
            
        logging.info("Uploading to Instagram...")
        ig_success = False
        try:
            ig_id = instagram([poster_path], caption_ig.strip())
            logging.info(f"Successfully uploaded to Instagram: {ig_id}")
            ig_success = True
        except Exception as e:
            logging.error(f"Failed to upload to Instagram: {e}")
            
        # 5. Upload to Facebook
        caption_fb = metadata.get("facebook", metadata.get("caption", ""))
        if tags and tags not in caption_fb:
            caption_fb += f"\n\n{tags}"
            
        logging.info("Uploading to Facebook...")
        fb_success = False
        try:
            fb_id = facebook([poster_path], caption_fb.strip())
            logging.info(f"Successfully uploaded to Facebook: {fb_id}")
            fb_success = True
        except Exception as e:
            logging.error(f"Failed to upload to Facebook: {e}")
            
        # 6. Delete from Google Drive if successful
        if ig_success and fb_success:
            logging.info("Both uploads successful. Deleting files from Google Drive...")
            for k in ["poster", "json", "illustration"]:
                if k in group:
                    file_id = group[k]["id"]
                    try:
                        drive.files().delete(fileId=file_id).execute()
                        logging.info(f"Deleted {group[k]['name']} from Drive.")
                    except Exception as e:
                        logging.error(f"Failed to delete {group[k]['name']}: {e}")
        else:
            logging.warning("Not all uploads succeeded. Files will NOT be deleted from Google Drive.")

if __name__ == "__main__":
    main()
