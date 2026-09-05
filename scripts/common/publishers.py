import json
import os
import subprocess
import time
import uuid
from datetime import timedelta
from pathlib import Path

from .config import GRAPH, LINKEDIN, TIKTOK, require
from .http import Http


def poll(fetch, complete, label, attempts=20, delay=3, failed=lambda _: False):
    for _ in range(attempts):
        value = fetch()
        if complete(value): return value
        if failed(value): raise RuntimeError(f"{label} failed: {value}")
        time.sleep(delay)
    raise TimeoutError(f"Timed out waiting for {label}")


def instagram(assets: list[Path], caption: str, http=Http()):
    env = require("INSTAGRAM_ACCOUNT_ID", "META_ACCESS_TOKEN")
    
    children = []
    for path in assets:
        with path.open("rb") as f:
            resp = http.json("POST", "https://uguu.se/upload", files={"files[]": f})
        url = resp["files"][0]["url"]
        
        child = http.json("POST", f"{GRAPH}/{env['INSTAGRAM_ACCOUNT_ID']}/media", data={"image_url": url, "is_carousel_item": "true", "access_token": env["META_ACCESS_TOKEN"]})["id"]
        poll(lambda: http.json("GET", f"{GRAPH}/{child}", params={"fields": "status_code", "access_token": env["META_ACCESS_TOKEN"]}), lambda x: x.get("status_code") == "FINISHED", "Instagram child", failed=lambda x: x.get("status_code") in {"ERROR", "EXPIRED"})
        children.append(child)
        
    parent = http.json("POST", f"{GRAPH}/{env['INSTAGRAM_ACCOUNT_ID']}/media", data={"media_type": "CAROUSEL", "children": ",".join(children), "caption": caption, "access_token": env["META_ACCESS_TOKEN"]})["id"]
    poll(lambda: http.json("GET", f"{GRAPH}/{parent}", params={"fields": "status_code", "access_token": env["META_ACCESS_TOKEN"]}), lambda x: x.get("status_code") == "FINISHED", "Instagram carousel", failed=lambda x: x.get("status_code") in {"ERROR", "EXPIRED"})
    
    return http.json("POST", f"{GRAPH}/{env['INSTAGRAM_ACCOUNT_ID']}/media_publish", data={"creation_id": parent, "access_token": env["META_ACCESS_TOKEN"]})["id"]


def facebook(assets: list[Path], caption: str, http=Http()):
    env = require("FACEBOOK_PAGE_ACCESS_TOKEN")
    
    # Facebook requires uploading photos individually as unpublished, then attaching them to a post
    attached_media = []
    for path in assets:
        # Instead of `files`, upload the image via a presigned-like temporary URL to bypass multipart quirks,
        # or we can use the same temporary upload server `uguu.se` that the instagram publisher is using.
        with path.open("rb") as f:
            resp = http.json("POST", "https://uguu.se/upload", files={"files[]": f})
        url = resp["files"][0]["url"]
        
        # Now submit the URL directly to Facebook using `/me/photos` to avoid ID resolution errors
        resp = http.json("POST", f"{GRAPH}/me/photos", data={"url": url, "published": "false", "access_token": env["FACEBOOK_PAGE_ACCESS_TOKEN"]})
        attached_media.append({"media_fbid": str(resp["id"])})
            
    # Create a multi-photo post by attaching the uploaded media
    return http.json("POST", f"{GRAPH}/me/feed", data={"message": caption, "attached_media": json.dumps(attached_media), "access_token": env["FACEBOOK_PAGE_ACCESS_TOKEN"]})["id"]


def facebook_video(asset: Path, caption: str, http=Http()):
    env = require("FACEBOOK_PAGE_ACCESS_TOKEN")
    
    with asset.open("rb") as f:
        resp = http.json("POST", "https://uguu.se/upload", files={"files[]": f})
    url = resp["files"][0]["url"]
    
    resp = http.json("POST", f"{GRAPH}/me/videos", data={
        "file_url": url, 
        "description": caption, 
        "access_token": env["FACEBOOK_PAGE_ACCESS_TOKEN"]
    })
    return resp.get("id", "uploaded")


def youtube(asset: Path, content: dict):
    env = require("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN")
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    credentials = Credentials(None, refresh_token=env["YOUTUBE_REFRESH_TOKEN"], token_uri="https://oauth2.googleapis.com/token", client_id=env["YOUTUBE_CLIENT_ID"], client_secret=env["YOUTUBE_CLIENT_SECRET"], scopes=["https://www.googleapis.com/auth/youtube.upload"])
    request = build("youtube", "v3", credentials=credentials, cache_discovery=False).videos().insert(part="snippet,status", body={"snippet": {"title": content["title"][:100], "description": content["caption"], "tags": [x.lstrip("#") for x in content["hashtags"]]}, "status": {"privacyStatus": os.getenv("YOUTUBE_PRIVACY_STATUS") or "public", "selfDeclaredMadeForKids": False}}, media_body=MediaFileUpload(str(asset), mimetype="video/mp4", resumable=True))
    response = None
    failures = 0
    while response is None:
        try:
            _, response = request.next_chunk()
            failures = 0
        except Exception:
            failures += 1
            if failures >= 4: raise
            time.sleep(min(8, 2 ** (failures - 1)))
    return response["id"]


def tiktok(assets: list[Path], caption: str, http=Http()):
    token = require("TIKTOK_ACCESS_TOKEN")["TIKTOK_ACCESS_TOKEN"]
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"}
    creator = http.json("POST", f"{TIKTOK}/post/publish/creator_info/query/", headers=headers, json={})["data"]
    privacy = os.getenv("TIKTOK_PRIVACY_LEVEL") or "SELF_ONLY"
    if privacy not in creator.get("privacy_level_options", []): raise RuntimeError(f"TIKTOK_PRIVACY_LEVEL {privacy} is not available")
    
    photo_images = []
    for asset in assets:
        size = asset.stat().st_size
        photo_images.append({"image_size": size, "chunk_size": size, "total_chunk_count": 1})
        
    data = http.json("POST", f"{TIKTOK}/post/publish/video/init/", headers=headers, json={
        "post_info": {
            "title": caption[:2200], 
            "privacy_level": privacy, 
            "disable_duet": False, 
            "disable_comment": False, 
            "disable_stitch": False,
            "music": "Education"
        }, 
        "source_info": {
            "source": "FILE_UPLOAD", 
            "photo_cover_index": 1,
            "photo_images": photo_images
        }
    })["data"]
    
    upload_urls = data.get("upload_urls") or [img.get("upload_url") for img in data.get("photo_images", [])]
    if not upload_urls and "upload_url" in data:
        upload_urls = [data["upload_url"]]
        
    for i, asset in enumerate(assets):
        if i < len(upload_urls):
            size = asset.stat().st_size
            with asset.open("rb") as handle: 
                http.request("PUT", upload_urls[i], headers={"Content-Type": "image/jpeg", "Content-Range": f"bytes 0-{size-1}/{size}"}, data=handle)
                
    poll(lambda: http.json("POST", f"{TIKTOK}/post/publish/status/fetch/", headers=headers, json={"publish_id": data["publish_id"]})["data"], lambda x: x.get("status") in {"PUBLISH_COMPLETE", "SEND_TO_USER_INBOX"}, "TikTok post", attempts=30, failed=lambda x: x.get("status") == "FAILED")
    return data["publish_id"]


def linkedin(asset: Path, caption: str, http=Http()):
    env = require("LINKEDIN_ACCESS_TOKEN", "LINKEDIN_ORGANIZATION_ID")
    urn = f"urn:li:organization:{env['LINKEDIN_ORGANIZATION_ID']}"
    headers = {"Authorization": f"Bearer {env['LINKEDIN_ACCESS_TOKEN']}", "LinkedIn-Version": os.getenv("LINKEDIN_VERSION") or "202508", "X-Restli-Protocol-Version": "2.0.0", "Content-Type": "application/json"}
    init = http.json("POST", f"{LINKEDIN}/rest/documents?action=initializeUpload", headers=headers, json={"initializeUploadRequest": {"owner": urn}})["value"]
    with asset.open("rb") as handle: http.request("PUT", init["uploadUrl"], headers={"Authorization": f"Bearer {env['LINKEDIN_ACCESS_TOKEN']}", "Content-Type": "application/pdf"}, data=handle)
    body = {"author": urn, "commentary": caption[:3000], "visibility": "PUBLIC", "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [], "thirdPartyDistributionChannels": []}, "content": {"media": {"title": caption.splitlines()[0][:200], "id": init["document"]}}, "lifecycleState": "PUBLISHED", "isReshareDisabledByAuthor": False}
    response = http.request("POST", f"{LINKEDIN}/rest/posts", headers=headers, json=body)
    return response.headers.get("x-restli-id", "created")
