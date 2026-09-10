import json
import logging
import os
import random
import tempfile
import time
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
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

def process_poster_upload(platform_name, upload_func, extract_metadata_func):
    load_env()
    drive = get_drive_service()
    if not drive:
        return

    folder_url = os.environ.get("POSTER_MEDIA_FOLDER")
    if not folder_url:
        logging.error("POSTER_MEDIA_FOLDER not found in environment")
        return

    folder_id = folder_url.split("folders/")[1].split("?")[0]

    lang = random.choice(["es", "en"])
    logging.info(f"Selected language: {lang}")

    results = drive.files().list(
        q=f"'{folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and name='{lang}'",
        fields="files(id, name)"
    ).execute()

    if not results.get("files"):
        logging.error(f"Could not find folder for language '{lang}' in Drive.")
        return

    lang_folder_id = results["files"][0]["id"]
    logging.info(f"Found {lang} folder with ID: {lang_folder_id}")

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
        return
        
    groups = {}
    for f in files:
        name = f["name"]
        if name.endswith("_poster.jpg"):
            prefix = name[:-11]
            groups.setdefault(prefix, {})["poster"] = f
        elif name.endswith("_social_copy.json"):
            prefix = name[:-17]
            groups.setdefault(prefix, {})["json"] = f

    valid_prefixes = [p for p, g in groups.items() if "poster" in g and "json" in g]
    if not valid_prefixes:
        logging.error("No complete poster+json groups found.")
        return
        
    random.shuffle(valid_prefixes)

    target_prefix = None
    target_poster = None
    target_json = None
    target_json_data = None

    uploaded_key = f"{platform_name}_uploaded"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        for prefix in valid_prefixes:
            group = groups[prefix]
            json_file = group["json"]
            poster_file = group["poster"]
            
            # Download JSON to check for the uploaded_key
            json_path = tmp_path / json_file["name"]
            try:
                request = drive.files().get_media(fileId=json_file["id"])
                with open(json_path, "wb") as f:
                    downloader = MediaIoBaseDownload(f, request)
                    done = False
                    while not done:
                        status, done = downloader.next_chunk()
                        
                with open(json_path, "r", encoding="utf-8") as f:
                    meta_json = json.load(f)
                    
                if not meta_json.get(uploaded_key):
                    target_prefix = prefix
                    target_poster = poster_file
                    target_json = json_file
                    target_json_data = meta_json
                    break
            except Exception as e:
                logging.error(f"Failed to process {json_file['name']}: {e}")
                continue

        if not target_prefix:
            logging.info(f"No unprocessed posters found for platform '{platform_name}'.")
            return

        logging.info(f"Selected poster '{target_prefix}'")
        
        poster_path = tmp_path / target_poster["name"]
        logging.info(f"Downloading {target_poster['name']}...")
        try:
            request = drive.files().get_media(fileId=target_poster["id"])
            with open(poster_path, "wb") as f:
                downloader = MediaIoBaseDownload(f, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
        except Exception as e:
            logging.error(f"Failed to download poster: {e}")
            return
            
        try:
            content = extract_metadata_func(target_json_data)
        except Exception as e:
            logging.error(f"Failed to extract metadata: {e}")
            return
            
        logging.info(f"Uploading to {platform_name}...")
        success = False
        try:
            upload_func(poster_path, content)
            logging.info(f"Successfully uploaded to {platform_name}!")
            success = True
        except Exception as e:
            logging.error(f"Failed to upload to {platform_name}: {e}")

        if success:
            logging.info(f"Writing {uploaded_key} key into JSON metadata...")
            try:
                target_json_data[uploaded_key] = True
                updated_json_path = tmp_path / f"updated_{target_json['name']}"
                with open(updated_json_path, "w", encoding="utf-8") as f:
                    json.dump(target_json_data, f, indent=4, ensure_ascii=False)
                    
                media = MediaFileUpload(str(updated_json_path), mimetype="application/json")
                drive.files().update(
                    fileId=target_json["id"],
                    media_body=media
                ).execute()
                logging.info(f"Successfully marked as uploaded for {platform_name}.")
            except Exception as e:
                logging.error(f"Failed to update JSON file on Drive: {e}")

