#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.common.publishers import youtube
from scripts.common.reel_uploader import process_reel_upload

def extract_metadata(meta_json):
    yt_meta = meta_json.get("youtube_shorts", meta_json.get("youtube", {}))
    if not yt_meta:
        raise ValueError("No youtube metadata found")
    
    return {
        "title": yt_meta.get("title", ""),
        "caption": yt_meta.get("description", ""),
        "hashtags": yt_meta.get("tags", [])
    }

def upload_func(video_path, content):
    youtube(video_path, content)

if __name__ == "__main__":
    process_reel_upload("youtube", upload_func, extract_metadata, preferred_video_name="reel_youtube.mp4")
