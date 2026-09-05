import argparse
from pathlib import Path

from .pipeline import run


def main(platform: str, argv=None) -> int:
    env_file = Path(".env")
    if env_file.exists():
        import os
        with open(env_file, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    if "=" in line:
                        key, value = line.split("=", 1)
                        os.environ.setdefault(key.strip(), value.strip().strip("'\""))
    parser = argparse.ArgumentParser(description=f"Generate and publish {platform} content")
    parser.add_argument("--generate-only", action="store_true", help="generate persistent assets and metadata without publishing")
    parser.add_argument("--output-dir", type=Path, help="persistent output directory; requires --generate-only")
    parser.add_argument("--article", type=Path, help="local Markdown source; skips random sitemap selection")
    args = parser.parse_args(argv)
    if args.output_dir and not args.generate_only:
        parser.error("--output-dir requires --generate-only")
    return run(platform, generate_only=args.generate_only, output_dir=args.output_dir, article_path=args.article)
