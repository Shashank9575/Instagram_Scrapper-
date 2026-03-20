# """
# Instagram Scraper — Configuration Settings
# ===========================================
# Edit this file to change scraping behaviour.
# """

# # ─── Scraping Targets ─────────────────────────────────────────────────────────

# HASHTAGS = [
#     "fashion",
#     "lifestyle",
#     "tech",
#     "comedy",
#     "ootd",
#     "techreview",
#     "fashionblogger",
#     "lifestyleblogger",
#     "standupcomedy",
#     "gadgets",
# ]

# # Minimum follower count to include an account
# MIN_FOLLOWERS = 100_000

# # How many posts to scan per hashtag (each post = 1 potential user)
# MAX_POSTS_PER_HASHTAG = 80

# # Max unique influencers to collect per hashtag
# MAX_USERS_PER_HASHTAG = 50

# # ─── Rate Limiting ────────────────────────────────────────────────────────────

# # Seconds to wait between fetching individual profiles
# # Keep these values HIGH — Instagram 429s when you fetch too fast
# PROFILE_DELAY_MIN = 8.0
# PROFILE_DELAY_MAX = 15.0

# # Extra seconds to wait between hashtags
# HASHTAG_DELAY_MIN = 15.0
# HASHTAG_DELAY_MAX = 30.0

# # ─── Output ───────────────────────────────────────────────────────────────────

# OUTPUT_DIR      = "data"
# OUTPUT_CSV      = "data/influencers.csv"
# CHECKPOINT_FILE = "data/checkpoint.json"

# # ─── Instagram Login (optional but strongly recommended) ─────────────────────
# # Using a real account dramatically reduces the chance of being rate-limited.
# # Leave as empty strings to run without login (more likely to get blocked).

# IG_USERNAME = ""   # e.g. "myaccount"
# IG_PASSWORD = ""   # e.g. "mypassword"

# # ─── Category Keywords ────────────────────────────────────────────────────────

# CATEGORY_KEYWORDS = {
#     "Fashion": [
#         "fashion", "style", "ootd", "outfit", "model", "clothing",
#         "streetwear", "designer", "couture", "wardrobe", "trendy",
#         "fashionista", "lookbook", "stylist", "apparel",
#     ],
#     "Lifestyle": [
#         "lifestyle", "travel", "wellness", "yoga", "fitness", "health",
#         "mindfulness", "vlog", "daily", "motivation", "selfcare",
#         "adventure", "explore", "wanderlust", "foodie", "luxurylife",
#     ],
#     "Tech": [
#         "tech", "technology", "coding", "developer", "programmer",
#         "ai", "artificialintelligence", "gadget", "software", "hardware",
#         "startup", "innovation", "cybersecurity", "iot", "machinelearning",
#         "datascience", "devops", "techreview", "unboxing",
#     ],
#     "Comedy": [
#         "comedy", "funny", "humor", "meme", "memes", "lol", "jokes",
#         "standup", "comedian", "satire", "parody", "prank", "skit",
#         "viral", "reels", "entertainment",
#     ],
# }

# # ─── Selenium Discovery Settings ─────────────────────────────────────────────

# # Run Chrome browser without opening a visible window.
# # Set to False if you want to watch the browser search Google (useful for demos)
# HEADLESS = True

# # How many Google result pages to scan per search query.
# # Each page has ~10 results. 3 pages = ~30 results per query.
# # More pages = more usernames but slower.
# GOOGLE_PAGES = 3
"""
Instagram Scraper — Configuration Settings
===========================================
Edit this file to change scraping behaviour.
"""

import os

# ─── Scraping Targets ─────────────────────────────────────────────────────────

HASHTAGS = [
     # Core Christian
    "christian",
    "christianinfluencer",
    "christiancreator",
    "christiancontent",

    # Faith & Spiritual
    "faith",
    "faithinspiration",
    "faithbased",
    "faithquotes",

    # Jesus / Bible
    "jesus",
    "jesuschrist",
    "bible",
    "bibleverse",
    "biblestudy",

    # Worship / Ministry
    "worship",
    "gospel",
    "christianmusic",
    "worshipleader",
    "churchlife",
    "ministry",

    # Motivation / Lifestyle
    "christianliving",
    "faithoverfear",
    "godisgood",
    "trustgod",
    "dailydevotional",




    # # Stock Market
    # "stockmarket",
    # "stockmarketindia",
    # "sharemarket",
    # "stockanalysis",
    # "stockmarketnews",
    # "equitymarket",

    # # Trading
    # "trading",
    # "trader",
    # "daytrading",
    # "swingtrading",
    # "optionstrading",
    # "futurestrading",
    # "forextrading",
    # "traderlife",
    # "priceactiontrading",

    # # Investing
    # "investing",
    # "investment",
    # "investingtips",
    # "longterminvesting",
    # "valueinvesting",
    # "wealthbuilding",
    # "passiveincome",
    # "portfolio",

    # # Finance
    # "finance",
    # "personalfinance",
    # "financialeducation",
    # "financialfreedom",
    # "moneytips",
    # "moneyeducation",

    # # Fintech
    # "fintech",
    # "digitalbanking",
    # "paymenttechnology",
    # "startupfinance",

    # # Indian Markets
    # "nifty50",
    # "banknifty",
    # "sensex",

    # # Technology
    # "tech",
    # "technology",
    # "coding",
    # "programming",
    # "softwaredeveloper",
    # "ai",
    # "machinelearning",
    # "datascience",

    # # Education
    # "education",
    # "learning",
    # "learnonline",
    # "studygram",
    # "edtech",
    # "careergrowth",

    # # Information / Knowledge
    # "knowledge",
    # "didyouknow",
    # "facts",
    # "dailyfacts",
    # "infographics",
]

# Minimum follower count to include an account
MIN_FOLLOWERS = 20000   # lowered slightly to capture niche finance educators

# How many posts to scan per hashtag (each post = 1 potential user)
MAX_POSTS_PER_HASHTAG = 50

# Max unique influencers to collect per hashtag
MAX_USERS_PER_HASHTAG = 30

# ─── Rate Limiting ────────────────────────────────────────────────────────────

PROFILE_DELAY_MIN = 8.0
PROFILE_DELAY_MAX = 15.0

HASHTAG_DELAY_MIN = 15.0
HASHTAG_DELAY_MAX = 30.0


# ─── Output ───────────────────────────────────────────────────────────────────

OUTPUT_DIR      = "data"
OUTPUT_CSV      = "data/influencers.csv"
CHECKPOINT_FILE = "data/checkpoint.json"


# ─── Instagram Login ──────────────────────────────────────────────────────────
# Set these via environment variables for security:
#   set IG_USERNAME=your_username
#   set IG_PASSWORD=your_password
# Or create a .env file and load it manually.

IG_USERNAME = os.environ.get("IG_USERNAME", "")
IG_PASSWORD = os.environ.get("IG_PASSWORD", "")


# ─── Category Keywords ────────────────────────────────────────────────────────

CATEGORY_KEYWORDS = {

    # "Stock Market": [
    #     "stockmarket", "stocks", "equity", "sharemarket",
    #     "nifty", "banknifty", "sensex", "stockanalysis",
    #     "technicalanalysis", "fundamentalanalysis",
    #     "marketupdate", "stocktips"
    # ],

    # "Trading": [
    #     "trading", "daytrading", "swingtrading",
    #     "optionstrading", "futurestrading",
    #     "trader", "intraday", "chartanalysis",
    #     "priceaction", "tradingsetup",
    #     "forextrading", "crypto trading"
    # ],

    # "Investment": [
    #     "investing", "investment", "longterminvesting",
    #     "valueinvesting", "wealthbuilding",
    #     "mutualfunds", "sip", "financialfreedom",
    #     "passiveincome", "portfolio",
    #     "dividends", "retirementplanning"
    # ],

    # "Technology": [
    #     "tech", "technology", "coding", "programming",
    #     "developer", "software", "ai",
    #     "artificialintelligence", "machinelearning",
    #     "datascience", "startup", "innovation",
    #     "gadgets", "techreview", "unboxing"
    # ],

    # "Education": [
    #     "education", "learning", "study",
    #     "onlinelearning", "edtech", "students",
    #     "teacher", "knowledge", "career",
    #     "skills", "selfimprovement",
    #     "productivity", "motivation"
    # ],

    # "Information": [
    #     "facts", "information", "didyouknow",
    #     "knowledge", "awareness",
    #     "explained", "insights",
    #     "analysis", "newsupdate",
    #     "infographic", "research"
    # ],
}

# ─── DM Settings ──────────────────────────────────────────────────────────────

SEND_DM = False   # ← Change to True to enable DM sending

DM_DELAY_MIN = 20.0   # seconds between each DM
DM_DELAY_MAX = 30.0

# ─── YOUR COLLABORATION MESSAGE ───────────────────────────────────────────────
# {username} gets replaced with the real username automatically

DM_MESSAGE = """Hi {full_name},

Great to meet you.

My name is [YOUR NAME HERE]. I would like to connect with you.
"""
# ─── Selenium Discovery Settings ─────────────────────────────────────────────

HEADLESS = False

GOOGLE_PAGES = 3