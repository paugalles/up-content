import argparse
from pathlib import Path

from .pipeline import run


def main(platform: str, argv=None) -> int:
    try:
        import dotenv
        dotenv.load_dotenv()
    except ImportError:
        pass
    parser = argparse.ArgumentParser(description=f"Generate and publish {platform} content")
    parser.add_argument("--generate-only", action="store_true", help="generate persistent assets and metadata without publishing")
    parser.add_argument("--output-dir", type=Path, help="persistent output directory; requires --generate-only")
    parser.add_argument("--article", type=Path, help="local Markdown source; skips random sitemap selection")
    args = parser.parse_args(argv)
    if args.output_dir and not args.generate_only:
        parser.error("--output-dir requires --generate-only")
    return run(platform, generate_only=args.generate_only, output_dir=args.output_dir, article_path=args.article)
