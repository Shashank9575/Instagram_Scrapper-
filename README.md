# Instagram Multi-Account Scraper & Auto-Engager

A production-grade Python scraper that automatically discovers Instagram brands and influencers matching specific criteria, extracts their profiles into a structured CSV, and natively powers an **Auto-Follow** and **Auto-DM** pipeline. 

It executes flawlessly inside a single `undetected-chromedriver` instance and features a mature **Multi-Account Rotation Engine** to distribute the workload safely across unlimited Instagram profiles.

---

## 🔥 Key Features

- **Multi-Account Rotation** — Load an unlimited number of accounts in your `.env`. The bot will independently log into them, cache their cookies (`ig_cookies_<username>.json`), and intelligently divide up your scraping workload across them seamlessly.
- **Auto-Follow & Auto-DM** — Natively clicks the "Follow" button and effortlessly bypasses transparent overlays and popups to deliver safe, randomized DMs to the extracted profiles.
- **Hashtag Discovery Engine** — Sources usernames algorithmically from Instagram's native hashtag engine or direct Google searching.
- **Micro-Account Filtering** — Pre-filters targets based on live follower counts, skipping micro-accounts.
- **Email & Category Extraction** — Cleans and logs explicitly displayed public emails and automatically assigns the user into an Industry Category (e.g. Technology, Fitness, Editor, Beauty).
- **Session Preservation** — Auto-saves cookies locally. You only have to log in once!
- **Deduplication** — Inherently resistant to repeats. Keeps a safe ledger so it never scrapes, follows, or DMs the same username twice.

---

## 🛠️ Project Structure

```text
instagram_scraper/
│
├── main.py                    # Entry point (run this)
│
├── config/
│   └── settings.py            # All tunable limits, speeds, and behavioral toggles
│
├── core/
│   ├── scraper.py             # Main Chrome automation, Login logic, Profile visits
│   ├── discovery.py           # Google-based backend username discovery
│   ├── profile_fetcher.py     # Pulls and cleans DOM data from profiles
│   └── parser.py              # JSON parsing + robust HTML extraction
│
├── utils/
│   ├── logger.py              # Colored terminal output setup
│   └── exporter.py            # CSV generation & Deduplication engine
│
├── data/                      # Auto-created on first run! Contains all outputs.
│   └── influencers1.csv       # Main output file
│
├── logs/                      # Auto-created on first run
└── requirements.txt
```

---

## ⚙️ Installation & Requirements

This bot is fully cross-platform (Windows, macOS, Linux) and built specifically to target modern architectures (**Python 3.10 to Python 3.12**).

1. Ensure **Google Chrome** is natively installed on your machine.
2. Clone or download this project.
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Credentials Setup (For Rotation, DMs, & Following)
Create a `.env` file in the root folder with as many accounts as you desire:

```ini
IG_USERNAME_1=account_one
IG_PASSWORD_1=password_one

IG_USERNAME_2=account_two
IG_PASSWORD_2=password_two
```
*The bot will automatically divide the resulting workload evenly across all inputted accounts.*

---

## 🚀 Usage Guide

First, adjust your limits inside `config/settings.py`:
- `SEND_DM = False` (Set to `True` for automated messaging)
- `AUTO_FOLLOW = True`
- `MAX_USERS_PER_HASHTAG = 15` (The total final output before it stops)

### Starting the Engine
```bash
python main.py
```

### Advanced Examples
Target exact hashtags with a specific minimum follower threshold:
```bash
python main.py --mode brands --hashtags "cricket" "fashion" --min-followers 20000
```

Target exact usernames explicitly without running the hashtag engine:
```bash
python main.py --usernames mrbeast nike gq
```

Reset the global Checkpoint history (Makes the scraper forget everyone it has already processed):
```bash
python main.py --reset-checkpoint
```

---

## 📊 Output Schema

The file `data/influencers.csv` exports standard structured sets: `username`, `full_name`, `followers`, `email`, `bio`, `profile_category`, `hashtag`, `profile_url`.

---

## ⚠️ Important Production Notes

1. **Initial Login Challenges:** If you are running an account through the bot for the absolute first time, Instagram might throw a simple 2FA or CAPTCHA sequence depending on your proxy location. The bot is programmed to detect this and will pause, allowing you to easily complete the puzzle inside the browser, after securely capturing your cookies to ensure it rarely asks again.
2. **Handle is Invalid Debug Output:** If you forcibly interrupt the script using `[Ctrl + C]` you may see an `OSError: [WinError 6]` from Selenium. This is just an OS-level cleanup error resulting from the sudden death of the Chrome subprocess and is completely normal on Windows! All of your data is safely saved up to the moment you quit!
3. **Headless Limitations:** For massive production automation, you can set `HEADLESS = True` inside `settings.py`. Due to browser fingerprinting techniques, you strongly need a robust Session Cookie history pre-recorded via the normal non-headless sequence before going headless, otherwise login pages might silently reject the Chrome driver.
