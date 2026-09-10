#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.common.publishers import tiktok
from scripts.common.htmlcss_uploader import process_htmlcss_upload

def extract_metadata(meta_json):
    platform_data = meta_json.get("tiktok", {})
    caption = platform_data.get("poster_post_description", "")
    hashtags = platform_data.get("hashtags", [])
    tags_str = " ".join([t if t.startswith("#") else f"#{t}" for t in hashtags])
    return f"{caption}\n\n{tags_str}".strip()

def upload_func(image_paths, caption):
    tiktok(image_paths, caption)

if __name__ == "__main__":
    process_htmlcss_upload("tiktok", "poster", upload_func, extract_metadata)
