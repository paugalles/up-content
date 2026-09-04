import json
import os

from .articles import Article
from .config import branding


SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["title", "caption", "hashtags", "slides", "narration"],
    "properties": {
        "title": {"type": "string"},
        "caption": {"type": "string"},
        "hashtags": {"type": "array", "items": {"type": "string"}, "minItems": 4, "maxItems": 10},
        "slides": {"type": "array", "minItems": 5, "maxItems": 8, "items": {
            "type": "object", "additionalProperties": False, "required": ["label", "title", "body"],
            "properties": {"label": {"type": "string"}, "title": {"type": "string"}, "body": {"type": "string"}}}},
        "narration": {"type": "string"},
    },
}


def _dry_content(article: Article) -> dict:
    brand = branding()
    sentences = [s.strip() for s in article.text.replace("## ", "").split("\n\n") if len(s.strip()) > 35]
    disclaimer = "Información general, no asesoramiento legal." if article.language == "es" else "General information, not legal advice."
    cta = brand.cta_es if article.language == "es" else brand.cta_en
    slides = [{"label": str(i + 1), "title": article.title if i == 0 else ("Punto clave" if article.language == "es" else "Key point"), "body": text[:260]} for i, text in enumerate(sentences[:6])]
    while len(slides) < 5:
        slides.append({"label": str(len(slides) + 1), "title": "inmibot.es", "body": f"{cta} {disclaimer}"})
    return {"title": article.title[:100], "caption": f"{article.title}\n\n{cta} {disclaimer}\n{article.canonical_url}", "hashtags": ["#inmigracion", "#spain", "#inmibot", "#informacion"], "slides": slides, "narration": " ".join(s["body"] for s in slides)}


def generate(article: Article, dry_run: bool) -> dict:
    brand = branding()
    if dry_run:
        return _dry_content(article)
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("Missing required environment variable: OPENAI_API_KEY")
    from openai import OpenAI
    prompt = f"""Act as an expert in marketing and social media content creation. Create concise {article.language} social content for {brand.name} from the supplied published article.
Use ONLY facts explicitly present in the source. Never invent legal facts, requirements, deadlines, fees, or outcomes.
Make 5-8 logically ordered slides, useful narration under 900 words, and a compelling platform-neutral caption.
The first slide MUST act as a hook or present the key point of the post, ensuring the viewer understands the main idea at first glance.
End caption and narration with this CTA ({brand.cta_es if article.language == 'es' else brand.cta_en}) and an informational-not-legal-advice disclaimer in {article.language}.
Source URL: {article.canonical_url}\nTITLE: {article.title}\nARTICLE:\n{article.text[:24000]}"""
    response = OpenAI().responses.create(
        model=os.getenv("OPENAI_MODEL") or "gpt-4.1-mini",
        input=[{"role": "system", "content": "You are a careful immigration-information editor expert in marketing and social media content creation."}, {"role": "user", "content": prompt}],
        text={"format": {"type": "json_schema", "name": "social_content", "strict": True, "schema": SCHEMA}},
    )
    return json.loads(response.output_text)
