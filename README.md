# Instagram Influencer Scraper

A production-grade Python scraper that discovers Instagram influencers (100K+ followers) via Google/Bing search and exports structured data to CSV. **No paid API required.** It uses Selenium to visit profiles and optionally send automated Direct Messages.

---

## Features

- **Hashtag-based discovery** — finds influencers via targeted Google & Bing searches (no Instagram rate limits on discovery).
- **Automated DM Sending** — can automatically send a customized welcome message to newly discovered influencers.
- **Follower filter** — automatically skips micro-accounts (configurable, default: 50K).
- **Email extraction** — detects emails published in bios.
- **Auto category detection** — classifies Fashion / Lifestyle / Tech / Comedy / Other.
- **Headless Mode** — runs completely silently in the background (no popup windows).
- **Checkpoint/resume** — auto-saves progress; resumes from where it left off if interrupted.
- **Deduplication** — never scrapes or DMs the same username twice.
- **Session Preservation** — saves your Instagram login cookies to stay logged in securely.

---

## Project Structure

```
instagram_scraper/
│
├── main.py                    # Entry point (run this)
│
├── config/
│   └── settings.py            # All tunable settings (delays, followers, queries)
│
├── core/
│   ├── scraper.py             # Main scraping & login logic
│   ├── discovery.py           # Google/Bing username discovery
│   ├── profile_fetcher.py     # Pulls data from profiles
│   └── parser.py              # JSON parsing + data extraction
│
├── utils/
│   ├── logger.py              # Colored logging setup
│   └── exporter.py            # CSV write/dedup/backup
│
├── .env                       # (Create this) Your Instagram credentials
├── ig_cookies.json            # Auto-generated saved login session
│
├── data/                      # Auto-created on first run
│   ├── influencers.csv        # Main output file
│   └── scraper_checkpoint.json# Resume state
│
├── logs/                      # Auto-created on first run
│   └── scrape_YYYYMMDD.log    # Full debug logs
│
└── requirements.txt
```

---

## Installation

```bash
# Clone or download the project
cd instagram_scraper

# Install dependencies (requires Chrome browser installed on your OS)
pip install -r requirements.txt
```

### Credentials Setup (For DM Sending)
To send Direct Messages, the scraper needs to log in to Instagram. Create a `.env` file in the root folder with your credentials:

```ini
IG_USERNAME=your_username
IG_PASSWORD=your_password
```
*(Note: If you only want to scrape data and DO NOT want to send DMs, you can leave these blank and the script will parse publicly visible profiles anonymously).*

---

## Usage

### Basic — scrape all configured hashtags
```bash
python main.py
```

### Scrape specific hashtags
```bash
python main.py --hashtags fashion ootd streetwear
```

### Scrape specific usernames directly
```bash
python main.py --usernames nike adidas gucci
```

### Custom follower threshold
```bash
python main.py --min-followers 500000
```

### Custom output file
```bash
python main.py --output my_data/results.csv
```

### Reset Checkpoint (Start completely fresh)
```bash
# Makes the scraper "forget" everyone it has already scraped/DM'd
python main.py --reset-checkpoint
```

### Dry run (test logging and setup without scraping)
```bash
python main.py --dry-run
```

---

## Output CSV Columns (`data/influencers.csv`)

| Column | Description |
|---|---|
| `username` | Instagram handle |
| `full_name` | Display name (extracted from profile) |
| `followers` | Follower count |
| `email` | Email found in bio/profile link |
| `bio` | Full bio text |
| `profile_category` | Auto-detected: Fashion / Lifestyle / Tech / Comedy / Other |
| `hashtag` | Top hashtags extracted from bio |
| `profile_url` | Full Instagram profile URL |

---

## Key Configuration (`config/settings.py`)

You can tune the scraper's speed and depth directly in `settings.py`:

**Discovery Settings:**
- `MAX_POSTS_PER_HASHTAG`: (Default: 50) Max names to pull from search engines before scraping.
- `MAX_USERS_PER_HASHTAG`: (Default: 30) Stop processing a hashtag once this many valid influencers are saved.
- `GOOGLE_PAGES`: (Default: 2) Number of Google pages to scan per specific query.

**Operation Settings:**
- `HEADLESS`: `True` runs silently. `False` shows the Chrome window (good for debugging).
- `SEND_DM`: `True` enables the automated DM sender. `False` skips DMs entirely.
- `DM_DELAY_MIN` / `DM_DELAY_MAX`: Controls the pause between sending each message to prevent spam blocks.
- `DM_MESSAGE`: The actual text sent to influencers. You can use `{full_name}` and `{username}` as dynamic placeholders.

---

## Important Notes & Troubleshooting

1. **Login Checkpoints:** If you run headless and see `❌ Login failed` in the logs, Instagram might have triggered a CAPTCHA. Change `HEADLESS = False`, run it once to manually solve the puzzle, and then switch back to headless.
2. **Handle is Invalid Error:** When you stop the script via `Ctrl+C`, you might see an `OSError: [WinError 6]` from Selenium. This is just a cleanup error when the driver is destroyed forcefully and can be safely ignored.
3. **Resetting Data:** If you want to run a completely new campaign, use `python main.py --reset-checkpoint` AND delete your `influencers.csv` file.

---

