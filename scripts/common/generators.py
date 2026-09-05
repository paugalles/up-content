import os
import re
import random
import textwrap
import glob
from dataclasses import dataclass
from typing import List, Dict, Optional
from pathlib import Path

from openai import OpenAI
from moviepy.editor import AudioFileClip, CompositeAudioClip, CompositeVideoClip, ImageClip, concatenate_audioclips
import moviepy.audio.fx.all as afx

from .articles import Article
from .config import branding

class Scene:
    def __init__(self, spoken_text: str, slide_title: str, slide_body: str, is_title: bool = False):
        self.spoken_text = spoken_text
        self.slide_title = slide_title
        self.slide_body = slide_body
        self.is_title = is_title

class NarrationGenerator:
    def generate_scenes(self, article: Article) -> List[Scene]:
        lang = article.language
        brand = branding().watermark_text if hasattr(branding(), 'watermark_text') else branding().name
        cta_text = branding().cta_es if lang == 'es' else branding().cta_en
        
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        
        if lang == 'es':
            intro = f"Hola y bienvenidos. Hoy hablaremos sobre: {article.title}. Este video llega gracias a {brand}."
            outro = f"Nota: Este video es informativo y no constituye asesoramiento legal. Gracias por ver. {cta_text}"
        elif lang == 'en':
            intro = f"Hello and welcome. Today we are talking about: {article.title}. This video is brought to you by {brand}."
            outro = f"Note: This video is for informational purposes and does not constitute legal advice. Thanks for watching. {cta_text}"
        else:
            base_intro = f"Hello and welcome. Today we are talking about: {article.title}. This video is brought to you by {brand}."
            base_outro = f"Note: This video is for informational purposes and does not constitute legal advice. Thanks for watching. {cta_text}"
            try:
                sys_msg = {"role": "system", "content": f"Translate the following text into the language '{lang}'. Output ONLY the translated text, nothing else."}
                res_intro = client.chat.completions.create(model="gpt-4o-mini", messages=[sys_msg, {"role": "user", "content": base_intro}], max_tokens=100)
                intro = res_intro.choices[0].message.content.strip()
                res_outro = client.chat.completions.create(model="gpt-4o-mini", messages=[sys_msg, {"role": "user", "content": base_outro}], max_tokens=100)
                outro = res_outro.choices[0].message.content.strip()
            except Exception:
                intro = base_intro
                outro = base_outro
            
        scenes = []
        scenes.append(Scene(spoken_text=intro, slide_title=article.title, slide_body="", is_title=True))
        
        grouped_sections = []
        current_group = {"heading": "", "paragraphs": []}
        
        lines = article.text.split('\n')
        for line in lines:
            line = line.strip()
            if not line: continue
            clean_line = re.sub(r"^[-*]\s*", "", line)
            if re.match(r"^(?:author|autor|publication date|fecha de publicaci[oó]n)\s*:", clean_line, re.IGNORECASE):
                continue
            if line.startswith('##'):
                if current_group["heading"] or current_group["paragraphs"]:
                    grouped_sections.append(current_group)
                current_group = {"heading": line.replace('##', '').strip(), "paragraphs": []}
            elif line.startswith('#'):
                continue
            else:
                current_group["paragraphs"].append(line)
                
        if current_group["heading"] or current_group["paragraphs"]:
            grouped_sections.append(current_group)
            
        for group in grouped_sections:
            heading = group["heading"]
            paragraphs_text = " ".join(group["paragraphs"])
            
            if not paragraphs_text and heading:
                scenes.append(Scene(spoken_text=heading, slide_title=heading, slide_body="", is_title=True))
                continue
                
            if not heading:
                heading = "Puntos Clave" if lang == 'es' else "Key Points"
                
            spoken_text = f"{heading}. {paragraphs_text}"
            
            try:
                sys_prompt = f"""You are a helpful assistant that summarizes text for a PowerPoint slide. 
If the text describes comparisons between options, costs/fees, wait times (e.g., in months), or any meaningful quantitative data, output a JSON object representing a chart that visualizes this data:
{{
  "type": "chart",
  "chart_type": "pie",
  "title": "Chart Title",
  "labels": ["Option A", "Option B"], 
  "values": [500, 800]
}}
If the text describes a step-by-step process or a timeline, output a JSON object representing a process diagram:
{{
  "type": "process",
  "title": "Process Title",
  "steps": ["Step 1 description", "Step 2 description", "Step 3 description"]
}}
Otherwise, output a JSON object with bullet points:
{{
  "type": "bullets",
  "items": [
    {{"title": "Paso 1", "content": "Details..."}},
    {{"title": "Paso 2", "content": "Details..."}}
  ]
}}
Write the content in the language '{lang}'. Output ONLY valid JSON."""
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    response_format={ "type": "json_object" },
                    messages=[
                        {"role": "system", "content": sys_prompt},
                        {"role": "user", "content": f"Please summarize this section for a presentation slide:\n\n{paragraphs_text}"}
                    ],
                    max_tokens=250
                )
                bullet_points = response.choices[0].message.content.strip()
            except Exception:
                bullet_points = "• " + paragraphs_text[:100] + "..."
                
            scenes.append(Scene(spoken_text=spoken_text, slide_title=heading, slide_body=bullet_points, is_title=False))
            
        scenes.append(Scene(spoken_text=outro, slide_title=brand, slide_body=cta_text, is_title=True))
        return scenes

class EdgeTTSProvider:
    def __init__(self, config: dict):
        self.language = config.get('language', 'es')
        if self.language.startswith('es'):
            self.voice = "es-ES-AlvaroNeural"
        elif self.language.startswith('en'):
            self.voice = "en-US-AriaNeural"
        else:
            self.voice = "es-ES-AlvaroNeural"

    async def generate(self, text: str, output_audio: str):
        print(f"Calling Edge TTS API with voice {self.voice}...")
        import edge_tts
        communicate = edge_tts.Communicate(text, self.voice)
        await communicate.save(output_audio)

class VideoComposer:
    def __init__(self, config: dict):
        self.config = config
        self.w, self.h = config['video']['resolution']
        self.fps = config['video']['fps']

    def compose(self, audio_path: str, slides_dir: str, scenes: List[Scene], output_path: str):
        narration_audio = AudioFileClip(audio_path)
        total_duration = narration_audio.duration
        
        total_words = sum(len(s.spoken_text.split()) for s in scenes)
        words_per_sec = total_words / total_duration if total_duration > 0 else 1.0
        
        visual_clips = []
        current_time = 0.0
        
        logo_path = self.config['branding'].get('logo_path', '')
        logo_clip = None
        if logo_path and os.path.exists(logo_path):
            logo_clip = ImageClip(logo_path).resize(height=60).set_position(('right', 'top')).margin(right=50, top=50, opacity=0).set_opacity(0.6).set_duration(total_duration)

        for i, scene in enumerate(scenes):
            scene_words = len(scene.spoken_text.split())
            scene_duration = max(2.0, scene_words / words_per_sec)
            
            if i == len(scenes) - 1:
                scene_duration = max(2.0, total_duration - current_time)
                
            slide_img_path = os.path.join(slides_dir, f"slide_{i}.png")
            slide_clip = ImageClip(slide_img_path).set_start(current_time).set_duration(scene_duration)
            
            if i > 0:
                slide_clip = slide_clip.crossfadein(0.5)
                
            visual_clips.append(slide_clip)
            current_time += scene_duration
            
        if logo_clip:
            visual_clips.append(logo_clip)
            
        video = CompositeVideoClip(visual_clips, size=(self.w, self.h))
        video = video.set_audio(narration_audio)
        
        music_folder = self.config['music'].get('folder', '')
        if music_folder and os.path.exists(music_folder):
            music_files = glob.glob(os.path.join(music_folder, '*.mp3'))
            if music_files:
                bgm_path = random.choice(music_files)
                bgm_volume = self.config['music'].get('volume', 0.1)
                bgm_clip = AudioFileClip(bgm_path).fx(afx.volumex, bgm_volume)
                
                if bgm_clip.duration < total_duration:
                    bgm_clip = afx.audio_loop(bgm_clip, duration=total_duration)
                else:
                    bgm_clip = bgm_clip.subclip(0, total_duration)
                    
                bgm_clip = bgm_clip.fx(afx.audio_fadeout, self.config['music']['fade_duration'])
                final_audio = CompositeAudioClip([video.audio, bgm_clip])
                video = video.set_audio(final_audio)

        print(f"Rendering video to {output_path} (Duration: {total_duration:.2f}s)")
        video.write_videofile(
            output_path, 
            fps=self.fps,
            codec='libx264',
            audio_codec='aac',
            threads=4,
            logger='bar'
        )
        video.close()
        narration_audio.close()
