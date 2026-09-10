import json
import logging
import os
import random
import tempfile
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

def process_htmlcss_upload(platform_name, upload_type, upload_func, extract_metadata_func):
    load_env()
    drive = get_drive_service()
    if not drive:
        return

    folder_url = os.environ.get("HTMLCSS_MEDIA_FOLDER")
    if not folder_url:
        logging.error("HTMLCSS_MEDIA_FOLDER not found in environment")
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
    target_files_to_download = []
    target_metadata_file = None
    target_json_data = None

    uploaded_key = f"{platform_name}_uploaded_{upload_type}"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        for subfolder in subfolders:
            res = drive.files().list(
                q=f"'{subfolder['id']}' in parents",
                fields="files(id, name)"
            ).execute()
            files = res.get("files", [])
            
            meta_file = next((f for f in files if f["name"] == "metadata.json"), None)
            if not meta_file:
                continue
                
            json_path = tmp_path / f"{subfolder['id']}_metadata.json"
            try:
                request = drive.files().get_media(fileId=meta_file["id"])
                with open(json_path, "wb") as f:
                    downloader = MediaIoBaseDownload(f, request)
                    done = False
                    while not done:
                        status, done = downloader.next_chunk()
                        
                with open(json_path, "r", encoding="utf-8") as f:
                    meta_json = json.load(f)
                    
                if not meta_json.get(uploaded_key):
                    # Find required images based on type
                    images = []
                    if upload_type == "carousel":
                        # find all ig_slide_X.jpg
                        slide_files = [f for f in files if f["name"].startswith("ig_slide_") and f["name"].endswith(".jpg")]
                        # Sort them by the number in the name
                        slide_files.sort(key=lambda x: int(''.join(filter(str.isdigit, x["name"]))))
                        images = slide_files
                    elif upload_type == "poster":
                        # find linkedin_poster.jpg
                        poster_file = next((f for f in files if f["name"] == "linkedin_poster.jpg"), None)
                        if poster_file:
                            images = [poster_file]
                            
                    if images:
                        target_subfolder = subfolder
                        target_metadata_file = meta_file
                        target_json_data = meta_json
                        target_files_to_download = images
                        break
            except Exception as e:
                logging.error(f"Failed to process {meta_file['name']}: {e}")
                continue

        if not target_subfolder:
            logging.info(f"No unprocessed '{upload_type}' items found for platform '{platform_name}'.")
            return

        logging.info(f"Selected subfolder '{target_subfolder['name']}'")
        
        downloaded_paths = []
        for file_info in target_files_to_download:
            file_path = tmp_path / file_info["name"]
            logging.info(f"Downloading {file_info['name']}...")
            try:
                request = drive.files().get_media(fileId=file_info["id"])
                with open(file_path, "wb") as f:
                    downloader = MediaIoBaseDownload(f, request)
                    done = False
                    while not done:
                        status, done = downloader.next_chunk()
                downloaded_paths.append(file_path)
            except Exception as e:
                logging.error(f"Failed to download image {file_info['name']}: {e}")
                return
            
        try:
            content = extract_metadata_func(target_json_data)
        except Exception as e:
            logging.error(f"Failed to extract metadata: {e}")
            return
            
        logging.info(f"Uploading to {platform_name}...")
        success = False
        try:
            if upload_type == "carousel":
                upload_func(downloaded_paths, content)
            else:
                # poster might be expected as a single path or list depending on the upload_func signature.
                # All our publisher funcs except linkedin and facebook_video expect lists for images.
                # Wait, up_poster_linkedin uses linkedin_image which takes a single Path.
                # up_poster_facebook uses facebook which takes a list.
                # Let's check publishers.py
                if platform_name == "linkedin":
                    upload_func(downloaded_paths[0], content)
                else:
                    upload_func(downloaded_paths, content)
            logging.info(f"Successfully uploaded to {platform_name}!")
            success = True
        except Exception as e:
            logging.error(f"Failed to upload to {platform_name}: {e}")

        if success:
            logging.info(f"Writing {uploaded_key} key into JSON metadata...")
            try:
                target_json_data[uploaded_key] = True
                updated_json_path = tmp_path / "updated_metadata.json"
                with open(updated_json_path, "w", encoding="utf-8") as f:
                    json.dump(target_json_data, f, indent=4, ensure_ascii=False)
                    
                media = MediaFileUpload(str(updated_json_path), mimetype="application/json")
                drive.files().update(
                    fileId=target_metadata_file["id"],
                    media_body=media
                ).execute()
                logging.info(f"Successfully marked as uploaded for {platform_name} ({upload_type}).")
            except Exception as e:
                logging.error(f"Failed to update JSON file on Drive: {e}")

