import os
from dataclasses import dataclass


def truthy(name: str) -> bool:
    return os.getenv(name, "").lower() in {"1", "true", "yes", "on"}


def require(*names: str) -> dict[str, str]:
    missing = [name for name in names if not os.getenv(name)]
    if missing:
        raise RuntimeError("Missing required environment variables: " + ", ".join(missing))
    return {name: os.environ[name] for name in names}


@dataclass(frozen=True)
class Branding:
    name: str
    site: str
    cta_es: str
    cta_en: str
    navy: str
    blue: str
    slate: str
    canvas: str
    border: str
    font_path: str
    tts_voice: str


def branding() -> Branding:
    req = require("BRAND_NAME", "BRAND_SITE", "BRAND_CTA_ES", "BRAND_CTA_EN")
    return Branding(
        name=req["BRAND_NAME"],
        site=req["BRAND_SITE"],
        cta_es=req["BRAND_CTA_ES"],
        cta_en=req["BRAND_CTA_EN"],
        navy=os.getenv("BRAND_COLOR_NAVY") or "#0c3d6d",
        blue=os.getenv("BRAND_COLOR_BLUE") or "#0c88eb",
        slate=os.getenv("BRAND_COLOR_TEXT") or "#0f172a",
        canvas=os.getenv("BRAND_COLOR_CANVAS") or "#f8fafc",
        border=os.getenv("BRAND_COLOR_BORDER") or "#e2e8f0",
        font_path=os.getenv("BRAND_FONT_PATH") or "",
        tts_voice=os.getenv("OPENAI_TTS_VOICE") or "alloy",
    )


TIMEOUT = float(os.getenv("REQUEST_TIMEOUT") or "30")
GRAPH = os.getenv("META_GRAPH_API") or "https://graph.facebook.com/v23.0"
TIKTOK = "https://open.tiktokapis.com/v2"
LINKEDIN = "https://api.linkedin.com"
