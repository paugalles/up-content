# Inmibot Social Publisher

Production-minded, standalone Python publishers for YouTube, Instagram, Facebook, TikTok, and LinkedIn. Each run chooses `es` or `en` with exactly equal probability, discovers a genuinely published article in that language from public sitemaps, downloads and extracts its canonical source, generates source-grounded copy with OpenAI structured JSON, renders valid platform media, validates it, and optionally uploads through the official API.

Generated copy is instructed never to invent legal facts, requirements, fees, deadlines, or outcomes. It includes a useful CTA and same-language informational-not-legal-advice wording. The repository has no database, web-framework model, template, config, asset, import, or path dependency on another source repository. Public website sitemaps and article pages are its only remote article source.

## Architecture

- `scripts/youtube.py`, `instagram.py`, `facebook.py`, `tiktok.py`, `linkedin.py`: the only executable platform entry points.
- `scripts/common/cli.py`: shared `--generate-only`, `--output-dir`, and `--article` CLI contract.
- `scripts/common/articles.py`: language-first selection, recursive sitemap indexes, retries, canonical extraction, frontmatter Markdown, and local Markdown loading.
- `scripts/common/content.py`: strict OpenAI JSON schema, source-safety prompt, CTAs/disclaimers, and source-only dry-run fallback.
- `scripts/common/assets.py`: shared Pillow layout, PDF carousel, OpenAI TTS, ffmpeg H.264/AAC video, and media validation.
- `scripts/common/publishers.py`: Meta Graph, YouTube Data API, TikTok Content Posting API, LinkedIn Posts/Documents, and temporary GCS media.
- `scripts/common/pipeline.py`: temporary live runs, persistent generation-only runs, validation, upload dispatch, and publication-ID logging.
- `.github/workflows/*.yml`: five independent scheduled/manual workflows.

## Prerequisites

- Git.
- Python 3.12.
- ffmpeg and ffprobe recommended. `imageio-ffmpeg` supplies a pinned portable rendering fallback, while GitHub Actions installs the system package.
- An OpenAI API key for real copy and TTS generation.
- Only the developer credentials for platforms being published to; generation-only mode needs none of them.

Install ffmpeg on macOS with `brew install ffmpeg`, or on Debian/Ubuntu with `sudo apt-get install ffmpeg fonts-dejavu-core`.

## Installation

```bash
git clone <repository-url> up-content
cd up-content
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

On Windows PowerShell, activate with `.venv\Scripts\Activate.ps1`.

## Safe Environment Setup

`.env.example` contains placeholders only. The application deliberately does not parse `.env`; export variables in the shell or use a secret manager. `.env`, credentials, generated media, caches, and virtual environments are gitignored.

```bash
cp .env.example .env
# Edit .env and keep only the variables needed for the intended command.
set -a
source .env
set +a
```

Never paste production secrets into issues, logs, workflow YAML, or committed files. A prior local draft contained live-looking credentials; rotate every credential that appeared in that draft before enabling publication. The repository does not print tokens or service-account JSON.

## Local Generation Only

`--generate-only` is the recommended content test. It performs selection/download, OpenAI generation, rendering, validation, and metadata writing without initializing any platform or GCS client. It never uploads or deletes the output.

```bash
python scripts/youtube.py --generate-only --output-dir generated/youtube
python scripts/instagram.py --generate-only --output-dir generated/instagram
python scripts/facebook.py --generate-only --output-dir generated/facebook
python scripts/tiktok.py --generate-only --output-dir generated/tiktok
python scripts/linkedin.py --generate-only --output-dir generated/linkedin
```

`OPENAI_API_KEY` is required for real generation. For a credential-free contributor smoke test, set `DRY_RUN=true`; copy then comes only from extracted source sentences and videos use silent audio.

### Repeatable Local Articles

Add `--article` to bypass sitemap fetching and randomness:

```bash
python scripts/instagram.py --generate-only --output-dir generated/instagram --article articles/sample.md
DRY_RUN=true python scripts/youtube.py --generate-only --output-dir generated/youtube --article articles/sample.md
```

Recommended Markdown format:

```markdown
---
title: "Renewing a residence permit"
language: en
url: "https://example.org/en/blog/residence-permit"
---

# Renewing a residence permit

Substantive article content goes here. Include enough source material for accurate summaries.
```

Supported frontmatter fields are `title`, `language` (`es` or `en`), and `url`. If omitted, title falls back to the first H1/filename, language is inferred from common words, and URL becomes the local file URI. Inputs shorter than 100 extracted characters fail with an actionable error.

### Generated Outputs

Every output directory contains `metadata.json`, a retained `article.md`, article title/language/canonical URL, generated copy, final caption, and primary asset names.

| Platform | Persistent output |
| --- | --- |
| Instagram | `slide-01.jpg` through 5-8 validated 1080x1350 JPEG slides |
| Facebook | `facebook.jpg`, a validated 1200x1500 JPEG, plus copy in `metadata.json` |
| LinkedIn | `carousel.pdf`, 5-8 page JPEG sources, and commentary in `metadata.json` |
| TikTok | `short.mp4` at 1080x1920 H.264/AAC, frame JPEGs, narration audio, and manifest |
| YouTube | `short.mp4` at 1080x1920 H.264/AAC, frame JPEGs, narration audio, and manifest |

`generated/` is gitignored. Regeneration overwrites deterministic filenames but does not clean the directory first.

## DRY_RUN Versus Generate Only

| Mode | Publishes | Credentials | Output lifetime |
| --- | --- | --- | --- |
| Normal live run | Yes | OpenAI plus platform credentials | Temporary assets are cleaned |
| `DRY_RUN=true` | No | None required | Temporary assets are cleaned |
| `--generate-only` | No | OpenAI for real generation | Persists under `--output-dir` |
| `DRY_RUN=true --generate-only` | No | None required | Persists under `--output-dir` |

`--output-dir` is valid only with `--generate-only`. API failures, validation errors, and polling timeouts exit nonzero; there is no fake live success path.

## Live Publishing

After exporting the appropriate credentials, run exactly one publisher:

```bash
python scripts/youtube.py
python scripts/instagram.py
python scripts/facebook.py
python scripts/tiktok.py
python scripts/linkedin.py
```

`--article articles/sample.md` may also be used during a live run to choose a fixed source. Live assets use a cleaned temporary directory. Instagram GCS objects are handled separately and deleted best-effort only after Meta finishes fetching/publishing.

## Environment Variables

Blank optional values use the documented default.

| Variable | Required | Used by | Purpose/default |
| --- | --- | --- | --- |
| `OPENAI_API_KEY` | Live/real generation | All | Structured copy and TTS authentication |
| `OPENAI_MODEL` | No | All | Copy model; default `gpt-4.1-mini` |
| `OPENAI_TTS_VOICE` | No | YouTube, TikTok | TTS voice; default `alloy` |
| `DRY_RUN` | No | All | Truthy values skip publishing; default false |
| `REQUEST_TIMEOUT` | No | All HTTP | Request seconds; default `30` |
| `ARTICLE_BASE_URL` | No | All | Default sitemap base; default `https://inmibot.es` |
| `ARTICLE_SITEMAP_URL_ES` | No | All | Spanish sitemap/index override |
| `ARTICLE_SITEMAP_URL_EN` | No | All | English sitemap/index override |
| `BRAND_NAME` | No | All assets/copy | Footer/prompt name; default `INMIBOT` |
| `BRAND_SITE` | No | All assets | Footer site; default `inmibot.es` |
| `BRAND_CTA_ES` | No | All copy | Spanish CTA |
| `BRAND_CTA_EN` | No | All copy | English CTA |
| `BRAND_COLOR_NAVY` | No | All assets | Heading/footer color; default `#0c3d6d` |
| `BRAND_COLOR_BLUE` | No | All assets | Accent color; default `#0c88eb` |
| `BRAND_COLOR_TEXT` | No | All assets | Body color; default `#0f172a` |
| `BRAND_COLOR_CANVAS` | No | All assets | Canvas color; default `#f8fafc` |
| `BRAND_COLOR_BORDER` | No | All assets | Card border; default `#e2e8f0` |
| `BRAND_FONT_PATH` | No | All assets | Local TrueType font path; fallback described below |
| `META_GRAPH_API` | No | Instagram, Facebook | Graph base; default `https://graph.facebook.com/v23.0` |
| `IG_USER_ID` | Live only | Instagram | Instagram professional account ID |
| `IG_ACCESS_TOKEN` | Live only | Instagram | Meta user/system-user access token |
| `GCS_BUCKET_NAME` | Live only | Instagram | Temporary external-media bucket |
| `GOOGLE_APPLICATION_CREDENTIALS_JSON` | Live only | Instagram | Entire service-account JSON object |
| `FACEBOOK_PAGE_ID` | Live only | Facebook | Target Page ID |
| `FACEBOOK_PAGE_ACCESS_TOKEN` | Live only | Facebook | Page access token |
| `YOUTUBE_CLIENT_ID` | Live only | YouTube | Google OAuth client ID |
| `YOUTUBE_CLIENT_SECRET` | Live only | YouTube | Google OAuth client secret |
| `YOUTUBE_REFRESH_TOKEN` | Live only | YouTube | Offline OAuth refresh token |
| `YOUTUBE_PRIVACY_STATUS` | No | YouTube | `public`, `unlisted`, or `private`; default `public` |
| `TIKTOK_ACCESS_TOKEN` | Live only | TikTok | Authorized Content Posting token |
| `TIKTOK_PRIVACY_LEVEL` | No | TikTok | Must match creator-info option; default `SELF_ONLY` |
| `LINKEDIN_ACCESS_TOKEN` | Live only | LinkedIn | Member/organization OAuth token |
| `LINKEDIN_AUTHOR_URN` | Live only | LinkedIn | `urn:li:person:...` or `urn:li:organization:...` |
| `LINKEDIN_VERSION` | No | LinkedIn | REST version header; default `202508` |

## Public Article Selection

Selection calls `random.choice(['es', 'en'])` first, then discovers and filters URLs for only that language, then chooses an article. `ARTICLE_SITEMAP_URL_ES` and `ARTICLE_SITEMAP_URL_EN` may point to sitemap indexes or URL sets. Sitemap indexes are followed recursively with bounded depth. If unset, both derive from `${ARTICLE_BASE_URL}/sitemap.xml`.

Published article URLs must contain `/blog/`; default bilingual filtering expects English routes under `/en/` or `/en/blog/` and excludes those routes from Spanish. Configure language-specific sitemaps if the public site uses another routing convention. Pages must expose useful `<article>` or `<main>` content; canonical links are honored. Requests use status checks, timeouts, and bounded exponential retries.

## Official Platform Setup

### YouTube

1. Create a Google Cloud project, enable YouTube Data API v3, and configure an OAuth consent screen.
2. Create an OAuth client, authorize the target channel with offline access and scope `https://www.googleapis.com/auth/youtube.upload`, then store the refresh token.
3. Set `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, and `YOUTUBE_REFRESH_TOKEN`.

Uploads use the official resumable `videos.insert` flow. Unverified/new projects may force uploads private. Daily quota, OAuth verification, channel strikes/policies, made-for-kids obligations, and YouTube's own Shorts classification remain external constraints.

### Instagram

1. Use an Instagram professional account linked to a Facebook Page and a Meta developer app.
2. Obtain app review/advanced access as applicable for `instagram_basic`, `instagram_content_publish`, `pages_show_list`, and `pages_read_engagement`.
3. Obtain a suitable long-lived user or system-user token and the Instagram account ID.
4. Configure the GCS setup below.

The publisher creates each child container, polls it to `FINISHED`, creates/polls the carousel container, then calls `media_publish`. Personal accounts are unsupported. Meta Business Verification, account linkage, content-publishing limits, token expiry, rate limits, and version changes apply.

### Facebook

1. Create a Meta app connected to the target Page.
2. Obtain appropriate app review/advanced access and Page authorization, commonly including `pages_manage_posts`, `pages_read_engagement`, and Page discovery permissions.
3. Set the Page ID and Page access token.

The publisher uses the official `/{page-id}/photos` Graph endpoint. The authenticated user/system user needs a sufficient Page task/role. Page access-token lifetime and Meta platform limits apply.

### TikTok

1. Create a TikTok developer app and add the Content Posting API Direct Post product.
2. Complete app/audit review and authorize the creator with `video.publish`.
3. Set `TIKTOK_ACCESS_TOKEN`; optionally set an allowed `TIKTOK_PRIVACY_LEVEL`.

Before upload, the publisher queries creator info, verifies privacy choice and maximum duration, initializes `FILE_UPLOAD`, sends bytes, and polls status. Unaudited clients are generally limited to private posts and a small set of test users. Creator eligibility, music/content policy, token expiry, daily caps, rate limits, and moderation remain TikTok-controlled.

### LinkedIn

1. Create a LinkedIn developer app and request the appropriate product/access.
2. For members, obtain `w_member_social`. For organizations, obtain approved organization posting access such as `w_organization_social`, and ensure the authenticated member has an authorized Page role.
3. Set `LINKEDIN_ACCESS_TOKEN` and the matching `LINKEDIN_AUTHOR_URN`.

The publisher initializes `/rest/documents`, uploads PDF bytes to the returned URL, then creates `/rest/posts`. LinkedIn product review, organization authorization, token lifetime, rate limits, content limits, and monthly REST version retirement apply. Update `LINKEDIN_VERSION` when required.

## Google Cloud Storage for Instagram

Instagram's Graph API fetches carousel images from external HTTPS URLs. This project uses private GCS objects with temporary V4 signed GET URLs.

1. Create a dedicated bucket near the expected workload; keep public access prevention enabled.
2. Enable Cloud Storage and create a dedicated service account.
3. Grant bucket-scoped object create, read, and delete permissions. A custom least-privilege role is preferable; `Storage Object Admin` works but is broader.
4. Create a JSON key, store its complete JSON as `GOOGLE_APPLICATION_CREDENTIALS_JSON`, and set `GCS_BUCKET_NAME`.
5. Add a short lifecycle deletion rule, such as one day, as crash cleanup. Normal runs delete objects best-effort after Meta completes.
6. Monitor storage operations and egress costs.

Objects receive unique `social-runs/<uuid>/...` prefixes. Signed URLs expire after six hours and grant only temporary HTTPS GET access. The bucket does not need to be public. CORS is not required for Meta's server-to-server GET because no browser JavaScript reads the object; if a separate browser preview tool is introduced, configure only that tool's exact origin and `GET` method rather than using wildcard CORS.

Google Drive is unsuitable: shared links commonly return HTML viewers, redirects, cookies, or confirmation pages rather than a stable direct image response. They also do not provide the predictable signed-origin and object-lifecycle behavior required for reliable Graph ingestion.

## GitHub Actions

Create these repository or environment secrets under **Settings > Secrets and variables > Actions**:

- Shared: `OPENAI_API_KEY`.
- Instagram: `IG_USER_ID`, `IG_ACCESS_TOKEN`, `GCS_BUCKET_NAME`, `GOOGLE_APPLICATION_CREDENTIALS_JSON`.
- Facebook: `FACEBOOK_PAGE_ID`, `FACEBOOK_PAGE_ACCESS_TOKEN`.
- YouTube: `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN`.
- TikTok: `TIKTOK_ACCESS_TOKEN`.
- LinkedIn: `LINKEDIN_ACCESS_TOKEN`, `LINKEDIN_AUTHOR_URN`.

Optional Actions variables wired by the workflows are `ARTICLE_SITEMAP_URL_ES`, `ARTICLE_SITEMAP_URL_EN`, and, for TikTok, `TIKTOK_PRIVACY_LEVEL`. Empty variables fall back to code defaults. Other optional environment settings are currently local/code defaults unless added to workflow `env` explicitly.

Each independent workflow uses Python 3.12, pip caching, ffmpeg/DejaVu installation, tests, least `contents: read` permission, a 30-minute timeout, and a platform-specific concurrency guard. Each supports `workflow_dispatch` and runs:

```text
0 8,14,20 * * *
```

Times are 08:00, 14:00, and 20:00 UTC. GitHub schedules run from the default branch, can be delayed or dropped under load, and public-repository schedules may be disabled after prolonged inactivity. Hosted Actions usage follows GitHub's current billing/minutes policy; public repositories do not imply unlimited, immediate, or guaranteed execution.

## Branding

The built-in visual language uses a cool slate canvas, white rounded card, vivid blue rule/labels, navy headings, responsive wrapping, compact sequence labels, and a brand/site footer. Prompts use the configured name and bilingual CTA. Change the `BRAND_*` variables in `.env.example` rather than editing render code.

No font was copied from another repository. CI installs the open DejaVu Sans package. Locally, `BRAND_FONT_PATH` may point to a legally obtained TrueType font; rendering otherwise tries system DejaVu Sans, macOS Arial, and finally Pillow's built-in fallback.

## Tests and Validation

```bash
python -m unittest discover -s tests -v
python -m compileall -q scripts tests
```

Tests mock OpenAI and publishing boundaries, validate image/PDF/video output, verify language-first selection and retries, exercise persistent generation-only behavior, ensure dry runs cannot publish, parse all five CLI contracts, and scan runtime/config/workflow files for forbidden parent-repository dependencies. Tests never publish.

## Security and Operational Limits

- Rotate leaked, expired, or draft credentials immediately; revoke unused tokens and service-account keys.
- Grant least scopes/roles, use separate production/test apps, protect workflow environments, and review Actions logs.
- Never log request authorization headers or secret JSON. Publication IDs and public source URLs are safe to log.
- OpenAI, Meta, Google, TikTok, LinkedIn, GCS, and GitHub all impose quotas, rate limits, policy review, outages, and API/version changes that code cannot remove.
- Content remains informational; human review is advisable for legal-information accuracy and policy compliance before enabling unattended public posting.

## Troubleshooting

| Symptom | Resolution |
| --- | --- |
| `Missing required environment variables` | Export every variable named in the error for that live platform; generation-only needs no platform variables. |
| No articles found | Verify sitemap URL/status, `/blog/` paths, language routing, and `ARTICLE_SITEMAP_URL_ES`/`EN`. |
| Insufficient local Markdown | Add at least 100 characters of substantive body content and preferably explicit frontmatter. |
| OpenAI authentication/schema error | Verify `OPENAI_API_KEY`, account quota, model access, and optional `OPENAI_MODEL`. |
| ffmpeg missing or invalid MP4 | Install system ffmpeg/ffprobe; confirm H.264 and AAC encoders are available. |
| Instagram container `ERROR`/timeout | Confirm signed URL is unexpired and returns JPEG bytes, token/scopes/account linkage are valid, and Meta limits are not exceeded. |
| GCS permission error | Confirm bucket name, valid JSON, object create/read/delete permissions, and key rotation status. |
| YouTube upload forced private/fails | Check OAuth verification, channel ownership, quota, refresh token, and project upload restrictions. |
| TikTok privacy rejected | Use a value returned by creator-info; unaudited apps commonly permit only `SELF_ONLY`. |
| LinkedIn 403/version error | Check author URN, member Page role, product/scopes, token expiry, and update `LINKEDIN_VERSION`. |
| GitHub schedule did not run exactly on time | Check default branch, repository activity, Actions enablement/billing, concurrency, and delayed scheduled-event delivery. |
