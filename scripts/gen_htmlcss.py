import os
import json
import asyncio
from pathlib import Path
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from google import genai
from google.genai import types
from jinja2 import Environment, FileSystemLoader
from playwright.async_api import async_playwright
from dotenv import load_dotenv

import sys
import re
sys.path.append(str(Path(__file__).parent.parent))
from scripts.common.http import Http
from scripts.common.articles import discover_urls

# Load env vars
load_dotenv()

def format_bullets_filter(text):
    if not text:
        return ""
    # Matches common emojis (like ✅, 👉, 📍), keycap numbers (like 1️⃣), standard numbered lists (like "1. "), AND standard bullets ("•", "-", "*")
    emoji_pattern = re.compile(r'((?:[\u2705\u2611\u2714\ud83d\udccc\ud83d\udccd\ud83d\udc49\ud83d\udca1]|\d\ufe0f?\u20e3|[\u2600-\u27bf]|\ud83c[\udf00-\udfff]|\ud83d[\udc00-\ude4f]|\ud83d[\ude80-\udeff]|\b\d+\.\s+|[•\-*]\s+))\s*')
    parts = emoji_pattern.split(text)
    
    if len(parts) > 1:
        html = ""
        # The first part is text before any bullet
        if parts[0].strip():
            html += f'<div class="intro-text">{parts[0].strip()}</div>'
        html += '<div class="bullet-list">'
        # Iterate through the matched bullets and their following content
        for i in range(1, len(parts), 2):
            bullet = parts[i]
            content = parts[i+1].strip()
            if content:
                html += f'<div class="bullet-item"><span class="bullet-icon">{bullet.strip()}</span><span class="bullet-content">{content}</span></div>'
        html += '</div>'
        return html
    else:
        return text

def parse_markdown_filter(text):
    if not text:
        return ""
    # Convert **bold** to <strong>bold</strong>
    text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', text)
    # Convert *bold* (sometimes AI uses single asterisks for bold despite being told not to) to <strong>bold</strong>
    # But we have to be careful not to match list bullets, so we only match if it's NOT at the start of a line/string
    text = re.sub(r'(?<!^)(?<!\n)\*([^\*]+)\*', r'<strong>\1</strong>', text)
    return text

BRAND_VARS = {
    "BRAND_NAME": os.environ.get("BRAND_NAME", "Brand"),
    "BRAND_SITE": os.environ.get("BRAND_SITE", "website.com"),
    "BRAND_COLOR_NAVY": os.environ.get("BRAND_COLOR_NAVY", "#0c3d6d"),
    "BRAND_COLOR_BLUE": os.environ.get("BRAND_COLOR_BLUE", "#0c88eb"),
    "BRAND_COLOR_TEXT": os.environ.get("BRAND_COLOR_TEXT", "#0f172a"),
    "BRAND_COLOR_CANVAS": os.environ.get("BRAND_COLOR_CANVAS", "#f8fafc"),
    "BRAND_COLOR_BORDER": os.environ.get("BRAND_COLOR_BORDER", "#e2e8f0")
}
ARTICLE_BASE_URL = os.environ.get("ARTICLE_BASE_URL", "https://example.com")

try:
    client = genai.Client(vertexai=True, location="us-central1")
except Exception as e:
    print("❌ Failed to initialize Google Cloud GenAI. Ensure gcloud is authenticated.")
    raise e

def fetch_article_text(http: Http, url: str) -> str:
    response = http.request("GET", url)
    soup = BeautifulSoup(response.text, "html.parser")
    
    root = soup.find("article") or soup.find("main") or soup.find("body")
    if not root:
        return ""
        
    for unwanted in root.select("nav, footer, aside, script, style, form, .share, .related"):
        unwanted.decompose()
        
    heading = root.find("h1") or soup.find("h1")
    title = heading.get_text(" ", strip=True) if heading else ""
    
    parts = []
    if title:
        parts.append(f"# {title}")
        
    for node in root.find_all(["h2", "h3", "p", "li"]):
        text = " ".join(node.get_text(" ", strip=True).split())
        if len(text) >= 20:
            parts.append(text)
            
    return "\n\n".join(parts)


def get_llm_prompt(language: str) -> str:
    lang_name = "English" if language == "en" else "Spanish"
    return f"""
You are an expert Social Media Manager. Analyze the provided blog article and extract highly useful, non-generic information (like specific requirements, precise forms to fill, where to book appointments). DO NOT include generic advice like "read instructions".

IMPORTANT FORMATTING RULE FOR CAROUSEL SLIDES:
If you are generating a list of items for a carousel slide's body, you MUST format them clearly. You MUST start EVERY single list item with the EXACT character "• " (a bullet point followed by a space). Do NOT use emojis, do NOT use numbers, do NOT use a single running paragraph. 

Generate the content in {lang_name} and output a strict JSON object matching this EXACT schema:
{{
    "instagram": {{
        "carousel_post_description": "Emoji-rich engaging description specifically tailored for the carousel (in {lang_name}). Distinct content.",
        "poster_post_description": "Emoji-rich engaging description specifically tailored for the poster (in {lang_name}). Use different words from the carousel description.",
        "hashtags": ["#tag1", "#tag2"],
        "poster_title": "Short Hook Title (in {lang_name})",
        "poster_quote": "A powerful, specific quote or key takeaway extracted from the article (in {lang_name}).",
        "carousel_slides": [
            {{"title": "Slide 1 Title (in {lang_name})", "body": "Specific detailed info (in {lang_name})."}}
        ]
    }},
    "linkedin": {{
        "carousel_post_description": "Professional insightful post specifically tailored for the carousel (in {lang_name}). Distinct content.",
        "poster_post_description": "Professional insightful post specifically tailored for the poster (in {lang_name}). Use different words from the carousel description.",
        "hashtags": ["#tag1", "#tag2"],
        "poster_title": "Short Hook Title (in {lang_name})",
        "poster_quote": "A powerful, specific quote or key takeaway extracted from the article (in {lang_name}).",
        "carousel_slides": [
            {{"title": "Slide 1 Title (in {lang_name})", "body": "Specific detailed info (in {lang_name})."}}
        ]
    }},
    "facebook": {{
        "carousel_post_description": "Conversational post specifically tailored for the carousel (in {lang_name}). Distinct content.",
        "poster_post_description": "Conversational post specifically tailored for the poster (in {lang_name}). Use different words from the carousel description.",
        "hashtags": ["#tag1", "#tag2"],
        "poster_title": "Short Hook Title (in {lang_name})",
        "poster_quote": "A powerful, specific quote or key takeaway extracted from the article (in {lang_name}).",
        "carousel_slides": [
            {{"title": "Slide 1 Title (in {lang_name})", "body": "Specific detailed info (in {lang_name})."}}
        ]
    }},
    "tiktok": {{
        "carousel_post_description": "Hook-driven description specifically tailored for the carousel (in {lang_name}). Distinct content.",
        "poster_post_description": "Hook-driven description specifically tailored for the poster (in {lang_name}). Use different words from the carousel description.",
        "hashtags": ["#tag1", "#tag2"],
        "poster_title": "Short Hook Title (in {lang_name})",
        "poster_quote": "A powerful, specific quote or key takeaway extracted from the article (in {lang_name}).",
        "carousel_slides": [
            {{"title": "Slide 1 Title (in {lang_name})", "body": "Specific detailed info (in {lang_name})."}}
        ]
    }}
}}
"""

async def generate_social_content(text: str, language: str) -> dict:
    prompt = get_llm_prompt(language)
    response = await client.aio.models.generate_content(
        model='gemini-2.5-pro',
        contents=f"{prompt}\n\nArticle Text:\n{text}",
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
        )
    )
    return json.loads(response.text)


async def render_html_to_image(page, html_path: Path, output_jpg: Path):
    await page.goto(f"file://{html_path.absolute()}")
    # Wait a tiny bit for fonts to load
    await page.wait_for_timeout(500)
    await page.screenshot(path=str(output_jpg), type="jpeg", quality=90, full_page=True)


async def process_url(browser, url: str, language: str, output_base: Path):
    parsed_path = urlparse(url).path
    article_slug = parsed_path.strip("/").split("/")[-1]
    if not article_slug:
        return
        
    target_dir = output_base / language / article_slug
    if target_dir.exists() and (target_dir / "metadata.json").exists():
        try:
            with open(target_dir / "metadata.json", "r", encoding="utf-8") as f:
                content_json = json.load(f)
                
            has_poster = (target_dir / "linkedin_poster.jpg").exists() if "linkedin" in content_json else True
            
            has_slides = True
            if "instagram" in content_json and "carousel_slides" in content_json["instagram"]:
                for i in range(len(content_json["instagram"]["carousel_slides"])):
                    if not (target_dir / f"ig_slide_{i+1}.jpg").exists():
                        has_slides = False
                        break
                        
            if has_poster and has_slides:
                print(f"⏭️ Skipping {article_slug} ({language}) - already exists.")
                return
        except Exception:
            pass
        
    print(f"⏳ Processing {article_slug} ({language})...")
    
    # 1. Scrape
    http = Http()
    text = await asyncio.to_thread(fetch_article_text, http, url)
    if not text or len(text) < 200:
        print(f"⚠️ Not enough content for {article_slug}")
        return
        
    # 2. Extract with Gemini
    try:
        content_json = await generate_social_content(text, language)
    except Exception as e:
        print(f"❌ LLM error on {article_slug}: {e}")
        return
        
    target_dir.mkdir(parents=True, exist_ok=True)
    
    # 3. Save metadata
    with open(target_dir / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(content_json, f, indent=4, ensure_ascii=False)
        
    # 4. Jinja templating
    env = Environment(loader=FileSystemLoader(str(Path(__file__).parent / "assets")))
    env.filters["format_bullets"] = format_bullets_filter
    env.filters["parse_markdown"] = parse_markdown_filter
    poster_tpl = env.get_template("poster.html")
    carousel_tpl = env.get_template("carousel_slide.html")
    
    page = await browser.new_page(viewport={"width": 1080, "height": 1350})
    
    try:
        # Generate LinkedIn Poster
        if "linkedin" in content_json:
            li_data = content_json["linkedin"]
            html_content = poster_tpl.render(
                language=language,
                title=li_data.get("poster_title", "Insight"),
                quote=li_data.get("poster_quote", ""),
                **BRAND_VARS
            )
            html_file = target_dir / "linkedin_poster.html"
            html_file.write_text(html_content, encoding="utf-8")
            await render_html_to_image(page, html_file, target_dir / "linkedin_poster.jpg")
            
        # Generate Instagram Carousel
        if "instagram" in content_json and "carousel_slides" in content_json["instagram"]:
            slides = content_json["instagram"]["carousel_slides"]
            total = len(slides)
            for i, slide in enumerate(slides):
                html_content = carousel_tpl.render(
                    language=language,
                    slide_index=i+1,
                    total_slides=total,
                    title=slide.get("title", ""),
                    body=slide.get("body", ""),
                    **BRAND_VARS
                )
                html_file = target_dir / f"ig_slide_{i+1}.html"
                html_file.write_text(html_content, encoding="utf-8")
                await render_html_to_image(page, html_file, target_dir / f"ig_slide_{i+1}.jpg")
                
        print(f"✅ Generated {article_slug} ({language})")
    finally:
        await page.close()


async def main(args=None):
    output_base = Path("generated/htmlcss")
    sitemap_url = f"{ARTICLE_BASE_URL.rstrip('/')}/sitemap.xml"
    
    http = Http()
    tasks_data = []
    for lang in ["en", "es"]:
        urls = discover_urls(sitemap_url, lang, http)
        for u in urls:
            tasks_data.append((u, lang))
            
    print(f"🚀 Found {len(tasks_data)} total URLs to process.")
    
    if args and args.process_n:
        tasks_data = tasks_data[:args.process_n]
        print(f"⚠️ Limiting execution to {len(tasks_data)} URLs as requested by --process-n.")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        
        # We can run in chunks to avoid overwhelming Playwright / Gemini
        chunk_size = 10
        for i in range(0, len(tasks_data), chunk_size):
            chunk = tasks_data[i:i+chunk_size]
            coroutines = [process_url(browser, url, lang, output_base) for url, lang in chunk]
            await asyncio.gather(*coroutines)
            
        await browser.close()
        
    print("🎉 All done!")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate social media assets.")
    parser.add_argument("--process-n", type=int, help="Limit the number of URLs to process")
    args = parser.parse_args()
    
    asyncio.run(main(args))
