#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.common.publishers import linkedin
from scripts.common.reel_uploader import process_reel_upload

def extract_metadata(meta_json):
    meta = meta_json.get("linkedin", {})
    if not meta:
        raise ValueError("No linkedin metadata found")
    
    caption = meta.get("post", meta.get("description", ""))
    hashtags = meta.get("tags", [])
    tags_str = " ".join([f"#{t}" if not t.startswith("#") else t for t in hashtags])
    return f"{caption}\n\n{tags_str}".strip()

def upload_func(video_path, caption):
    linkedin(video_path, caption)

if __name__ == "__main__":
    process_reel_upload("linkedin", upload_func, extract_metadata)
