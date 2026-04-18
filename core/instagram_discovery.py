import re
import time
import random
from typing import List, Optional, Set

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    StaleElementReferenceException,
)

from utils.logger import get_logger
import config.settings as g_settings

logger = get_logger()

# Paths that are NOT user profiles
SKIP_PATHS = ["/explore/", "/p/", "/reel/", "/reels/", "/stories/",
              "/tags/", "/locations/", "/accounts/", "/direct/"]


class InstagramDiscovery:
    """
    Discovers Instagram usernames from hashtag explore pages.
    Operates on the same Chrome driver used for login, scraping, and DMs.
    """

    def __init__(self, driver):
        self.driver = driver

    # ── Public API ────────────────────────────────────────────────────────────

    def discover(self, hashtag: str, max_posts: int = 50) -> List[str]:
        """
        Navigate to a hashtag page, scroll to load posts, visit each post,
        and extract the poster's username.

        Args:
            hashtag:   The hashtag to search (without #)
            max_posts: Maximum number of posts to scan

        Returns:
            List of unique Instagram usernames discovered
        """
        # Clean the hashtag (remove spaces, #)
        hashtag = hashtag.replace(" ", "").replace("#", "").strip()
        tag_url = f"https://www.instagram.com/explore/tags/{hashtag}/"

        logger.info(f"  Navigating to #{hashtag} ...")
        try:
            self.driver.get(tag_url)
            time.sleep(random.uniform(2.5, 4.0))
            self._close_popups()
        except Exception as e:
            logger.error(f"  Could not load hashtag page #{hashtag}: {e}")
            return []

        # Step 1: Scroll and collect post URLs
        post_hrefs = self._scroll_and_collect_posts(max_posts)
        if not post_hrefs:
            logger.warning(f"  No posts found for #{hashtag}")
            return []

        logger.info(f"  Collected {len(post_hrefs)} unique post links for #{hashtag}")

        # Step 2: Visit each post and extract usernames
        usernames: List[str] = []
        seen: Set[str] = set()

        for i, post_url in enumerate(post_hrefs, start=1):
            if len(usernames) >= max_posts:
                break

            try:
                username = self._extract_username_from_post(post_url, i, len(post_hrefs))

                if not username:
                    continue

                if username in seen:
                    logger.debug(f"    Duplicate username @{username}, skipping")
                    continue

                seen.add(username)
                usernames.append(username)
                logger.debug(f"    Discovered @{username} ({len(usernames)} so far)")

            except KeyboardInterrupt:
                raise
            except Exception as e:
                logger.debug(f"    Error on post [{i}]: {e}")
                continue

            # Minimal safety loop padding
            time.sleep(0.5)

        logger.info(f"  #{hashtag}: discovered {len(usernames)} unique usernames")
        return usernames

    # ── Scrolling ─────────────────────────────────────────────────────────────

    def _scroll_and_collect_posts(self, max_posts: int) -> List[str]:
        """
        Scroll the Instagram hashtag page and accumulate /p/ hrefs.
        Uses a persistent set to survive DOM virtualization (Instagram
        recycles DOM nodes as you scroll).
        """
        logger.info(f"  Scrolling to load posts (target: {max_posts})...")

        all_hrefs: Set[str] = set()
        last_height = self.driver.execute_script("return document.body.scrollHeight")
        scrolls = 0
        no_new_scrolls = 0

        while scrolls < g_settings.MAX_SCROLLS:
            try:
                # Collect all /p/ links currently visible in the DOM
                current_posts = self.driver.find_elements(
                    By.XPATH, '//a[contains(@href, "/p/")]'
                )
                before = len(all_hrefs)

                for link in current_posts:
                    try:
                        href = link.get_attribute("href")
                        if href and "/p/" in href:
                            all_hrefs.add(href)
                    except StaleElementReferenceException:
                        continue

                newly_added = len(all_hrefs) - before
                logger.debug(
                    f"    Scroll {scrolls + 1}: +{newly_added} new | "
                    f"{len(all_hrefs)} total"
                )

                # Check if we've hit our target
                if len(all_hrefs) >= max_posts:
                    logger.info(f"    Reached target of {max_posts} posts")
                    break

                # Scroll down
                self.driver.execute_script(
                    "window.scrollTo(0, document.body.scrollHeight);"
                )
                time.sleep(g_settings.SCROLL_PAUSE)
                self._close_popups()

                # Check if page grew
                new_height = self.driver.execute_script(
                    "return document.body.scrollHeight"
                )
                if new_height == last_height:
                    no_new_scrolls += 1
                    if no_new_scrolls >= 8:
                        logger.info("    No more content loading, stopping scroll")
                        break
                else:
                    no_new_scrolls = 0

                last_height = new_height
                scrolls += 1

            except KeyboardInterrupt:
                raise
            except Exception as e:
                logger.debug(f"    Scroll error: {e}")
                scrolls += 1
                continue

        logger.info(
            f"    Scrolling done: {scrolls} scrolls | "
            f"{len(all_hrefs)} posts accumulated"
        )
        return list(all_hrefs)[:max_posts]

    # ── Username Extraction from Post ─────────────────────────────────────────

    def _extract_username_from_post(
        self, post_url: str, index: int, total: int
    ) -> Optional[str]:
        """
        Visit a post URL and extract the poster's username.
        Uses 4 fallback strategies (adapted from demo.py).
        """
        logger.debug(f"    [{index}/{total}] Opening post: {post_url}")

        try:
            self.driver.get(post_url)
            time.sleep(random.uniform(g_settings.DISCOVERY_POST_DELAY_MIN, g_settings.DISCOVERY_POST_DELAY_MAX))
            self._close_popups()
        except Exception as e:
            logger.debug(f"    Could not load post: {e}")
            return None

        username = None

        # Strategy 1: Username span with specific CSS classes
        try:
            WebDriverWait(self.driver, 8).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "span._ap3a._aaco._aacw[dir='auto']")
                )
            )
            span = self.driver.find_element(
                By.CSS_SELECTOR, "span._ap3a._aaco._aacw[dir='auto']"
            )
            text = span.text.strip()
            if text and " " not in text and len(text) > 1:
                username = text
        except (TimeoutException, NoSuchElementException):
            pass

        # Strategy 2: Post header container with profile link
        if not username:
            try:
                container = self.driver.find_element(
                    By.CSS_SELECTOR, "div._aaqt"
                )
                for a in container.find_elements(
                    By.CSS_SELECTOR, "a._a6hd[href][role='link']"
                ):
                    href = a.get_attribute("href") or ""
                    if href and not any(s in href for s in SKIP_PATHS):
                        part = href.rstrip("/").split("/")[-1]
                        if part and len(part) > 1:
                            username = part
                            break
            except (NoSuchElementException, StaleElementReferenceException):
                pass

        # Strategy 3: Profile picture alt text
        if not username:
            try:
                img = self.driver.find_element(
                    By.CSS_SELECTOR, 'header img[alt*="profile picture"]'
                )
                alt = img.get_attribute("alt") or ""
                if "'s profile picture" in alt:
                    username = alt.split("'s profile picture")[0].strip()
            except NoSuchElementException:
                pass

        # Strategy 4: Any profile link in the article
        if not username:
            try:
                for a in self.driver.find_elements(
                    By.CSS_SELECTOR, 'article a[role="link"][href^="/"]'
                ):
                    href = a.get_attribute("href") or ""
                    if href and not any(s in href for s in SKIP_PATHS):
                        part = href.rstrip("/").split("/")[-1]
                        if part and len(part) > 1:
                            username = part
                            break
            except (NoSuchElementException, StaleElementReferenceException):
                pass

        if username:
            logger.debug(f"      Found username: @{username}")
        else:
            logger.debug(f"      Could not extract username from post")

        return username

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _close_popups(self):
        """Dismiss common Instagram popups (cookie consent, notifications, etc.)."""
        popup_xpaths = [
            '//button[contains(text(),"Not Now")]',
            '//button[contains(text(),"Not now")]',
            '//button[contains(text(),"Allow all cookies")]',
            '//button[contains(text(),"Accept All")]',
            '//button[contains(text(),"Accept")]',
            '//div[@role="dialog"]//button[contains(text(),"Not Now")]',
            '//button[contains(text(),"Close")]',
        ]
        for xpath in popup_xpaths:
            try:
                btn = self.driver.find_element(By.XPATH, xpath)
                btn.click()
                time.sleep(0.8)
            except NoSuchElementException:
                continue
            except Exception:
                continue
