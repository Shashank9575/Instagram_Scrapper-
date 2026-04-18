"""
Profile Fetcher — Selenium Edition
====================================
Visits each Instagram profile URL directly in Chrome and extracts data.

Extraction priority:
1. JSON blobs in <script> tags (fast & complete)
2. DOM-based extraction (reliable when JSON is stripped — from demo.py)
3. Meta tag extraction (last resort, minimal data)

Data extracted per profile:
- username, full_name, bio, followers, following, post_count
- email (regex from bio), category, hashtags, verified, business
"""

import re
import json
import time
import random
from typing import Dict, Optional, List, Any

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
)

from core.parser import extract_email, extract_hashtags, detect_category
from utils.logger import get_logger

logger = get_logger()

# ── Regex patterns for page parsing ──────────────────────────────────────────

# Followers count from page — multiple formats Instagram uses
FOLLOWERS_RE = re.compile(
    r'"edge_followed_by"\s*:\s*\{\s*"count"\s*:\s*(\d+)',
)
FOLLOWERS_META_RE = re.compile(
    r'([\d,\.]+[KMB]?)\s*Followers',
    re.IGNORECASE,
)

# JSON blob in script tags
JSON_DATA_RE = re.compile(
    r'window\._sharedData\s*=\s*(\{.+?\});\s*</script>',
    re.DOTALL,
)
ADDITIONAL_DATA_RE = re.compile(
    r'window\.__additionalDataLoaded\s*\(\s*["\'].*?["\']\s*,\s*(\{.+?\})\s*\)\s*;',
    re.DOTALL,
)


class SeleniumProfileFetcher:
    """
    Fetches Instagram profile data using the Chrome browser (Selenium).
    Reuses the same driver instance used for login and discovery.
    """

    def __init__(self, driver, min_followers: int = 100_000):
        self._driver      = driver
        self._min_followers = min_followers
        self._request_count = 0

    def fetch(self, username: str, source: str = "") -> Optional[Dict[str, Any]]:
        """
        Visit instagram.com/{username}/ in Chrome and extract profile data.
        Returns None if profile doesn't exist or followers < threshold.
        """
        url = f"https://www.instagram.com/{username}/"
        try:
            self._driver.get(url)
            self._request_count += 1

            # Wait for page to load
            time.sleep(random.uniform(2.5, 4.5))

            # Get full page source
            page_source = self._driver.page_source

            # Check for login wall or error page
            if self._is_blocked(page_source):
                logger.debug(f"  @{username}: login wall or error page")
                return None

            # Try to extract data from embedded JSON first (most reliable)
            data = self._extract_from_json(page_source, username)
            if not data:
                # Fallback 2: DOM-based extraction (from demo.py — reliable)
                data = self._extract_from_dom(username)
            if not data:
                # Fallback 3: HTML meta tags (minimal data)
                data = self._extract_from_meta(page_source, username)

            if not data:
                logger.debug(f"  Could not parse profile data for @{username}")
                return None

            if data["followers"] < self._min_followers:
                logger.debug(f"  Skip @{username}: {data['followers']:,} followers")
                return None

            data["discovered_via"] = source
            logger.info(
                f"  ✓ @{username} | {data['followers']:,} followers | "
                f"{data['category']} | email: {data['email'] or 'N/A'}"
            )
            return data

        except Exception as e:
            logger.debug(f"  Error fetching @{username}: {e}")
            return None

    def total_requests(self) -> int:
        return self._request_count

    # ── JSON Extraction (primary method) ─────────────────────────────────────

    def _extract_from_json(self, html: str, username: str) -> Optional[Dict]:
        """Extract profile data from JSON blobs embedded in the page."""

        # Try window._sharedData first
        user_node = self._find_user_in_shared_data(html)

        # Try script tags containing JSON with user data
        if not user_node:
            user_node = self._find_user_in_script_tags(html, username)

        if not user_node:
            return None

        return self._build_profile_dict(user_node, username)

    def _find_user_in_shared_data(self, html: str) -> Optional[Dict]:
        """Look for user data in window._sharedData JSON."""
        match = JSON_DATA_RE.search(html)
        if not match:
            return None
        try:
            data = json.loads(match.group(1))
            # Navigate to user node
            entry_data = data.get("entry_data", {})
            profile_page = entry_data.get("ProfilePage", [{}])
            if profile_page:
                return profile_page[0].get("graphql", {}).get("user")
        except Exception:
            pass
        return None

    def _find_user_in_script_tags(self, html: str, username: str) -> Optional[Dict]:
        """Search all <script> tags for JSON containing user profile data."""
        # Find all script tag contents
        scripts = re.findall(r'<script[^>]*type="application/json"[^>]*>(.*?)</script>', html, re.DOTALL)
        scripts += re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)

        for script in scripts:
            if "edge_followed_by" not in script and "follower_count" not in script:
                continue
            try:
                # Try direct JSON parse
                data = json.loads(script.strip())
                user = self._find_user_in_dict(data)
                if user:
                    return user
            except Exception:
                # Try extracting JSON objects from the script
                for obj_match in re.finditer(r'\{[^{}]{100,}\}', script):
                    try:
                        obj = json.loads(obj_match.group())
                        user = self._find_user_in_dict(obj)
                        if user:
                            return user
                    except Exception:
                        continue
        return None

    def _find_user_in_dict(self, data: Any) -> Optional[Dict]:
        """Recursively search a dict for a user profile node."""
        if not isinstance(data, dict):
            return None
        # Check if this IS a user node
        if "edge_followed_by" in data and "biography" in data:
            return data
        if "follower_count" in data and "biography" in data:
            return data
        # Recurse into nested dicts
        for value in data.values():
            if isinstance(value, dict):
                result = self._find_user_in_dict(value)
                if result:
                    return result
            elif isinstance(value, list):
                for item in value:
                    result = self._find_user_in_dict(item)
                    if result:
                        return result
        return None

    def _build_profile_dict(self, user: Dict, username: str) -> Dict:
        """Normalize a user JSON node into our standard profile dict."""
        followers = (
            user.get("edge_followed_by", {}).get("count")
            or user.get("follower_count")
            or 0
        )
        following = (
            user.get("edge_follow", {}).get("count")
            or user.get("following_count")
            or 0
        )
        post_count = (
            user.get("edge_owner_to_timeline_media", {}).get("count")
            or user.get("media_count")
            or 0
        )
        bio = (user.get("biography") or "").strip()
        full_name = (user.get("full_name") or "").strip()
        external_url = user.get("external_url") or ""
        is_verified = user.get("is_verified", False)
        is_business = user.get("is_business_account", False)

        bio_hashtags = extract_hashtags(bio)
        email = extract_email(bio) or extract_email(external_url)
        category = detect_category(bio, bio_hashtags)

        return {
            "username":            user.get("username", username),
            "full_name":           full_name,
            "email":               email,
            "bio":                 bio.replace("\n", " "),
            "followers":           int(followers),
            "following":           int(following),
            "post_count":          int(post_count),
            "category":            category,
            "hashtags_used":       ", ".join(bio_hashtags[:20]),
            "is_verified":         is_verified,
            "is_business_account": is_business,
            "profile_url":         f"https://www.instagram.com/{username}/",
            "external_url":        external_url,
            "discovered_via":      "",
        }

    # ── Meta Tag Extraction (fallback) ────────────────────────────────────────

    def _extract_from_meta(self, html: str, username: str) -> Optional[Dict]:
        """
        Fallback: extract basic data from HTML meta tags.
        Less complete but works when JSON isn't available.
        """
        # og:description usually has: "X Followers, Y Following, Z Posts"
        desc_match = re.search(r'<meta[^>]+property="og:description"[^>]+content="([^"]+)"', html)
        title_match = re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"', html)

        if not desc_match:
            return None

        description = desc_match.group(1)
        title = title_match.group(1) if title_match else username

        # Parse followers from description: "1.2M Followers, 400 Following, 850 Posts"
        followers = self._parse_count_from_text(description, "Followers")
        if followers == 0:
            return None

        following  = self._parse_count_from_text(description, "Following")
        post_count = self._parse_count_from_text(description, "Posts")

        # Bio is in the page title or description after the counts
        bio_match = re.search(r'See Instagram.*?from (.+?)(?:\s*\||\s*-|$)', description)
        bio = bio_match.group(1).strip() if bio_match else ""

        bio_hashtags = extract_hashtags(bio)
        email = extract_email(bio)
        category = detect_category(bio, bio_hashtags)

        return {
            "username":            username,
            "full_name":           title.split("(")[0].strip(),
            "email":               email,
            "bio":                 bio,
            "followers":           followers,
            "following":           following,
            "post_count":          post_count,
            "category":            category,
            "hashtags_used":       ", ".join(bio_hashtags[:20]),
            "is_verified":         False,
            "is_business_account": False,
            "profile_url":         f"https://www.instagram.com/{username}/",
            "external_url":        "",
            "discovered_via":      "",
        }

    # ── DOM-Based Extraction (from demo.py) ────────────────────────────────

    def _extract_from_dom(self, username: str) -> Optional[Dict]:
        """
        Extract profile data directly from the visible DOM elements.
        This is more reliable than JSON when Instagram strips script data.
        """
        try:
            self._expand_bio()

            followers = self._get_followers_from_dom()
            if followers == 0:
                return None

            category_label = self._get_category_from_dom()

            # Extract bio text
            bio = self._get_bio_from_dom()

            # Extract full name from header
            full_name = ""
            try:
                name_el = self._driver.find_element(
                    By.CSS_SELECTOR, "header section span[dir='auto']"
                )
                full_name = name_el.text.strip()
            except NoSuchElementException:
                pass

            bio_hashtags = extract_hashtags(bio)
            email = extract_email(bio)

            # Use DOM category if available, else detect from bio
            if category_label:
                category = category_label
            else:
                category = detect_category(bio, bio_hashtags)

            return {
                "username":            username,
                "full_name":           full_name,
                "email":               email,
                "bio":                 bio.replace("\n", " "),
                "followers":           followers,
                "following":           0,
                "post_count":          0,
                "category":            category,
                "hashtags_used":       ", ".join(bio_hashtags[:20]),
                "is_verified":         False,
                "is_business_account": False,
                "profile_url":         f"https://www.instagram.com/{username}/",
                "external_url":        "",
                "discovered_via":      "",
            }
        except Exception as e:
            logger.debug(f"  DOM extraction failed for @{username}: {e}")
            return None

    def _expand_bio(self):
        """Click the 'more' button to expand truncated bios."""
        try:
            more_btn = self._driver.find_element(
                By.XPATH,
                '//div[@role="button"][.//span[contains(text(),"more")]]'
            )
            more_btn.click()
            time.sleep(1)
        except NoSuchElementException:
            pass
        except Exception:
            pass

    def _get_bio_from_dom(self) -> str:
        """Extract bio text from visible DOM spans."""
        try:
            WebDriverWait(self._driver, 5).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "span._ap3a._aaco._aacu[dir='auto']")
                )
            )
            bio_spans = self._driver.find_elements(
                By.CSS_SELECTOR, "span._ap3a._aaco._aacu[dir='auto']"
            )
            # The longest span is typically the bio
            return max((s.text.strip() for s in bio_spans), key=len, default="")
        except (TimeoutException, NoSuchElementException):
            return ""

    def _get_followers_from_dom(self) -> int:
        """
        Extract follower count from the profile page DOM.
        Uses 3 strategies (from demo.py).
        """
        # Strategy 1: title attribute (raw integer with commas)
        for xpath in [
            '//span[contains(text(),"followers")]//span[@title]',
            '//span[contains(text(),"followers")]/preceding-sibling::span[@title]',
            '//span[@title][following-sibling::span[contains(text(),"followers")]]',
        ]:
            try:
                el = self._driver.find_element(By.XPATH, xpath)
                title = el.get_attribute("title")
                if title:
                    return int(title.replace(",", ""))
            except (NoSuchElementException, ValueError):
                pass

        # Strategy 2: visible abbreviated label (38.2K, 1.1M)
        try:
            el = self._driver.find_element(
                By.XPATH,
                '//span[contains(text(),"followers")]'
                '//span[contains(@class,"html-span")]'
            )
            text = el.text.strip()
            if text:
                return self._parse_count_from_text(text + " Followers", "Followers")
        except NoSuchElementException:
            pass

        # Strategy 3: meta description fallback
        try:
            meta = self._driver.find_element(
                By.XPATH, '//meta[@name="description"]'
            )
            content = meta.get_attribute("content") or ""
            m = re.search(r"([\d,]+)\s+Followers", content, re.IGNORECASE)
            if m:
                return int(m.group(1).replace(",", ""))
        except (NoSuchElementException, ValueError):
            pass

        return 0

    def _get_category_from_dom(self) -> str:
        """
        Extract the Instagram profile category label (e.g., 'Digital creator',
        'Musician/band', 'Public figure').
        Uses CSS class fingerprinting from demo.py.
        """
        # Strategy 1: exact CSS class fingerprint
        for selector in [
            "div._ap3a._aaco._aacu._aacy._aad6._aade[dir='auto']",
            "div._ap3a._aaco._aacu._aad6._aade[dir='auto']",
        ]:
            try:
                el = self._driver.find_element(By.CSS_SELECTOR, selector)
                text = el.text.strip()
                if text and text.lower() != "follow":
                    return text
            except NoSuchElementException:
                pass

        # Strategy 2: span variant
        try:
            el = self._driver.find_element(
                By.CSS_SELECTOR,
                "span._ap3a._aaco._aacu._aacy._aad6._aade[dir='auto']"
            )
            text = el.text.strip()
            if text and text.lower() != "follow":
                return text
        except NoSuchElementException:
            pass

        # Strategy 3: XPath with class attributes
        try:
            candidates = self._driver.find_elements(
                By.XPATH,
                '//*[@dir="auto" and contains(@class,"_aad6") '
                'and contains(@class,"_aade")]'
            )
            for el in candidates:
                text = el.text.strip()
                if text and len(text) <= 60 and text.lower() != "follow":
                    return text
        except NoSuchElementException:
            pass

        return ""

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _is_blocked(self, html: str) -> bool:
        """Check if Instagram showed a login wall or error instead of profile."""
        blocked_signals = [
            "You must be logged in",
            "Log in to Instagram",
            "Page Not Found",
            "Sorry, this page",
            "isn't available",
        ]
        return any(signal.lower() in html.lower() for signal in blocked_signals)

    @staticmethod
    def _parse_count_from_text(text: str, label: str) -> int:
        """
        Parse a follower/following/post count from text like '1.2M Followers'.
        Handles K (thousands), M (millions), B (billions).
        """
        pattern = re.compile(
            rf'([\d,\.]+)\s*([KMB]?)\s*{label}',
            re.IGNORECASE,
        )
        match = pattern.search(text)
        if not match:
            return 0
        try:
            num_str = match.group(1).replace(",", "")
            num = float(num_str)
            suffix = match.group(2).upper()
            multipliers = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}
            return int(num * multipliers.get(suffix, 1))
        except Exception:
            return 0
