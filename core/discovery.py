"""
Username Discovery Engine — Selenium Edition
=============================================

Uses Selenium Chrome browser to search Google for Instagram profiles
related to finance, trading, investing, technology, education, and
informational content.

Flow:
1. Search Google: site:instagram.com {keyword} influencer
2. Extract Instagram profile URLs
3. Extract usernames
4. Paginate Google results
5. Fallback to Bing if Google blocks
6. Add curated seed accounts

Returns: list of Instagram usernames
"""

import re
import time
import random
from typing import List, Optional

from utils.logger import get_logger

logger = get_logger()

# ─────────────────────────────────────────────
# Username extraction regex
# ─────────────────────────────────────────────

IG_USERNAME_RE = re.compile(
    r'instagram\.com/([A-Za-z0-9_.]{1,30})(?:[/?#]|$)'
)

# Instagram system pages
SKIP_USERNAMES = {
    "p","reel","reels","explore","accounts","stories",
    "direct","tv","legal","about","press","api",
    "privacy","safety","help","support","directory",
    "music","blog","jobs","developer","contact",
    "login","signup","web"
}

# ─────────────────────────────────────────────
# Google Search Queries
# ─────────────────────────────────────────────

SEARCH_QUERIES = {
    "christian": [
    "site:instagram.com christian influencer",
    "site:instagram.com christian content creator",
    "site:instagram.com bible teacher instagram",
    "site:instagram.com gospel preacher instagram",
    "site:instagram.com christian motivational speaker instagram",
    "site:instagram.com faith based influencer instagram",
    "site:instagram.com christian youth leader instagram",
    "site:instagram.com worship leader instagram",
    "site:instagram.com christian pastor instagram",
    "site:instagram.com jesus influencer instagram",
],

    # "stockmarket": [
    #     "site:instagram.com stock market influencer",
    #     "site:instagram.com stock market educator",
    #     "site:instagram.com stock market trader",
    #     "site:instagram.com stock trading instagram",
    #     "site:instagram.com stock market tips instagram",
    #     "site:instagram.com indian stock market influencer",
    #     "site:instagram.com stock analysis instagram",
    #     "site:instagram.com stock market mentor",
    # ],

    # "trading": [
    #     "site:instagram.com trading influencer",
    #     "site:instagram.com day trading educator",
    #     "site:instagram.com swing trader instagram",
    #     "site:instagram.com options trader instagram",
    #     "site:instagram.com forex trader instagram",
    #     "site:instagram.com crypto trader instagram",
    #     "site:instagram.com trading mentor instagram",
    #     "site:instagram.com trading academy instagram",
    # ],

    # "investment": [
    #     "site:instagram.com investment advisor instagram",
    #     "site:instagram.com investing influencer",
    #     "site:instagram.com investment mentor",
    #     "site:instagram.com long term investor instagram",
    #     "site:instagram.com wealth building instagram",
    #     "site:instagram.com portfolio investor instagram",
    #     "site:instagram.com value investing instagram",
    # ],

    # "finance": [
    #     "site:instagram.com finance influencer",
    #     "site:instagram.com personal finance influencer",
    #     "site:instagram.com money management instagram",
    #     "site:instagram.com financial freedom influencer",
    #     "site:instagram.com finance educator instagram",
    #     "site:instagram.com budgeting tips instagram",
    # ],

    # "fintech": [
    #     "site:instagram.com fintech influencer",
    #     "site:instagram.com fintech startup instagram",
    #     "site:instagram.com fintech entrepreneur instagram",
    #     "site:instagram.com digital banking influencer",
    #     "site:instagram.com payment technology influencer",
    # ],

    # "technology": [
    #     "site:instagram.com tech influencer",
    #     "site:instagram.com technology creator instagram",
    #     "site:instagram.com coding developer instagram",
    #     "site:instagram.com ai technology influencer",
    #     "site:instagram.com startup founder instagram",
    #     "site:instagram.com software developer instagram",
    #     "site:instagram.com gadget reviewer instagram",
    #     "site:instagram.com tech educator instagram",
    # ],

    # "education": [
    #     "site:instagram.com education influencer",
    #     "site:instagram.com online learning educator",
    #     "site:instagram.com study tips influencer",
    #     "site:instagram.com educational content creator",
    #     "site:instagram.com learning mentor instagram",
    #     "site:instagram.com career guidance influencer",
    #     "site:instagram.com skill development instagram",
    # ],

    # "information": [
    #     "site:instagram.com knowledge page instagram",
    #     "site:instagram.com facts page instagram",
    #     "site:instagram.com informative content creator",
    #     "site:instagram.com educational reels instagram",
    #     "site:instagram.com daily knowledge instagram",
    #     "site:instagram.com infographic page instagram",
    # ],
}
# ─────────────────────────────────────────────
# Seed Accounts (Fallback)
# ─────────────────────────────────────────────

SEED_ACCOUNTS = {

    "stockmarket": [
        "pranjalkamra",
        "ca_rachana_phadke_ranade",
        "zerodhaonline",
        "marketgurukul",
    ],

    "trading": [
        "boomingbulls",
        "tradingchanakya",
        "powerofstocks",
    ],

    "technology": [
        "mkbhd",
        "techburner",
        "unboxtherapy",
        "mrwhosetheboss",
    ],

    "education": [
        "khanacademy",
        "unacademy",
        "physicswallah",
        "study_iq",
    ],
}


class DiscoveryEngine:

    def __init__(self, headless: bool = True, google_pages: int = 3):
        self.headless = headless
        self.google_pages = google_pages
        self._driver = None

    # ─────────────────────────────────────────
    # Public Method
    # ─────────────────────────────────────────

    def discover(self, hashtag: str, max_users: int = 80) -> List[str]:

        usernames = []

        queries = self._get_queries(hashtag)

        logger.info(f"Searching Google for #{hashtag}")

        try:

            driver = self._get_driver()

            for query in queries:

                found = self._selenium_google_search(driver, query)

                self._add_unique(usernames, found)

                logger.info(f"Query '{query}' → {len(found)} users")

                if len(usernames) >= max_users:
                    break

                time.sleep(random.uniform(3,6))

        except Exception as e:
            logger.warning(f"Selenium error: {e}")

        logger.info(f"After Google: {len(usernames)} usernames")

        if len(usernames) < 20:

            logger.info("Trying Bing fallback")

            bing = self._bing_search(hashtag)

            self._add_unique(usernames, bing)

        seeds = SEED_ACCOUNTS.get(hashtag.lower(), [])

        self._add_unique(usernames, seeds)

        logger.info(f"Total collected: {len(usernames)}")

        return usernames[:max_users]
    def close(self):
        if self._driver:
            try:
                self._driver.quit()
                logger.info("Chrome browser closed")
            except Exception:
                pass
            self._driver = None


    # ─────────────────────────────────────────
    # Google Search via Selenium
    # ─────────────────────────────────────────

    def _selenium_google_search(self, driver, query):

        from selenium.webdriver.common.by import By

        usernames = []

        url = f"https://www.google.com/search?q={query.replace(' ','+')}"

        driver.get(url)

        time.sleep(random.uniform(2,4))

        for page in range(self.google_pages):

            links = driver.find_elements(By.TAG_NAME,"a")

            for link in links:

                try:

                    href = link.get_attribute("href") or ""

                    username = self._extract_username(href)

                    if username and username not in usernames:

                        usernames.append(username)

                except Exception:
                    pass

            try:

                next_btn = driver.find_element(By.ID,"pnnext")

                next_btn.click()

                time.sleep(random.uniform(3,6))

            except Exception:
                break

        return usernames

    # ─────────────────────────────────────────
    # Bing fallback
    # ─────────────────────────────────────────

    def _bing_search(self, hashtag):

        import requests

        usernames = []

        query = f"site:instagram.com {hashtag} influencer"

        url = f"https://www.bing.com/search?q={query.replace(' ','+')}"

        headers = {
            "User-Agent":
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }

        try:

            r = requests.get(url, headers=headers, timeout=10)

            if r.status_code == 200:

                found = IG_USERNAME_RE.findall(r.text)

                for u in found:

                    if u not in SKIP_USERNAMES and u not in usernames:

                        usernames.append(u)

        except Exception as e:
            logger.debug(e)

        return usernames

    # ─────────────────────────────────────────
    # Chrome Driver
    # ─────────────────────────────────────────

    def _get_driver(self):

        if self._driver:
            return self._driver

        import undetected_chromedriver as uc

        options = uc.ChromeOptions()

        if self.headless:
            options.add_argument("--headless=new")

        options.add_argument("--start-maximized")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")

        driver = uc.Chrome(options=options)

        # Extra stealth
        driver.execute_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)

        self._driver = driver
        return driver
        # ─────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────

    @staticmethod
    def _extract_username(url: str) -> Optional[str]:

        if "instagram.com" not in url:
            return None

        match = IG_USERNAME_RE.search(url)

        if not match:
            return None

        username = match.group(1).lower()

        if username in SKIP_USERNAMES:
            return None

        return username

    def _get_queries(self, hashtag):

        if hashtag.lower() in SEARCH_QUERIES:
            return SEARCH_QUERIES[hashtag.lower()]

        return [
            f"site:instagram.com {hashtag} influencer"
        ]

    @staticmethod
    def _add_unique(target, source):

        for u in source:

            if u not in target:

                target.append(u)