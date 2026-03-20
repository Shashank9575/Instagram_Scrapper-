"""
Profile Fetcher — Selenium Edition
====================================
Visits each Instagram profile URL directly in Chrome (already open from
discovery) and extracts data from the page HTML/JSON.

Why this approach:
- Uses the SAME Chrome browser already open for Google search
- No Instagram API calls at all — zero rate limiting risk
- Instagram serves the page normally to a real logged-in browser
- Data is extracted from JSON embedded in the page's <script> tags

Data extracted per profile:
- username, full_name, bio, followers, following, post_count
- email (regex from bio), category, hashtags, verified, business
"""

import re
import json
import time
import random
from typing import Dict, Optional, List, Any

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
    Reuses the same driver instance from DiscoveryEngine.
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
            if data:
                if data["followers"] < self._min_followers:
                    logger.debug(f"  Skip @{username}: {data['followers']:,} followers")
                    return None
                data["discovered_via"] = source
                logger.info(
                    f"  ✓ @{username} | {data['followers']:,} followers | "
                    f"{data['category']} | email: {data['email'] or 'N/A'}"
                )
                return data

            # Fallback: extract from HTML meta tags
            data = self._extract_from_meta(page_source, username)
            if data:
                if data["followers"] < self._min_followers:
                    logger.debug(f"  Skip @{username}: {data['followers']:,} followers")
                    return None
                data["discovered_via"] = source
                logger.info(
                    f"  ✓ @{username} | {data['followers']:,} followers | "
                    f"{data['category']} | email: {data['email'] or 'N/A'}"
                )
                return data

            logger.debug(f"  Could not parse profile data for @{username}")
            return None

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
