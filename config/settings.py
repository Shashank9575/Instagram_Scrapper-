"""
Instagram Scraper — Configuration Settings
===========================================
Edit this file to change scraping behaviour.
"""
import os
from dotenv import load_dotenv

# Load variables from .env file into os.environ
load_dotenv(override=True)

# ─── Target Mode ──────────────────────────────────────────────────────────────
# "brands"      → scrape brand/business accounts
# "influencers" → scrape influencer/creator accounts
TARGET_MODE = "brands"

# ─── Scraping Targets ─────────────────────────────────────────────────────────

HASHTAGS = [
    # Technology & Software
    "techstartup",
    "softwarecompany",
    "saas",
    "techbrand",

    # Fashion & Apparel
    "fashionbrand",
    "clothingbrand",
    "streetwearbrand",
    "sustainablefashion",

    # Beauty & Skincare
    "skincarebrand",
    "beautybrand",
    "cosmeticscompany",

    # Fitness & Health
    "fitnessbrand",
    "healthandwellness",

    # General Business / E-commerce
    "ecommercebusiness",
    "smallbusiness",
    "dtcbrand",
]

# Minimum follower count to include an account
MIN_FOLLOWERS = 20000   # lowered slightly to capture niche finance educators

# Max unique influencers to collect per hashtag (Target goal)
MAX_USERS_PER_HASHTAG = 15

PROFILE_DELAY_MIN = 12.0
PROFILE_DELAY_MAX = 25.0

HASHTAG_DELAY_MIN = 30.0
HASHTAG_DELAY_MAX = 60.0

# Delays between opening posts during the #hashtag discovery phase
DISCOVERY_POST_DELAY_MIN = 1.0 # default was ~3.0s total but split up
DISCOVERY_POST_DELAY_MAX = 2.0


# ─── Output ───────────────────────────────────────────────────────────────────

OUTPUT_DIR      = "data"
OUTPUT_CSV      = "data/influencers1.csv"
CHECKPOINT_FILE = "data/checkpoint.json"


# ─── Instagram Login ──────────────────────────────────────────────────────────
# ─── Multi-Account Login & Rotation ───────────────────────────────────────────
# You can define multiple accounts via numbered environment variables:
#   IG_USER_1 = "account1" | IG_PASS_1 = "pwd1"
#   IG_USER_2 = "account2" | IG_PASS_2 = "pwd2"
# Or use the legacy IG_USERNAME / IG_PASSWORD for a single account.

ACCOUNTS = []
_idx = 1
while True:
    u = os.environ.get(f"IG_USERNAME_{_idx}") or os.environ.get(f"IG_USER_{_idx}")
    p = os.environ.get(f"IG_PASSWORD_{_idx}") or os.environ.get(f"IG_PASS_{_idx}")
    if not u or not p:
        break
    ACCOUNTS.append({"username": u.strip().strip('"').strip("'"), "password": p.strip().strip('"').strip("'")})
    _idx += 1

# Fallback to legacy single-account if no numbered accounts found
if not ACCOUNTS:
    _legacy_u = os.environ.get("IG_USERNAME", "").strip().strip('"').strip("'")
    _legacy_p = os.environ.get("IG_PASSWORD", "").strip().strip('"').strip("'")
    if _legacy_u and _legacy_p:
        ACCOUNTS.append({"username": _legacy_u, "password": _legacy_p})


# ─── Category Keywords ────────────────────────────────────────────────────────

CATEGORY_KEYWORDS = {
    "Technology": [
        "tech", "software", "saas", "startup", "developer", 
        "ai", "artificial intelligence", "app", "platform", "technology", "techbrand"
    ],
    "Fashion": [
        "fashion", "clothing", "apparel", "streetwear", "boutique", 
        "sustainable fashion", "wear", "style", "garments", "fashionbrand"
    ],
    "Beauty": [
        "skincare", "beauty", "cosmetics", "makeup", "serum", 
        "wellness", "haircare", "bodycare", "beautybrand"
    ],
    "Fitness": [
        "fitness", "gym", "workout", "activewear", "supplements",
        "health", "athletics", "training", "fitnessbrand"
    ],
    "E-commerce & Business": [
        "store", "shop", "ecommerce", "brand", "dtc", "company",
        "official", "business", "retail", "smallbusiness"
    ]
}

# ─── DM & Engagement Settings ───────────────────────────────────────────────────

SEND_DM = True   # ← Change to True to enable DM sending
AUTO_FOLLOW = True   # ← Change to True to automatically follow profiles before DMing
AUTO_LIKE_FIRST_POST = True  # ← Change to True to automatically like their first post/reel

AUTO_COMMENT = True  # ← Change to True to automatically comment on their first post
COMMENTS_LIST = [
    "Love this! ❤️",
    "Amazing profile! 🔥",
    "Great content, keep it up!",
    "Wow, this is so cool!",
    "Awesome post!"
]

DM_DELAY_MIN = 30.0 # seconds between each DM
DM_DELAY_MAX = 60.0

# ─── YOUR COLLABORATION MESSAGE ───────────────────────────────────────────────
# {username} and {full_name} get replaced automatically.
# Use DOUBLE braces for Spintax: {{option1|option2|option3}}
# (Python .format() converts {{ }} to { } then Spintax resolves them)

DM_MESSAGE = """{{Hey|Hi|Hello}} {full_name} 
"""
# ─── Selenium Settings ───────────────────────────────────────────────────────

HEADLESS = False

# Instagram hashtag page scrolling
SCROLL_PAUSE = 2.5       # seconds to wait between scrolls
MAX_SCROLLS  = 50        # maximum scroll attempts per hashtag page

# ─── Proxy Settings ──────────────────────────────────────────────────────────

# Set to True to route Selenium through a proxy (Requires credentials in .env)
# The scraper works perfectly fine on your normal IP if this is False.
USE_PROXY = os.environ.get("USE_PROXY", "False").lower() == "true"
PROXY_HOST = os.environ.get("PROXY_HOST", "")
PROXY_PORT = os.environ.get("PROXY_PORT", "")
PROXY_USER = os.environ.get("PROXY_USER", "")
PROXY_PASS = os.environ.get("PROXY_PASS", "")