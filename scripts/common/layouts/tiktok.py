import textwrap
from PIL import Image, ImageDraw, ImageFont
from ..config import branding

def create_tiktok_poster(title, description, top_label, output_path, is_centered=False):
    """Generates a purely programmatic vector-style poster using Pillow."""
    width, height = 1080, 1920
    
    # Base background (Dark Blue)
    img = Image.new('RGB', (width, height), color=(12, 61, 109))
    draw = ImageDraw.Draw(img)
    
    # Draw geometric accents to make it look professional and designed
    # Accent 1: Top right vivid blue circle
    draw.ellipse([width - 500, -200, width + 300, 600], fill=(12, 136, 235))
    
    # Accent 2: Bottom left dark slate circle
    draw.ellipse([-400, height - 700, 400, height + 100], fill=(15, 23, 42))
    
    # Accent 3: Small decorative circle
    draw.ellipse([width - 150, height - 400, width - 50, height - 300], fill=(255, 200, 50))

    # Load fonts
    font_path = branding().font_path
    if not font_path:
        import sys
        font_path = "/System/Library/Fonts/Supplemental/Arial.ttf" if sys.platform == "darwin" else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        
    import os
    if not os.path.exists(font_path):
        font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf" if os.path.exists("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf") else ""
        
    try:
        font_title = ImageFont.truetype(font_path, 85) if font_path else ImageFont.load_default()
        font_desc = ImageFont.truetype(font_path, 55) if font_path else ImageFont.load_default()
        font_top = ImageFont.truetype(font_path, 45) if font_path else ImageFont.load_default()
        font_footer = ImageFont.truetype(font_path, 40) if font_path else ImageFont.load_default()
    except Exception as e:
        print(f"Warning: Could not load custom font, using default. ({e})")
        font_title = ImageFont.load_default()
        font_desc = ImageFont.load_default()
        font_top = ImageFont.load_default()
        font_footer = ImageFont.load_default()

    px = 100
    y_text = 500 if is_centered else 300

    # 1. Draw Top Label
    if top_label:
        draw.text((px, y_text), top_label, fill=(255, 200, 50), font=font_top)
        y_text += 100

    # 2. Draw Title
    title_lines = textwrap.wrap(title, width=18)
    for line in title_lines:
        draw.text((px, y_text), line, fill=(255, 255, 255), font=font_title)
        y_text += 100

    # Draw separator line
    y_text += 40
    draw.line([px, y_text, px + 200, y_text], fill=(12, 136, 235), width=10)
    y_text += 80

    # 3. Draw Description
    if description:
        desc_lines = textwrap.wrap(description, width=28)
        for line in desc_lines:
            draw.text((px, y_text), line, fill=(220, 220, 220), font=font_desc)
            y_text += 75

    # 4. Draw Footer
    draw.text((px, height - 150), branding().name, fill=(255, 255, 255), font=font_footer)

    img.save(output_path)
