import json
import logging
import os
import random
import tempfile
import time
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.auth import default

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

def get_drive_service():
    try:
        credentials, _ = default(scopes=["https://www.googleapis.com/auth/drive"])
        drive = build("drive", "v3", credentials=credentials)
        logging.info("Successfully initialized Google Drive API.")
        return drive
    except Exception as e:
        logging.error(f"Failed to initialize Google Drive API: {e}")
        return None

def process_reel_upload(platform_name, upload_func, extract_metadata_func, preferred_video_name=None):
    load_env()
    drive = get_drive_service()
    if not drive:
        return

    folder_url = os.environ.get("REEL_MEDIA_FOLDER")
    if not folder_url:
        logging.error("REEL_MEDIA_FOLDER not found in environment")
        return

    folder_id = folder_url.split("folders/")[1].split("?")[0]

    lang = random.choice(["es", "en"])
    logging.info(f"Selected language: {lang}")

    # Find the language folder ID
    results = drive.files().list(
        q=f"'{folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and name='{lang}'",
        fields="files(id, name)"
    ).execute()

    if not results.get("files"):
        logging.error(f"Could not find folder for language '{lang}' in Drive.")
        return

    lang_folder_id = results["files"][0]["id"]
    logging.info(f"Found {lang} folder with ID: {lang_folder_id}")

    # List subfolders
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
        return

    random.shuffle(subfolders)
    target_subfolder = None
    target_video_id = None
    target_metadata_id = None
    target_video_name = None

    property_flag = f"{platform_name}_uploaded"

    for subfolder in subfolders:
        res = drive.files().list(
            q=f"'{subfolder['id']}' in parents",
            fields="files(id, name, properties)"
        ).execute()
        files = res.get("files", [])
        
        # Check if any file in the folder (like the metadata file) has our custom property flag set
        already_uploaded = False
        for f in files:
            if f.get("properties", {}).get(property_flag) == "true":
                already_uploaded = True
                break
                
        if already_uploaded:
            continue  # Already uploaded to this platform

        video_id = None
        video_name = None
        # First try to find the preferred video name if specified
        if preferred_video_name:
            for f in files:
                if f["name"] == preferred_video_name:
                    video_id = f["id"]
                    video_name = f["name"]
                    break
                    
        # Fallback to any .mp4 if preferred not found or not specified
        if not video_id:
            for f in files:
                if f["name"].endswith(".mp4") and f["name"] != preferred_video_name:
                    video_id = f["id"]
                    video_name = f["name"]
                    # For youtube, we ideally want reel_youtube.mp4.
                    # But if we just find reel.mp4, we'll use it as fallback.
                    if f["name"] == "reel.mp4":
                        break

        meta_id = None
        for f in files:
            if f["name"] in ("metadata.json", "reels_metadata.json"):
                meta_id = f["id"]
                break

        if video_id and meta_id:
            target_subfolder = subfolder
            target_video_id = video_id
            target_metadata_id = meta_id
            target_video_name = video_name
            break

    if not target_subfolder:
        logging.info(f"No unprocessed subfolders found for platform '{platform_name}'.")
        return

    logging.info(f"Selected subfolder '{target_subfolder['name']}'")

    # Download
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        video_path = tmp_path / target_video_name
        meta_path = tmp_path / "metadata.json"

        for name, file_id, path in [(target_video_name, target_video_id, video_path),
                                    ("metadata.json", target_metadata_id, meta_path)]:
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
                return

        # Parse JSON metadata
        with open(meta_path, "r", encoding="utf-8") as f:
            meta_json = json.load(f)

        try:
            content = extract_metadata_func(meta_json)
        except Exception as e:
            logging.error(f"Failed to extract metadata: {e}")
            return

        # Upload to platform
        logging.info(f"Uploading to {platform_name}...")
        success = False
        try:
            upload_func(video_path, content)
            logging.info(f"Successfully uploaded to {platform_name}!")
            success = True
        except Exception as e:
            logging.error(f"Failed to upload to {platform_name}: {e}")

        # Mark as uploaded using Google Drive custom properties
        if success:
            logging.info(f"Setting '{property_flag}' property on metadata file in Google Drive...")
            try:
                drive.files().update(
                    fileId=target_metadata_id,
                    body={"properties": {property_flag: "true"}}
                ).execute()
                logging.info(f"Successfully marked as uploaded for {platform_name}.")
            except Exception as e:
                logging.error(f"Failed to write flag property to Drive: {e}")
