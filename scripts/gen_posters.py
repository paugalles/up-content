import os
import json
import time
import re
import io
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from google import genai
from google.genai import types
from PIL import Image, ImageDraw, ImageFont, ImageOps

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from scripts.common.http import Http
from scripts.common.articles import discover_urls

# Load .env variables
env_file = Path(".env")
if env_file.exists():
    with open(env_file, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                if "=" in line:
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key.strip(), value.strip().strip("'\""))

BRAND_NAME = os.environ.get("BRAND_NAME", "Brand")
BRAND_SITE = os.environ.get("BRAND_SITE", "website.com")
BRAND_COLOR_NAVY = os.environ.get("BRAND_COLOR_NAVY", "#0c3d6d")
BRAND_COLOR_BLUE = os.environ.get("BRAND_COLOR_BLUE", "#0c88eb")
BRAND_COLOR_TEXT = os.environ.get("BRAND_COLOR_TEXT", "#0f172a")
BRAND_COLOR_CANVAS = os.environ.get("BRAND_COLOR_CANVAS", "#f8fafc")
BRAND_COLOR_BORDER = os.environ.get("BRAND_COLOR_BORDER", "#e2e8f0")
ARTICLE_BASE_URL = os.environ.get("ARTICLE_BASE_URL", "https://example.com")

try:
    client = genai.Client(vertexai=True, location="us-central1")
    print("✅ Initialized Vertex AI (via google-genai SDK)")
except Exception as e:
    print("❌ Failed to initialize Google Cloud. Did you run 'gcloud auth application-default login'?")
    raise e


# --- Pillow Helper Functions ---

def get_font(size, bold=False):
    # Try to load the local brand fonts
    base_path = Path(__file__).parent / "assets" / "fonts"
    font_name = "Roboto-Bold.ttf" if bold else "Roboto-Regular.ttf"
    font_path = base_path / font_name
    
    try:
        return ImageFont.truetype(str(font_path), size)
    except:
        # Fallback if local font fails
        try:
            sys_font = "HelveticaNeue-Bold.ttc" if bold else "HelveticaNeue.ttc"
            return ImageFont.truetype(f"/System/Library/Fonts/{sys_font}", size)
        except:
            return ImageFont.load_default()

def textwrap_text(text, font, max_width):
    words = text.split()
    lines = []
    current_line = []
    for word in words:
        test_line = ' '.join(current_line + [word])
        # PIL textbbox returns (left, top, right, bottom)
        tw = font.getbbox(test_line)[2]
        if tw <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(' '.join(current_line))
            current_line = [word]
    if current_line:
        lines.append(' '.join(current_line))
    return lines

def draw_text_centered(draw, text, font, box, fill):
    x1, y1, x2, y2 = box
    w = x2 - x1
    h = y2 - y1
    
    lines = []
    for line in text.split('\n'):
        lines.extend(textwrap_text(line, font, w - 80))
        
    line_heights = [font.getbbox(line)[3] - font.getbbox(line)[1] for line in lines]
    total_height = sum(line_heights) + 15 * (len(lines) - 1)
    
    current_y = y1 + (h - total_height) / 2
    for line, lh in zip(lines, line_heights):
        lw = font.getbbox(line)[2] - font.getbbox(line)[0]
        current_x = x1 + (w - lw) / 2
        draw.text((current_x, current_y), line, font=font, fill=fill)
        current_y += lh + 15


# --- Prompt Generation ---

def hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

def get_system_prompt(language: str):
    lang_name = "English" if language == "en" else "Spanish"
    brand_cta = os.environ.get(f"BRAND_CTA_{language.upper()}", "")
    
    return f"""
You are an expert Social Media Manager. Read the provided blog article and generate the content for an infographic poster.
Generate all text in {lang_name}, matching the language of the article.

The generated text MUST be highly useful and relevant. DO NOT include generic advice (e.g., "have your documentation ready", "read the instructions", or obvious filler). INSTEAD, focus ONLY on relevant and highly specific information such as: exactly what the user will find in the form, specific requirements, and exactly where to book an appointment.

You MUST respond with a valid JSON object containing EXACTLY the following keys:
{{
    "title": "A short, catchy title summarizing the article (max 6 words, in {lang_name}).",
    "image_prompt": "A prompt for an AI image generator to create an illustration ONLY. ABSOLUTELY NO TEXT, NO WORDS, NO LETTERS, NO NUMBERS inside the image. It must be a flat, clean illustration relevant to the article. The background MUST be a completely solid, uniform, untextured fill of exact hex color {BRAND_COLOR_CANVAS}. Use {BRAND_COLOR_NAVY} and {BRAND_COLOR_BLUE} for the illustration accents. The instructions MUST be in English.",
    "sections": [
        {{
            "heading": "Short heading (max 2 words, in {lang_name})",
            "bullets": ["Bullet 1 (max 4 words)", "Bullet 2", "Bullet 3"]
        }}
    ],
    "facebook": "An engaging, conversational post for Facebook (in {lang_name}). End with: {brand_cta}",
    "instagram": "A highly visual, emoji-rich post for Instagram (in {lang_name}). End with: {brand_cta}",
    "x": "A snappy, punchy tweet (under 280 characters, in {lang_name}). End with: {brand_cta}",
    "tiktok": "A hook-driven description for a TikTok video or photo slide (in {lang_name}). End with: {brand_cta}",
    "linkedin": "A professional, value-driven, and insightful post for LinkedIn (in {lang_name}). End with: {brand_cta}",
    "tags": "#List #Of #Relevant #Hashtags (in {lang_name})"
}}

CRITICAL: You MUST provide EXACTLY 2, 3, 4, or 6 sections in the "sections" array. 
CRITICAL: You MUST provide a STRICT MAXIMUM of 3 or 4 bullets per section.
If 2 sections, they will be stacked vertically. If 3, they will be arranged in a 1x3 row. If 4, a 2x2 grid. If 6, a 3x2 grid. Keep bullet points very concise.
"""

def fetch_article_text(http: Http, url: str) -> str:
    response = http.request("GET", url)
    soup = BeautifulSoup(response.text, "html.parser")
    
    root = soup.find("article") or soup.find("main")
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
        text = re.sub(r"\s+", " ", node.get_text(" ", strip=True))
        text = re.sub(r"^H[1-6]:\s*", "", text, flags=re.IGNORECASE)
        if re.match(r"^(?:author|autor|publication date|fecha de publicaci[oó]n)\s*:", text, re.IGNORECASE):
            continue
        if len(text) >= 20:
            parts.append(("## " if node.name in {"h2", "h3"} else "") + text)
            
    return "\n\n".join(parts)


def compose_poster(content_data: dict, ai_image_bytes: bytes, output_path: str, existing_poster_path: str = None):
    """Composes the final 4:5 poster using Pillow."""
    # Dimensions for 4:5 aspect ratio
    W, H = 1080, 1350
    
    # Layout definition
    y_title_start, y_title_end = 0, 180      # ~13%
    y_img_start, y_img_end = 180, 600        # ~31%
    y_content_start, y_content_end = 600, 1270 # ~50%
    y_footer_start, y_footer_end = 1270, 1350  # ~6%
    
    # Create empty canvas or use existing
    if existing_poster_path and os.path.exists(existing_poster_path):
        canvas = Image.open(existing_poster_path).convert("RGB")
        draw = ImageDraw.Draw(canvas)
        # Blank out the previous text areas (top and bottom)
        draw.rectangle([0, 0, W, y_img_start], fill=BRAND_COLOR_CANVAS)
        draw.rectangle([0, y_img_end, W, H], fill=BRAND_COLOR_CANVAS)
    else:
        canvas = Image.new("RGB", (W, H), color=BRAND_COLOR_CANVAS)
        draw = ImageDraw.Draw(canvas)
        
        # 2. Paste AI Image (only if not re-using an existing poster canvas)
        if ai_image_bytes:
            try:
                ai_img = Image.open(io.BytesIO(ai_image_bytes)).convert("RGBA")
                
                # Match the generated background seamlessly with the canvas
                canvas_rgb = hex_to_rgb(BRAND_COLOR_CANVAS)
                
                # Find the most common corner color to identify the AI's generated background
                pixdata = ai_img.load()
                width, height = ai_img.size
                corners = [pixdata[0,0], pixdata[width-1,0], pixdata[0,height-1], pixdata[width-1,height-1]]
                bg_color = max(set(corners), key=corners.count)
                
                # Safely replace all background pixels (including jpeg artifacts) with the EXACT canvas color
                for y in range(height):
                    for x in range(width):
                        r, g, b, a = pixdata[x, y]
                        if abs(r - bg_color[0]) < 25 and abs(g - bg_color[1]) < 25 and abs(b - bg_color[2]) < 25:
                            pixdata[x, y] = (canvas_rgb[0], canvas_rgb[1], canvas_rgb[2], 255)
                
                ai_img = ai_img.convert("RGB")
                
                # Calculate maximum dimensions for the image while keeping clean margins
                img_margin_x = 80
                img_margin_y = 20
                max_img_w = W - (img_margin_x * 2)
                max_img_h = (y_img_end - y_img_start) - (img_margin_y * 2)
                
                # Resize the image IN PLACE to fit within the box without adding any padded borders
                ai_img.thumbnail((max_img_w, max_img_h), Image.Resampling.LANCZOS)
                
                # Center the image safely in its allocated block
                paste_x = (W - ai_img.width) // 2
                paste_y = y_img_start + (y_img_end - y_img_start - ai_img.height) // 2
                canvas.paste(ai_img, (paste_x, paste_y))
            except Exception as e:
                print(f"      [Warning] Could not paste AI image: {e}")

    # 1. Draw Title
    font_title = get_font(60, bold=True)
    draw_text_centered(draw, content_data.get("title", "").upper(), font_title, 
                       (0, y_title_start, W, y_title_end), BRAND_COLOR_NAVY)

    # 3. Draw Sections
    sections = content_data.get("sections", [])
    
    num_sec = len(sections)
    
    if num_sec <= 2:
        cols, rows = 1, 2
        sections = sections[:2]
    elif num_sec == 3:
        cols, rows = 3, 1
    elif num_sec == 4:
        cols, rows = 2, 2
        sections = sections[:4]
    else:
        cols, rows = 3, 2
        sections = sections[:6]

    if cols == 1:
        margin_x, col_spacing = 120, 0
        font_heading = get_font(36, bold=True)
        font_bullet = get_font(32, bold=False)
        pill_pad_x, pill_pad_y = 40, 16
    elif cols == 2:
        margin_x, col_spacing = 60, 40
        font_heading = get_font(30, bold=True)
        font_bullet = get_font(26, bold=False)
        pill_pad_x, pill_pad_y = 24, 14
    else: # cols == 3
        margin_x, col_spacing = 40, 30
        font_heading = get_font(24, bold=True)
        font_bullet = get_font(22, bold=False)
        pill_pad_x, pill_pad_y = 16, 12
        
    row_spacing = 30 if rows > 1 else 0
    slot_w = (W - (margin_x * 2) - (col_spacing * (cols - 1))) / cols
    slot_h = (y_content_end - y_content_start - (row_spacing * (rows - 1))) / rows

    for idx, sec in enumerate(sections):
        r = idx // cols
        c = idx % cols
        
        x1 = margin_x + c * (slot_w + col_spacing)
        y1 = y_content_start + r * (slot_h + row_spacing)
        x2 = x1 + slot_w
        y2 = y1 + slot_h
        cx = (x1 + x2) / 2
        
        # Heading Pill
        heading = sec.get("heading", "").upper()
        hw = font_heading.getbbox(heading)[2] - font_heading.getbbox(heading)[0]
        hh = font_heading.getbbox(heading)[3] - font_heading.getbbox(heading)[1]
        
        pill_w = min(hw + (pill_pad_x * 2), slot_w)
        pill_h = hh + (pill_pad_y * 2)
        
        pill_x1 = cx - (pill_w / 2)
        pill_y1 = y1 + 10
        pill_x2 = cx + (pill_w / 2)
        pill_y2 = pill_y1 + pill_h
        
        draw.rounded_rectangle([pill_x1, pill_y1, pill_x2, pill_y2], radius=pill_h/2, fill=BRAND_COLOR_NAVY)
        text_x = pill_x1 + (pill_w - hw) / 2
        draw.text((text_x, pill_y1 + pill_pad_y), heading, font=font_heading, fill=BRAND_COLOR_CANVAS)
        
        # Bullets
        bullet_y = pill_y2 + 20
        bullets_text_lines = []
        max_w = 0
        for bullet in sec.get("bullets", [])[:4]: # Max 4 bullets
            b_text = f"• {bullet}"
            blines = textwrap_text(b_text, font_bullet, slot_w - 10)
            for i, bline in enumerate(blines):
                lw = font_bullet.getbbox(bline)[2] - font_bullet.getbbox(bline)[0]
                max_w = max(max_w, lw)
                bullets_text_lines.append((bline, i == 0))
        
        # Center the entire block of bullets below the pill
        block_x = cx - (max_w / 2)
        
        for bline, is_first in bullets_text_lines:
            if is_first and bullets_text_lines.index((bline, is_first)) != 0:
                bullet_y += 18 # extra space between bullets
            draw.text((block_x, bullet_y), bline, font=font_bullet, fill=BRAND_COLOR_TEXT)
            bullet_y += font_bullet.getbbox(bline)[3] - font_bullet.getbbox(bline)[1] + 12

    # 4. Draw Footer
    font_footer = get_font(36, bold=True)
    draw_text_centered(draw, BRAND_SITE, font_footer, 
                       (0, y_footer_start, W, y_footer_end), BRAND_COLOR_BLUE)
    
    # Save the final composed image
    canvas.save(output_path, quality=95)


def generate_assets_for_blog(blog_id: str, blog_content: str, language: str, output_dir: str, overwrite_copy: bool = False):
    print(f"\n⏳ Processing Blog: {blog_id} ({language})...")
    
    lang_output_dir = os.path.join(output_dir, language)
    os.makedirs(lang_output_dir, exist_ok=True)
    
    poster_filename = os.path.join(lang_output_dir, f"{blog_id}_poster.jpg")
    json_filename = os.path.join(lang_output_dir, f"{blog_id}_social_copy.json")
    illustration_filename = os.path.join(lang_output_dir, f"{blog_id}_illustration.jpg")
    
    if not overwrite_copy and os.path.exists(poster_filename) and os.path.exists(json_filename):
        print(f"  ⏭️  Skipping: Assets already generated for {blog_id}.")
        return
        
    try:
        print("  - Generating copy and structure (gemini-2.5-flash)...")
        prompt = get_system_prompt(language)
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=f"{prompt}\n\nBlog Article:\n{blog_content}",
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            )
        )
        
        content_data = json.loads(response.text)
        
        with open(json_filename, "w", encoding="utf-8") as f:
            json.dump(content_data, f, indent=4, ensure_ascii=False)
        print(f"  ✅ Saved structure to {json_filename}")

        image_bytes = None
        existing_poster = None
        if overwrite_copy:
            if os.path.exists(illustration_filename):
                print("  - Re-using existing illustration...")
                with open(illustration_filename, "rb") as f:
                    image_bytes = f.read()
            elif os.path.exists(poster_filename):
                print("  - Re-using image from existing poster canvas...")
                existing_poster = poster_filename
                
        if not image_bytes and not existing_poster:
            print("  - Generating illustration (gemini-2.5-flash-image)...")
            imagen_prompt = content_data["image_prompt"]
            try:
                # We use 16:9 so it nicely fits the wide horizontal slot of the poster (1080x338)
                image_response = client.models.generate_content(
                    model='gemini-2.5-flash-image',
                    contents=imagen_prompt,
                    config=types.GenerateContentConfig(
                        response_modalities=["IMAGE"],
                        image_config=types.ImageConfig(
                            aspect_ratio="16:9"
                        )
                    )
                )
                
                if image_response.candidates and image_response.candidates[0].content.parts:
                    for part in image_response.candidates[0].content.parts:
                        if part.inline_data:
                            image_bytes = part.inline_data.data
                            with open(illustration_filename, "wb") as f:
                                f.write(image_bytes)
                            break 
                
                if not image_bytes:
                    print(f"  ⚠️  Model responded but no image was found in the output.")
                    
            except Exception as img_err:
                print(f"  ⚠️  Failed to generate image: {img_err}")

        # Programmatically compose the final poster
        print("  - Composing final poster with Pillow...")
        compose_poster(content_data, image_bytes, poster_filename, existing_poster)
        print(f"  ✅ Saved composed poster to {poster_filename}")

    except Exception as e:
        print(f"  ❌ Error processing {blog_id}: {e}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate posters for blog articles.")
    parser.add_argument("--overwrite-copy", action="store_true", help="Overwrite generated text but keep and re-use existing images.")
    args = parser.parse_args()
    
    OUTPUT_FOLDER = os.path.join("generated", "posters")
    SITEMAP_URL = f"{ARTICLE_BASE_URL.rstrip('/')}/sitemap.xml"
    
    print("🚀 Starting Batch Generation for all articles...")
    http = Http()
    
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def process_url(url, language, output_folder, overwrite_copy):
        try:
            parsed_path = urlparse(url).path
            blog_id = parsed_path.strip("/").split("/")[-1]
            
            # Using a fresh Http instance might be safer for threads
            local_http = Http()
            content = fetch_article_text(local_http, url)
            if not content or len(content) < 200:
                print(f"  ⚠️  Skipping {url}: insufficient content extracted.")
                return
                
            generate_assets_for_blog(blog_id, content, language, output_folder, overwrite_copy=overwrite_copy)
        except Exception as e:
            print(f"  ❌ Error in thread for {url}: {e}")

    tasks = []
    for language in ["en", "es"]:
        print(f"\n--- Fetching {language.upper()} URLs from {SITEMAP_URL} ---")
        urls = discover_urls(SITEMAP_URL, language, http)
        print(f"Found {len(urls)} URLs for {language}.")
        
        for url in urls:
            tasks.append((url, language))
            
    print(f"\n🚀 Processing {len(tasks)} articles concurrently (10 workers)...")
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(process_url, url, lang, OUTPUT_FOLDER, args.overwrite_copy) for url, lang in tasks]
        for future in as_completed(futures):
            pass # wait for all to finish
            
    print(f"\n🎉 Batch generation complete! Check the '{OUTPUT_FOLDER}' folder.")