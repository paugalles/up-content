import textwrap
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from ..config import branding

class YoutubeSlideGenerator:
    def __init__(self, config: dict):
        self.w, self.h = config['video']['resolution']
        self.config = config

    def generate_image(self, scene, output_path: str):
        img = Image.new('RGB', (self.w, self.h), (248, 250, 252))

        glow_layer = Image.new('RGBA', (self.w, self.h), (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow_layer)
        glow_draw.ellipse(
            [self.w * 0.52, -self.h * 0.35, self.w * 1.12, self.h * 0.55],
            fill=(191, 219, 254, 145),
        )
        glow_draw.ellipse(
            [-self.w * 0.18, self.h * 0.70, self.w * 0.32, self.h * 1.25],
            fill=(186, 230, 253, 105),
        )
        glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=95))
        img = Image.alpha_composite(img.convert('RGBA'), glow_layer).convert('RGB')
        draw = ImageDraw.Draw(img)

        draw.rectangle([0, 0, self.w, 12], fill=(12, 136, 235))
        if not scene.is_title:
            draw.rounded_rectangle(
                [65, 255, self.w - 65, self.h - 55],
                radius=42,
                fill=(255, 255, 255),
                outline=(226, 232, 240),
                width=3,
            )
        
        font_path = branding().font_path or "/System/Library/Fonts/Supplemental/Arial.ttf"
        
        title_font = ImageFont.truetype(font_path, 90)
        main_title_font = ImageFont.truetype(font_path, 130)
        subtitle_font = ImageFont.truetype(font_path, 65)
        body_font = ImageFont.truetype(font_path, 50)
        
        title_color = (12, 61, 109)
        accent_color = (12, 136, 235)
        body_color = (15, 23, 42)
        
        def draw_wrapped_text(draw, text, font, x, y, width, fill, align="left", bullet=False):
            items_to_draw = [text]
            if bullet and "•" in text:
                items_to_draw = [t.strip() for t in text.split("•") if t.strip()]
                
            current_y = y
            
            for item in items_to_draw:
                lines = textwrap.wrap(item, width=width)
                for i, line in enumerate(lines):
                    bbox = draw.textbbox((0,0), line, font=font)
                    line_w = bbox[2] - bbox[0]
                    line_h = bbox[3] - bbox[1]
                    draw_x = x
                    if align == "center":
                        draw_x = x - (line_w // 2)
                        
                    if bullet and i == 0:
                        r = 8
                        cy = current_y + (line_h // 2) + 5
                        cx = draw_x - 30
                        draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=fill)
                        
                    draw.text((draw_x, current_y), line, font=font, fill=fill)
                    current_y += line_h + 15
                current_y += 30
            return current_y

        if scene.is_title:
            draw_wrapped_text(draw, scene.slide_title, main_title_font, self.w//2, self.h//2 - 150, 25, title_color, align="center")
            if scene.slide_body:
                draw_wrapped_text(draw, scene.slide_body, subtitle_font, self.w//2, self.h//2 + 50, 45, accent_color, align="center")
        else:
            draw_wrapped_text(draw, scene.slide_title, title_font, 100, 60, 40, title_color, align="left")
            
            try:
                import json
                data = json.loads(scene.slide_body)
            except:
                data = {"type": "bullets", "items": [{"title": "", "content": scene.slide_body}]}
            
            if data.get("type") == "chart":
                import matplotlib.pyplot as plt
                import io
                
                fig, ax = plt.subplots(figsize=(12, 5), dpi=120)
                labels = data.get("labels", [])
                values = data.get("values", [])
                
                chart_type = data.get("chart_type", "bar")
                if chart_type == "pie":
                    ax.pie(values, labels=labels, autopct='%1.1f%%', colors=['#0C88EB', '#F59E0B', '#10B981', '#14B8A6'])
                elif chart_type == "line":
                    ax.plot(labels, values, color='#0C88EB', marker='o', linewidth=3, markersize=8)
                else:
                    ax.bar(labels, values, color='#0C88EB')
                    
                ax.set_title(data.get("title", ""), fontsize=20, color='#0F172A')
                fig.tight_layout()
                
                buf = io.BytesIO()
                fig.savefig(buf, format='png', transparent=True)
                buf.seek(0)
                plt.close(fig)
                
                chart_img = Image.open(buf).convert("RGBA")
                img.paste(chart_img, (150, 300), chart_img)
                
            elif data.get("type") == "process":
                steps = data.get("steps", [])
                num_steps = len(steps)
                if num_steps > 0:
                    import textwrap
                    
                    spacing = 50
                    start_x = 100
                    start_y = 350
                    box_h = 400
                    
                    box_w = int((self.w - (start_x * 2) - (num_steps - 1) * spacing) / num_steps)
                    
                    step_font = ImageFont.truetype(branding().font_path or "/System/Library/Fonts/Supplemental/Arial.ttf", 40)
                    
                    for i, step_text in enumerate(steps):
                        x1 = start_x + i * (box_w + spacing)
                        y1 = start_y
                        x2 = x1 + box_w
                        y2 = y1 + box_h
                        
                        draw.rounded_rectangle([x1, y1, x2, y2], radius=25, fill=(12, 136, 235), outline=(12, 61, 109), width=5)
                        
                        chars_per_line = max(10, int(box_w / 22)) 
                        lines = textwrap.wrap(step_text, width=chars_per_line)
                        
                        total_h = 0
                        line_heights = []
                        for line in lines:
                            bbox = draw.textbbox((0,0), line, font=step_font)
                            lh = bbox[3] - bbox[1]
                            line_heights.append(lh)
                            total_h += lh
                        total_h += (len(lines) - 1) * 15
                        
                        curr_y = y1 + (box_h - total_h) // 2
                        
                        for idx, line in enumerate(lines):
                            bbox = draw.textbbox((0,0), line, font=step_font)
                            line_w = bbox[2] - bbox[0]
                            draw.text((x1 + (box_w - line_w) // 2, curr_y), line, font=step_font, fill=(255, 255, 255))
                            curr_y += line_heights[idx] + 15
                            
                        if i < num_steps - 1:
                            arrow_x_start = x2 + 5
                            arrow_x_end = arrow_x_start + spacing - 10
                            arrow_y = y1 + box_h // 2
                            
                            draw.line([(arrow_x_start, arrow_y), (arrow_x_end, arrow_y)], fill=(15, 23, 42), width=8)
                            draw.polygon([(arrow_x_end, arrow_y), (arrow_x_end - 15, arrow_y - 15), (arrow_x_end - 15, arrow_y + 15)], fill=(15, 23, 42))
                            
            else:
                items = data.get("items", [])
                if not items:
                    raw_text = scene.slide_body
                    if "•" in raw_text:
                        items = [{"title": "", "content": t.strip()} for t in raw_text.split("•") if t.strip()]
                    else:
                        items = [{"title": "", "content": raw_text}]
                
                start_y = 300
                for item in items:
                    t = item.get("title", "")
                    c = item.get("content", "")
                    text = f"{t}: {c}" if t and c else f"{t}{c}"
                    
                    start_y = draw_wrapped_text(draw, text, body_font, 150, start_y, 65, body_color, align="left", bullet=True)
                    start_y += 30
                
        img.save(output_path)
