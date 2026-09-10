#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.common.publishers import facebook
from scripts.common.poster_uploader import process_poster_upload

def extract_metadata(meta_json):
    caption = meta_json.get("facebook", "")
    hashtags = meta_json.get("tags", "")
    return f"{caption}\n\n{hashtags}".strip()

def upload_func(image_path, caption):
    facebook([image_path], caption)

if __name__ == "__main__":
    process_poster_upload("facebook", upload_func, extract_metadata)
