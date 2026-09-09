#!/usr/bin/env python3
import os
import sys
import json
import concurrent.futures
from pathlib import Path

# Ensure we're in the right working directory or adjust sys.path
sys.path.insert(0, str(Path(__file__).parent))

from google import genai
from google.genai import types

def process_metadata(md_path, client):
    json_path = md_path.with_name("metadata.json")
    if json_path.exists():
        print(f"Skipping {md_path}, JSON already exists.")
        return

    print(f"Processing {md_path}")
    try:
        md_content = md_path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"Error reading {md_path}: {e}")
        return

    prompt = f"""
You are an expert content formatter.
Read the following markdown text that contains metadata for a YouTube video and a LinkedIn post.
Extract the information into a strict JSON format with the exact following schema:
{{
    "youtube": {{
        "title": "A suitable title for the YouTube video",
        "description": "The description text for YouTube (excluding tags)",
        "tags": ["tag1", "tag2"]
    }},
    "linkedin": {{
        "post": "The text of the LinkedIn post (excluding tags)",
        "tags": ["tag1", "tag2"]
    }}
}}

Make sure to extract hashtags into the 'tags' arrays without the '#' symbol.

Markdown content:
{md_content}
"""

    try:
        resp = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            )
        )
        
        # Parse JSON to ensure it is valid
        data = json.loads(resp.text)
        
        # Save it formatted
        json_path.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")
        print(f"✅ Successfully created {json_path}")
    except Exception as e:
        print(f"❌ Error processing {md_path}: {e}")

def main():
    try:
        client = genai.Client(vertexai=True, location="us-central1")
    except Exception as e:
        print("Failed to initialize Google Cloud. Did you run 'gcloud auth application-default login'?")
        raise e

    base_dir = Path("generated/powerpoints")
    if not base_dir.exists():
        print(f"Directory {base_dir} does not exist.")
        return

    md_files = list(base_dir.rglob("metadata.md"))
    print(f"Found {len(md_files)} metadata.md files.")

    max_workers = 5
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(process_metadata, md_path, client) 
            for md_path in md_files
        ]
        concurrent.futures.wait(futures)

if __name__ == "__main__":
    main()
