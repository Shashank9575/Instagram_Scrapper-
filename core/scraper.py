import json
import random
import ssl
import time
import urllib3
from pathlib import Path
import charset_normalizer
from typing import Dict, List, Optional, Set, Any

# ── SSL patch for corporate proxy/firewall ────────────────────────────────────
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
_orig_ssl = ssl.create_default_context
def _no_verify(*a, **kw):
    ctx = _orig_ssl(*a, **kw)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx
ssl.create_default_context = _no_verify
ssl._create_default_https_context = ssl._create_unverified_context
# ─────────────────────────────────────────────────────────────────────────────

from core.instagram_discovery import InstagramDiscovery
from core.profile_fetcher import SeleniumProfileFetcher
from utils.exporter import CSVExporter
from utils.logger import get_logger
import config.settings as g_settings

logger = get_logger()

def resolve_spintax(text: str) -> str:
    """Resolves spintax strings like {Hi|Hello} dynamically."""
    import re
    while True:
        match = re.search(r'\{([^{}]+)\}', text)
        if not match:
             break
        options = match.group(1).split('|')
        text = text[:match.start()] + random.choice(options) + text[match.end():]
    return text

class InstagramScraper:

    def __init__(self, hashtags: Optional[List[str]] = None):
        self.hashtags = hashtags or g_settings.HASHTAGS
        self._seen_usernames: Set[str] = set()
        self._load_checkpoint()
        self._fetcher: Optional[SeleniumProfileFetcher] = None
        self._discovery: Optional[InstagramDiscovery] = None
        self._request_count = 0
        self._current_account_idx = 0
        self._profiles_this_session = 0
        self.profiles_per_account = float('inf')
        self._exporter = CSVExporter(filepath=g_settings.OUTPUT_CSV)
        self._total_saved = 0
        self._total_dm_sent = 0
        self._dm_failed: List[str] = []
        self._insta_driver = None

    # ── Public ────────────────────────────────────────────────────────────────

    def run(self) -> List[Dict[str, Any]]:
        import config.settings as _s
        import math
        all_profiles: List[Dict] = []
        logger.info(f"Starting — {len(self.hashtags)} hashtags | min {_s.MIN_FOLLOWERS:,} followers")
        logger.info("Mode: Single-browser Instagram-native scraping")
        logger.info(f"DM Sending: {'ENABLED' if g_settings.SEND_DM else 'DISABLED'}")
        logger.info(f"Output: {_s.OUTPUT_CSV}")

        # Auto-calculate account rotation logic based on target limits
        total_targets = len(self.hashtags) * _s.MAX_USERS_PER_HASHTAG
        num_accounts = len(_s.ACCOUNTS)
        if num_accounts > 1:
            self.profiles_per_account = max(1, math.ceil(total_targets / num_accounts))
        else:
            self.profiles_per_account = float('inf')

        # Step 1: Login to Instagram (single Chrome browser)
        self._instagram_login()

        interrupted = False
        try:
            for idx, hashtag in enumerate(self.hashtags, 1):
                logger.info(f"[{idx}/{len(self.hashtags)}] Hashtag: #{hashtag}")
                try:
                    profiles = self._scrape_hashtag(hashtag)
                    all_profiles.extend(profiles)
                    self._save_checkpoint()
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    logger.error(f"Error on #{hashtag}: {e}")

                if idx < len(self.hashtags):
                    delay = random.uniform(g_settings.HASHTAG_DELAY_MIN, g_settings.HASHTAG_DELAY_MAX)
                    logger.info(f"  Waiting {delay:.0f}s before next hashtag...")
                    time.sleep(delay)

        except KeyboardInterrupt:
            logger.warning("\n⚠ Interrupted by user.")
            interrupted = True

        # Cleanup — single browser
        if self._insta_driver:
            try:
                self._insta_driver.quit()
                logger.info("Chrome browser closed")
            except Exception:
                pass
            self._insta_driver = None
        logger.info(f"Total profiles saved: {self._total_saved}")
        if g_settings.SEND_DM:
            logger.info(f"Total DMs sent: {self._total_dm_sent}")
            if self._dm_failed:
                logger.warning(f"DMs failed for: {', '.join(self._dm_failed)}")
                
        if interrupted:
            raise KeyboardInterrupt
            
        return self._deduplicate(all_profiles)

    def scrape_usernames(self, usernames: List[str]) -> List[Dict[str, Any]]:
        import config.settings as _s
        import math
        
        logger.info(f"Direct scrape: {len(usernames)} usernames")
        
        # Auto-calculate account rotation logic based on targets
        total_targets = len(usernames)
        num_accounts = len(_s.ACCOUNTS)
        if num_accounts > 1:
            self.profiles_per_account = max(1, math.ceil(total_targets / num_accounts))
        else:
            self.profiles_per_account = float('inf')
            
        self._instagram_login()
        fetcher = self._get_fetcher()
        profiles = []
        for u in usernames:
            p = fetcher.fetch(u, source="manual")
            if p:
                profiles.append(p)
                self._save_profile_now(p)
                
                import config.settings as _s
                if getattr(_s, "AUTO_FOLLOW", False):
                    self._follow_user(p["username"])
                    
                if getattr(_s, "AUTO_LIKE_FIRST_POST", False) or getattr(_s, "AUTO_COMMENT", False):
                    self._engage_first_post(p["username"])
                    
                if g_settings.SEND_DM:
                    self._send_dm(p)
                    
                # Step 5: Rotate Account Check (Based on successful scrape)
                self._profiles_this_session += 1
                if self._profiles_this_session >= self.profiles_per_account:
                    self._switch_account()
                    
            self._rate_limit()
        if self._insta_driver:
            try:
                self._insta_driver.quit()
                logger.info("Chrome browser closed")
            except Exception:
                pass
            self._insta_driver = None
        return profiles

    def total_requests(self) -> int:
        base = self._request_count
        if self._fetcher:
            base += self._fetcher.total_requests()
        return base

    def _is_logged_in(self, driver):
        cookies = driver.get_cookies()
        return any(c['name'] == 'sessionid' for c in cookies)



    def _sanitize_cookies(self, cookies):
        """Strip keys that cause Selenium add_cookie() to fail."""
        safe_cookies = []
        for cookie in cookies:
            clean = {
                "name": cookie.get("name"),
                "value": cookie.get("value"),
                "domain": cookie.get("domain"),
                "path": cookie.get("path", "/"),
            }
            if cookie.get("secure"):
                clean["secure"] = cookie["secure"]
            if cookie.get("httpOnly"):
                clean["httpOnly"] = cookie["httpOnly"]
            safe_cookies.append(clean)
        return safe_cookies

    def _save_cookies(self, driver, username="default"):
        """Save current session cookies to ig_cookies_{username}.json."""
        try:
            with open(f"ig_cookies_{username}.json", "w", encoding="utf-8") as f:
                json.dump(driver.get_cookies(), f)
            logger.info(f"💾 Session saved for @{username}")
        except Exception as e:
            logger.warning(f"Could not save cookies: {e}")

    # ── Instagram Login ───────────────────────────────────────────────────────

    def _instagram_login(self, account=None):
        from pathlib import Path
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.common.exceptions import TimeoutException, NoSuchElementException
        import config.settings as _s

        driver = self._get_instagram_driver()
        self._insta_driver = driver

        if account is None:
            if not _s.ACCOUNTS:
                logger.error("No Instagram accounts configured in .env!")
                return
            account = _s.ACCOUNTS[self._current_account_idx % len(_s.ACCOUNTS)]

        username = account.get("username", "")
        password = account.get("password", "")

        # ── Step 1: Try loading saved session (cookies) ──────────────────────
        cookies_path = Path(f"ig_cookies_{username}.json")

        if cookies_path.exists():
            logger.info(f"Loading saved Instagram session for @{username}...")
            driver.get("https://www.instagram.com/")
            time.sleep(3)

            try:
                with open(cookies_path, "r", encoding="utf-8") as f:
                    cookies = json.load(f)

                safe_cookies = self._sanitize_cookies(cookies)
                for cookie in safe_cookies:
                    try:
                        driver.add_cookie(cookie)
                    except Exception as e:
                        logger.debug(f"Skipped cookie {cookie.get('name')}: {e}")

                driver.refresh()
                time.sleep(4)
                self._dismiss_popups(driver)

                if self._is_logged_in(driver):
                    logger.info(f"✅ Logged in via saved cookies as @{username}")
                    self._dismiss_popups(driver)
                    return
                else:
                    logger.warning("Saved session expired — will try fresh login")
            except Exception as e:
                logger.warning(f"Could not load cookies: {e}")

        # ── Step 2: Try automated login with credentials ─────────────────────
        if username and password:
            logger.info(f"Attempting automated login as @{username}...")
            if self._try_automated_login(driver, username, password):
                return
            logger.warning("Automated login failed — falling back to manual login")

        # ── Step 3: Manual login fallback (most reliable) ────────────────────
        logger.info(f"Opening Instagram for manual login (@{username})...")
        driver.get("https://www.instagram.com/")
        time.sleep(3)
        self._dismiss_popups(driver)

        # Check if already logged in (maybe from Step 2 partial success)
        if self._is_logged_in(driver):
            logger.info(f"✅ Already logged in as @{username}")
            self._save_cookies(driver, username)
            return

        # Prompt user to log in manually
        print("\n" + "=" * 60)
        print(f"  🔐 MANUAL LOGIN REQUIRED: @{username}")
        print("=" * 60)
        print("  Please log in to Instagram in the browser window.")
        print("  When fully logged in, come back here and press ENTER.")
        print("=" * 60)
        input("\n  Press ENTER when login is complete... ")
        print()

        time.sleep(3)
        self._dismiss_popups(driver)
        time.sleep(2)
        self._dismiss_popups(driver)

        if self._is_logged_in(driver):
            logger.info(f"✅ Manual login successful for @{username}")
            self._save_cookies(driver, username)
        else:
            logger.warning("⚠ Login could not be verified — continuing anyway")
            # Save cookies anyway in case session exists but detection failed
            self._save_cookies(driver, username)

    def _switch_account(self):
        import config.settings as _s
        if len(_s.ACCOUNTS) <= 1:
            return  # No point rotating if only 1 account configured

        self._current_account_idx += 1
        next_account = _s.ACCOUNTS[self._current_account_idx % len(_s.ACCOUNTS)]
        
        logger.info(f"\n🔄 Account rotation threshold reached! Switching to @{next_account['username']}...")
        
        driver = self._get_instagram_driver()
        driver.delete_all_cookies()
        time.sleep(2)
        
        self._instagram_login(account=next_account)
        self._profiles_this_session = 0

    def _try_automated_login(self, driver, username, password) -> bool:
        """Attempt automated login with stored credentials. Returns True on success."""
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.common.exceptions import TimeoutException

        try:
            driver.get("https://www.instagram.com/accounts/login/")
            wait = WebDriverWait(driver, 20)
            time.sleep(5)
            self._dismiss_popups(driver)

            # ── Find username field ──
            username_field = None
            for selector in [
                (By.CSS_SELECTOR, "input[name='username']"),
                (By.XPATH, "//input[@aria-label='Phone number, username, or email']"),
                (By.XPATH, "//input[@type='text']")
            ]:
                try:
                    # Use presence instead of clickable to bypass invisible overlays
                    username_field = wait.until(EC.presence_of_element_located(selector))
                    break
                except TimeoutException:
                    continue
                    
            if not username_field:
                logger.warning("Username field not found on login page")
                return False

            # Type username (forcefully via JS and standard events)
            driver.execute_script("arguments[0].scrollIntoView(true);", username_field)
            time.sleep(0.5)
            try:
                username_field.click()
            except Exception:
                pass # ignore if blocked by overlay
                
            driver.execute_script("arguments[0].value = '';", username_field)
            logger.info(f"Typing username: @{username}")
            
            # Send keys one by one. If standard send fails due to overlay, fallback to JS.
            try:
                for char in username:
                    username_field.send_keys(char)
                    time.sleep(random.uniform(0.05, 0.15))
            except Exception:
                # Fallback to JavaScript if send_keys is intercepted
                driver.execute_script(f"arguments[0].value = '{username}';", username_field)
                # Dispatch event to trigger React state update
                driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", username_field)

            # ── Find and fill password field ──
            password_field = None
            for selector in [
                (By.NAME, "password"),
                (By.XPATH, "//input[@type='password']"),
                (By.XPATH, "//input[@aria-label='Password']")
            ]:
                try:
                    password_field = wait.until(EC.presence_of_element_located(selector))
                    break
                except TimeoutException:
                    continue
                    
            if not password_field:
                logger.warning("Password field not found")
                return False

            driver.execute_script("arguments[0].scrollIntoView(true);", password_field)
            time.sleep(0.5)
            try:
                password_field.click()
            except Exception:
                pass
                
            driver.execute_script("arguments[0].value = '';", password_field)
            logger.info("Typing password...")
            
            try:
                for char in password:
                    password_field.send_keys(char)
                    time.sleep(random.uniform(0.05, 0.15))
            except Exception:
                driver.execute_script(f"arguments[0].value = '{password}';", password_field)
                driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", password_field)

            time.sleep(random.uniform(1.0, 2.0))

            # ── Click submit ──
            try:
                submit_btn = wait.until(
                    EC.presence_of_element_located((By.XPATH, "//button[@type='submit']"))
                )
                try:
                    submit_btn.click()
                except Exception:
                    # JavaScript click bypasses overlays
                    driver.execute_script("arguments[0].click();", submit_btn)
            except TimeoutException:
                # If no submit button, send ENTER key to password field
                try:
                    from selenium.webdriver.common.keys import Keys
                    password_field.send_keys(Keys.RETURN)
                except Exception:
                    # Dispatch ENTER keydown event via JS
                    driver.execute_script("arguments[0].dispatchEvent(new KeyboardEvent('keydown', {'key': 'Enter'}));", password_field)

            logger.info("Login submitted — waiting for redirect...")
            time.sleep(10)

            # Check result
            if self._is_logged_in(driver):
                logger.info(f"✓ Logged in successfully as @{username}")
                time.sleep(2)
                self._dismiss_popups(driver)
                time.sleep(2)
                self._dismiss_popups(driver)
                self._save_cookies(driver, username)
                return True

            # Check for 2FA / checkpoint
            if "challenge" in driver.current_url or "checkpoint" in driver.current_url:
                logger.warning("⚠ Instagram requires verification (2FA/checkpoint)")
                logger.warning("👉 Complete it manually in browser (90 sec timeout)")
                time.sleep(90)

                if self._is_logged_in(driver):
                    logger.info("✅ Verification completed")
                    time.sleep(2)
                    self._dismiss_popups(driver)
                    self._save_cookies(driver, username)
                    return True

            # Last attempt — dismiss popups and recheck
            time.sleep(3)
            self._dismiss_popups(driver)
            time.sleep(2)
            if self._is_logged_in(driver):
                logger.info("✓ Login succeeded after popup dismissal")
                self._save_cookies(driver, username)
                return True

            return False

        except Exception as e:
            logger.warning(f"Automated login error: {e}")
            return False

    # ── Hashtag Scraping (Instagram-Native) ────────────────────────────────────

    def _scrape_hashtag(self, hashtag: str) -> List[Dict]:
        """Discover usernames from Instagram hashtag page, then visit each profile."""
        discovery = self._get_discovery()
        import config.settings as dynamic_settings
        limit = dynamic_settings.MAX_USERS_PER_HASHTAG
        
        # Calculate a safe multiplier of posts to gather to guarantee hitting the users target
        dynamic_max_posts = max(50, limit * 3)
        
        # Step 1: Discover usernames from the hashtag page (same browser)
        candidates = discovery.discover(hashtag, max_posts=dynamic_max_posts)

        if not candidates:
            logger.warning(f"  No candidates found for #{hashtag}")
            return []

        logger.info(f"  Visiting {len(candidates)} profiles...")
        fetcher  = self._get_fetcher()
        profiles = []

        for username in candidates:
            if len(profiles) >= limit:
                break
            if username in self._seen_usernames:
                continue
            self._seen_usernames.add(username)

            try:
                # Step 2: Visit profile and scrape data
                data = fetcher.fetch(username, source=hashtag)

                if data:
                    profiles.append(data)

                    # Step 3: Save to CSV immediately
                    self._save_profile_now(data)

                    import config.settings as _s
                    if getattr(_s, "AUTO_FOLLOW", False):
                        self._follow_user(data["username"])

                    if getattr(_s, "AUTO_LIKE_FIRST_POST", False) or getattr(_s, "AUTO_COMMENT", False):
                        self._engage_first_post(data["username"])

                    # Step 4: Send DM if enabled
                    if g_settings.SEND_DM:
                        self._send_dm(data)

                    # Step 5: Rotate Account Check (Based on successful scrape)
                    self._profiles_this_session += 1
                    if self._profiles_this_session >= self.profiles_per_account:
                        self._switch_account()

            except KeyboardInterrupt:
                logger.warning(f"  Interrupted during @{username} — all saved data is safe")
                raise
            except Exception as e:
                logger.debug(f"  Error on @{username}: {e}")

            self._rate_limit()

        logger.info(f"  #{hashtag} done: {len(profiles)} profiles found")
        return profiles

    # ── Save Immediately ──────────────────────────────────────────────────────

    def _save_profile_now(self, profile: Dict):
        """Write this single profile to CSV right now."""
        try:
            stats = self._exporter.export([profile])
            if stats["new"] > 0:
                self._total_saved += 1
                logger.info(
                    f"  💾 Saved @{profile['username']} "
                    f"| {profile['followers']:,} followers "
                    f"| {profile['category']} "
                    f"(total: {self._total_saved})"
                )
        except Exception as e:
            logger.warning(f"  Save error for @{profile['username']}: {e}")

    # ── Actions & Interactivity ───────────────────────────────────────────────

    def _follow_user(self, username: str):
        """Clicks the 'Follow' or 'Follow Back' button on the current profile page."""
        try:
            from selenium.webdriver.common.by import By
            import time
            driver = getattr(self, "_insta_driver", None)
            if not driver: return
            
            time.sleep(1.5)
            
            follow_btn = None
            for xpath in [
                "//button[.//div[text()='Follow']]",
                "//button[.//div[text()='Follow Back']]",
                "//div[@role='button' and text()='Follow']",
                "//button[text()='Follow']",
                "//div[contains(text(), 'Follow')]/ancestor::button"
            ]:
                try:
                    elems = driver.find_elements(By.XPATH, xpath)
                    for el in elems:
                        if el.is_displayed():
                            follow_btn = el
                            break
                    if follow_btn: break
                except Exception:
                    continue
                    
            if follow_btn:
                driver.execute_script("arguments[0].click();", follow_btn)
                logger.info(f"  👤 Followed @{username}")
                time.sleep(random.uniform(2.0, 4.0))
            else:
                logger.debug(f"  Follow button not found for @{username} (might already be following)")
        except Exception as e:
            logger.debug(f"  Follow action failed: {e}")

    def _engage_first_post(self, username: str):
        """Finds the first post/reel on the profile, opens it, and executes Like and Comment actions."""
        import config.settings as _s
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.webdriver.common.keys import Keys
            from selenium.webdriver.common.action_chains import ActionChains
            from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException

            driver = getattr(self, "_insta_driver", None)
            if not driver: return

            do_like = getattr(_s, "AUTO_LIKE_FIRST_POST", False)
            do_comment = getattr(_s, "AUTO_COMMENT", False)

            logger.info(f"  ❤️ Engaging first post for @{username} (like={do_like}, comment={do_comment})...")

            # Scroll down to post grid area
            driver.execute_script("window.scrollTo(0, 400);")
            time.sleep(1.5)

            # 1. Find the first post link
            first_post = None
            for selector in [
                "//a[contains(@href, '/p/')]",
                "//a[contains(@href, '/reel/')]"
            ]:
                try:
                    elems = driver.find_elements(By.XPATH, selector)
                    if elems:
                        first_post = elems[0]
                        break
                except Exception:
                    continue

            if not first_post:
                logger.warning(f"  ⚠ No posts found on profile for @{username}")
                return

            # Get the post URL before clicking (useful for fallback)
            post_href = first_post.get_attribute("href") or ""
            logger.info(f"  Found post: {post_href}")

            # 2. Click the post to open modal
            try:
                first_post.click()
            except Exception:
                driver.execute_script("arguments[0].click();", first_post)

            # 3. Wait for the post modal/article to actually load
            post_container = None
            try:
                post_container = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "article"))
                )
                logger.info(f"  Post modal loaded (article found)")
            except TimeoutException:
                # Fallback: maybe it navigated to the post page instead of modal
                logger.info(f"  No article found, trying dialog...")
                try:
                    post_container = driver.find_element(By.CSS_SELECTOR, "div[role='dialog']")
                except NoSuchElementException:
                    pass

            if not post_container:
                logger.warning(f"  ⚠ Post content never loaded for @{username}")
                return

            time.sleep(random.uniform(1.5, 2.5))

            # 4. Diagnostic: Log SVG aria-labels INSIDE the post container
            try:
                aria_elements = driver.execute_script("""
                    var container = arguments[0];
                    var results = [];
                    container.querySelectorAll('svg[aria-label]').forEach(function(el) {
                        results.push(el.getAttribute('aria-label'));
                    });
                    return results;
                """, post_container)
                logger.info(f"  🔍 SVG aria-labels in post: {aria_elements}")
            except Exception:
                logger.warning(f"  ⚠ Could not read SVG aria-labels")

            # 5. Handle Like
            if do_like:
                liked = False

                # Search ONLY inside the post container to avoid matching thumbnail SVGs
                like_svgs = post_container.find_elements(By.XPATH, ".//svg[@aria-label='Like']")
                unlike_svgs = post_container.find_elements(By.XPATH, ".//svg[@aria-label='Unlike']")

                if unlike_svgs:
                    logger.info(f"  Post already liked for @{username}")
                    liked = True
                elif like_svgs:
                    # Pick the FIRST VISIBLE Like SVG (skip hidden ones)
                    target_svg = None
                    for svg in like_svgs:
                        try:
                            if svg.is_displayed():
                                target_svg = svg
                                break
                        except StaleElementReferenceException:
                            continue
                    
                    if not target_svg:
                        target_svg = like_svgs[0]
                    
                    logger.info(f"  Found {len(like_svgs)} Like SVG(s), clicking visible one...")

                    # Strategy A: Find the nearest clickable ancestor and JS-click it
                    try:
                        driver.execute_script("""
                            var svg = arguments[0];
                            var el = svg.closest('[role="button"], button');
                            if (el) { el.click(); }
                            else { svg.parentElement.click(); }
                        """, target_svg)
                        time.sleep(1.5)
                        
                        # Verify: check if Unlike SVG appeared (confirms like registered)
                        verify_unlike = post_container.find_elements(By.XPATH, ".//svg[@aria-label='Unlike']")
                        if verify_unlike:
                            liked = True
                            logger.info(f"  ✅ Like verified (Unlike SVG appeared)")
                        else:
                            logger.info(f"  JS closest() click didn't register, trying ActionChains...")
                    except Exception as e1:
                        logger.info(f"  JS closest() failed ({e1})")

                    # Strategy B: ActionChains on the SVG's parent
                    if not liked:
                        try:
                            parent = target_svg.find_element(By.XPATH, "./..")
                            ActionChains(driver).move_to_element(parent).click().perform()
                            time.sleep(1.5)
                            verify_unlike = post_container.find_elements(By.XPATH, ".//svg[@aria-label='Unlike']")
                            if verify_unlike:
                                liked = True
                                logger.info(f"  ✅ Like verified via ActionChains parent click")
                        except Exception as e2:
                            logger.info(f"  ActionChains parent click failed ({e2})")

                    # Strategy C: Direct ActionChains click on SVG
                    if not liked:
                        try:
                            ActionChains(driver).move_to_element(target_svg).click().perform()
                            time.sleep(1.5)
                            verify_unlike = post_container.find_elements(By.XPATH, ".//svg[@aria-label='Unlike']")
                            if verify_unlike:
                                liked = True
                                logger.info(f"  ✅ Like verified via direct SVG click")
                        except Exception as e3:
                            logger.info(f"  Direct SVG click failed ({e3})")

                if not liked:
                    # Strategy D: Double-click on the post image/video (Instagram native gesture)
                    logger.info(f"  Trying double-click on post media...")
                    try:
                        media = None
                        for sel in [
                            "div[role='button'] img",
                            "article img",
                            "article video",
                            "div[role='dialog'] img",
                            "div[role='presentation'] img",
                        ]:
                            try:
                                candidates = post_container.find_elements(By.CSS_SELECTOR, sel)
                                for m in candidates:
                                    if m.is_displayed() and m.size.get('height', 0) > 100:
                                        media = m
                                        break
                                if media:
                                    break
                            except (NoSuchElementException, StaleElementReferenceException):
                                continue

                        if media:
                            ActionChains(driver).move_to_element(media).double_click().perform()
                            time.sleep(2.0)
                            verify_unlike = post_container.find_elements(By.XPATH, ".//svg[@aria-label='Unlike']")
                            if verify_unlike:
                                liked = True
                                logger.info(f"  ✅ Like verified via double-click on media")
                            else:
                                logger.warning(f"  Double-click performed but like not confirmed")
                        else:
                            logger.warning(f"  ⚠ No visible media found to double-click")
                    except Exception as e:
                        logger.warning(f"  ⚠ Double-click failed: {e}")

                if liked:
                    logger.info(f"  ❤️ Successfully liked post for @{username}")
                    time.sleep(random.uniform(1.5, 3.0))
                else:
                    logger.warning(f"  ⚠ Could not like post for @{username} — all strategies exhausted")

            # 5. Handle Comment
            if do_comment:
                try:
                    comments = getattr(_s, "COMMENTS_LIST", [])
                    if not comments:
                        logger.warning(f"  ⚠ COMMENTS_LIST is empty, skipping comment")
                    else:
                        comment_text = random.choice(comments)

                        # Step A: Find the comment textarea
                        comment_box = None
                        try:
                            comment_box = WebDriverWait(driver, 5).until(
                                EC.presence_of_element_located((By.CSS_SELECTOR, "textarea"))
                            )
                        except TimeoutException:
                            try:
                                comment_box = driver.find_element(By.XPATH, "//*[contains(@aria-label, 'comment') or contains(@aria-label, 'Comment')]")
                            except NoSuchElementException:
                                pass

                        if not comment_box:
                            logger.warning(f"  ⚠ Comment box not found for @{username} (comments may be disabled)")
                        else:
                            # Step B: Click to expand/focus
                            comment_box.click()
                            time.sleep(1.0)

                            # Step C: Re-find (Instagram replaces the element on focus)
                            try:
                                comment_box = driver.find_element(By.CSS_SELECTOR, "textarea")
                            except NoSuchElementException:
                                try:
                                    comment_box = driver.find_element(By.CSS_SELECTOR, "[contenteditable='true']")
                                except NoSuchElementException:
                                    logger.warning(f"  ⚠ Comment box disappeared after click for @{username}")
                                    comment_box = None

                            if comment_box:
                                # Step D: Click again to ensure focus
                                comment_box.click()
                                time.sleep(0.3)

                                # Step E: Type character by character
                                for char in comment_text:
                                    comment_box.send_keys(char)
                                    time.sleep(random.uniform(0.03, 0.08))

                                time.sleep(random.uniform(1.0, 2.0))

                                # Step F: Submit the comment
                                posted = False
                                for post_xpath in [
                                    "//div[@role='button' and text()='Post']",
                                    "//button[text()='Post']",
                                    "//div[text()='Post']",
                                    "//span[text()='Post']/ancestor::div[@role='button']",
                                    "//form//div[@role='button']",
                                ]:
                                    try:
                                        post_btn = driver.find_element(By.XPATH, post_xpath)
                                        if post_btn.is_displayed():
                                            driver.execute_script("arguments[0].click();", post_btn)
                                            posted = True
                                            break
                                    except (NoSuchElementException, StaleElementReferenceException):
                                        continue

                                if not posted:
                                    comment_box.send_keys(Keys.CONTROL, Keys.RETURN)

                                logger.info(f"  💬 Commented on @{username}: \"{comment_text}\"")
                                time.sleep(random.uniform(3.0, 5.0))

                except Exception as e:
                    logger.warning(f"  ⚠ Comment failed for @{username}: {e}")

            # 6. Close modal
            self._close_post_modal(driver)

        except Exception as e:
            logger.warning(f"  ⚠ Engage action failed for @{username}: {e}")
            try:
                self._close_post_modal(driver)
            except Exception:
                pass

    def _close_post_modal(self, driver):
        """Helper to reliably close the post modal via DOM click or ESC fallback."""
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.keys import Keys
        import time
        try:
            # Try clicking the Close SVG directly
            close_btn = driver.find_element(By.XPATH, "//svg[@aria-label='Close']")
            driver.execute_script("arguments[0].click();", close_btn)
        except Exception:
            # Fallback to ESC
            try:
                driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
            except Exception:
                pass
        time.sleep(1)

    # ── DM Sender ─────────────────────────────────────────────────────────────

    def _send_dm(self, profile: Dict):
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.common.keys import Keys
        from selenium.common.exceptions import TimeoutException, NoSuchElementException

        #driver = self._discovery._get_driver()
        driver = getattr(self, "_insta_driver", None)
        if driver is None:
            driver = self._get_instagram_driver()
            self._insta_driver = driver

        username = profile.get("username", "")
        full_name = profile.get("full_name", "") or username

        try:
            logger.info(f"  📨 Sending DM to @{username}...")

            # Step 1: Go to their profile
            driver.get(f"https://www.instagram.com/{username}/")
            time.sleep(random.uniform(3, 5))

            # Step 2: Dismiss any login/signup popup that's blocking the page
            # This is the main cause of "element click intercepted" error
            for popup_xpath in [
                "//div[@role='dialog']//button[contains(text(),'Not Now')]",
                "//button[contains(text(),'Not Now')]",
                "//button[contains(text(),'Close')]",
                "//div[@aria-label='Close']",
                "//button[@aria-label='Close']",
            ]:
                try:
                    btn = driver.find_element(By.XPATH, popup_xpath)
                    btn.click()
                    time.sleep(1)
                    logger.debug(f"  Dismissed popup for @{username}")
                    break
                except NoSuchElementException:
                    continue

            # Step 3: Scroll to top to ensure buttons are visible
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)

            wait = WebDriverWait(driver, 25)

            # Step 4: Click Message button using JavaScript to bypass overlay issues
            # Based on the exact HTML you shared: role="button" with text "Message"
            message_btn = None

            # Try finding by exact text content first
            try:
                message_btn = wait.until(
                    EC.presence_of_element_located((
                        By.XPATH,
                        "//div[@role='button'][normalize-space(text())='Message']"
                    ))
                )
            except TimeoutException:
                pass

            # Fallback selectors
            if not message_btn:
                for xpath in [
                    "//div[@role='button' and text()='Message']",
                    "//span[text()='Message']/ancestor::div[@role='button']",
                    "//div[contains(@class,'x1i10hfl') and text()='Message']",
                ]:
                    try:
                        message_btn = driver.find_element(By.XPATH, xpath)
                        break
                    except NoSuchElementException:
                        continue

            if not message_btn:
                logger.warning(f"  ⚠ Message button not found for @{username} — likely not logged in or private account")
                self._dm_failed.append(username)
                return

            # Use JavaScript click to bypass any overlay blocking normal click
            driver.execute_script("arguments[0].click();", message_btn)
            time.sleep(random.uniform(3, 5))

            # Step 5: Dismiss "Open in App" popup if it appears
            for popup_xpath in [
                "//button[text()='Not Now']",
                "//button[contains(text(),'Not Now')]",
                "//div[text()='Not Now']",
            ]:
                try:
                    btn = driver.find_element(By.XPATH, popup_xpath)
                    btn.click()
                    time.sleep(1)
                    break
                except NoSuchElementException:
                    continue

            # Step 6: Find message input box
            msg_input = None
            for xpath in [
                "//div[@aria-label='Message']",
                "//div[@role='textbox']",
                "//p[@class='xat24cr xdj266r']",
                "//div[@contenteditable='true']",
            ]:
                try:
                    msg_input = wait.until(EC.presence_of_element_located((By.XPATH, xpath)))
                    break
                except TimeoutException:
                    continue

            if not msg_input:
                logger.warning(f"  ⚠ Message box not found for @{username}")
                self._dm_failed.append(username)
                return

            # Step 7: Click and type message
            driver.execute_script("arguments[0].focus();", msg_input)
            time.sleep(0.5)
            msg_input.click()
            time.sleep(0.5)

            personalized_message = g_settings.DM_MESSAGE.format(username=username, full_name=full_name)
            
            # Dynamically resolve Spintax (e.g. {Hi|Hello}) so Instagram doesn't flag identical messages
            personalized_message = resolve_spintax(personalized_message)
            
            # Strip emojis to prevent ChromeDriver BMP crashes
            personalized_message = "".join(c for c in personalized_message if ord(c) <= 0xFFFF)

            # Send line by line (Much faster than character-by-character, but still safe for newlines)
            lines = personalized_message.split('\n')
            for i, line in enumerate(lines):
                if line:
                    msg_input.send_keys(line)
                
                # If this isn't the last line, insert a safe newline
                if i < len(lines) - 1:
                    msg_input.send_keys(Keys.SHIFT, Keys.ENTER)
                
                time.sleep(random.uniform(0.1, 0.3))

            time.sleep(random.uniform(0.5, 1.0))
            msg_input.send_keys(" ")
            time.sleep(0.5)
           
            # ── Step 8: Send message (ICON BUTTON FIX) ─────────────────────────

# ── Step 8: Send message (FINAL CORRECT VERSION) ─────────────────────────

            sent = False

            try:
                # Find ALL buttons near message box
                buttons = driver.find_elements(By.XPATH, "//button")

                for btn in buttons:
                    try:
                        # Check if button contains SVG (icon)
                        if btn.find_elements(By.XPATH, ".//*[name()='svg']"):

                            # VERY IMPORTANT: only click visible + enabled button near bottom
                            location = btn.location['y']

                            if location > 500:   # bottom area (DM zone)
                                driver.execute_script("arguments[0].click();", btn)
                                sent = True
                                logger.info(f"  ✅ DM sent to @{username}")
                                break

                    except Exception:
                        continue

            except Exception as e:
                logger.warning(f"Send button detection failed: {e}")

            # ── fallback ──
            if not sent:
                try:
                    msg_input.send_keys(Keys.ENTER)
                    logger.info(f"  ✅ DM sent via ENTER to @{username}")
                    sent = True
                except Exception as e:
                    logger.warning(f"ENTER failed: {e}")

            if sent:
                self._total_dm_sent += 1

            # Step 9: Wait before next DM
            dm_delay = random.uniform(g_settings.DM_DELAY_MIN, g_settings.DM_DELAY_MAX)
            logger.info(f"  Waiting {dm_delay:.0f}s before next DM...")
            time.sleep(dm_delay)

        except KeyboardInterrupt:
            raise
        except Exception as e:
            logger.warning(f"  ⚠ DM failed for @{username}: {e}")
            self._dm_failed.append(username)
        # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_fetcher(self) -> SeleniumProfileFetcher:
        if self._fetcher is None:
            driver = getattr(self, "_insta_driver", None)
            if driver is None:
                driver = self._get_instagram_driver()
                self._insta_driver = driver

            self._fetcher = SeleniumProfileFetcher(
                driver=driver,
                min_followers=g_settings.MIN_FOLLOWERS
            )
        return self._fetcher

    def _get_discovery(self) -> InstagramDiscovery:
        """Get the Instagram-native discovery engine (shares the same Chrome driver)."""
        if self._discovery is None:
            driver = getattr(self, "_insta_driver", None)
            if driver is None:
                driver = self._get_instagram_driver()
                self._insta_driver = driver
            self._discovery = InstagramDiscovery(driver=driver)
        return self._discovery

    def _rate_limit(self):
        delay = random.uniform(g_settings.PROFILE_DELAY_MIN, g_settings.PROFILE_DELAY_MAX)
        logger.debug(f"  Waiting {delay:.1f}s between profiles")
        time.sleep(delay)

    def _save_checkpoint(self):
        try:
            Path(g_settings.CHECKPOINT_FILE).parent.mkdir(parents=True, exist_ok=True)
            with open(g_settings.CHECKPOINT_FILE, "w") as f:
                json.dump({"seen": list(self._seen_usernames)}, f)
        except Exception as e:
            logger.warning(f"Checkpoint error: {e}")

    def _load_checkpoint(self):
        try:
            if Path(g_settings.CHECKPOINT_FILE).exists():
                with open(g_settings.CHECKPOINT_FILE) as f:
                    self._seen_usernames = set(json.load(f).get("seen", []))
                logger.info(f"Resumed: {len(self._seen_usernames)} already scraped")
        except Exception:
            self._seen_usernames = set()

    @staticmethod
    def _deduplicate(profiles: List[Dict]) -> List[Dict]:
        seen: Set[str] = set()
        result = []
        for p in profiles:
            if p["username"] not in seen:
                seen.add(p["username"])
                result.append(p)
        return result
    def _dismiss_popups(self, driver):
        """Dismiss common Instagram popups (cookie consent, notifications, save login, etc.)."""
        from selenium.webdriver.common.by import By
        from selenium.common.exceptions import NoSuchElementException
        popup_xpaths = [
            # Cookie banners
            "//button[contains(text(),'Allow all cookies')]",
            "//button[contains(text(),'Allow')]",
            "//button[contains(text(),'Accept')]",
            "//button[contains(text(),'Decline optional cookies')]",
            "//div[@role='button' and contains(text(),'Allow all cookies')]",
            
            # Login info banners
            "//button[contains(text(),'Save Info')]",
            "//button[contains(text(),'Save info')]",
            "//button[text()='Save Info']",
            "//div[@role='button' and contains(text(),'Save info')]",
            
            # Notifications banner
            "//button[contains(text(),'Not Now')]",
            "//button[text()='Not Now']",
            "//div[@role='button' and contains(text(),'Not Now')]",
        ]
        for xpath in popup_xpaths:
            try:
                btn = driver.find_element(By.XPATH, xpath)
                try:
                    btn.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", btn)
                time.sleep(1)
                logger.debug(f"Dismissed popup: {xpath}")
                break # Usually one popup at a time blocks the view
            except NoSuchElementException:
                continue

    # Dedicated Driver for Instagram 
    def _get_instagram_driver(self):
        if self._insta_driver:
            return self._insta_driver

        import undetected_chromedriver as uc
        import config.settings as g_settings

        options = uc.ChromeOptions()
        
        if g_settings.HEADLESS:
            options.add_argument("--headless=new")
            
        options.add_argument("--start-maximized")
        options.add_argument("--disable-background-timer-throttling")
        options.add_argument("--disable-backgrounding-occluded-windows")
        options.add_argument("--disable-renderer-backgrounding")
        
        # Implement proxy if enabled
        if getattr(g_settings, "USE_PROXY", False):
            try:
                from utils.proxy_util import create_proxy_extension
                logger.info(f"Setting up Proxy: {g_settings.PROXY_HOST}:{g_settings.PROXY_PORT}")
                proxy_ext_dir = create_proxy_extension(
                    g_settings.PROXY_HOST,
                    g_settings.PROXY_PORT,
                    g_settings.PROXY_USER,
                    g_settings.PROXY_PASS
                )
                if proxy_ext_dir:
                    options.add_argument(f"--load-extension={proxy_ext_dir}")
            except Exception as e:
                logger.warning(f"Failed to configure proxy extension: {e}")

        # Auto-detect installed Chrome version to prevent mismatch
        chrome_version = self._detect_chrome_version()

        try:
            if chrome_version:
                logger.info(f"Detected Chrome version: {chrome_version}")
                driver = uc.Chrome(options=options, version_main=chrome_version)
            else:
                logger.info("Could not detect Chrome version — letting driver auto-detect")
                driver = uc.Chrome(options=options)
                
            # Patch driver.quit to silently ignore WinError 6 on Windows __del__
            _original_quit = driver.quit
            def _quiet_quit(*args, **kwargs):
                try:
                    _original_quit(*args, **kwargs)
                except OSError:
                    pass
            driver.quit = _quiet_quit
            
        except Exception as e:
            logger.error(
                f"Failed to start Chrome browser. "
                f"Please ensure Google Chrome is installed. Details: {e}"
            )
            raise

        driver.execute_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)

        self._insta_driver = driver
        return driver

    @staticmethod
    def _detect_chrome_version() -> Optional[int]:
        """
        Auto-detect the installed Google Chrome major version.
        Checks Windows Registry, then falls back to common file paths.
        """
        import subprocess
        import re as _re

        # Method 1: Windows Registry (most reliable)
        try:
            result = subprocess.run(
                ['reg', 'query',
                 r'HKEY_CURRENT_USER\Software\Google\Chrome\BLBeacon',
                 '/v', 'version'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                match = _re.search(r'(\d+)\.\d+\.\d+\.\d+', result.stdout)
                if match:
                    return int(match.group(1))
        except Exception:
            pass

        # Method 2: Chrome executable --version flag
        chrome_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ]
        for path in chrome_paths:
            try:
                result = subprocess.run(
                    [path, '--version'],
                    capture_output=True, text=True, timeout=5
                )
                match = _re.search(r'(\d+)\.\d+\.\d+\.\d+', result.stdout)
                if match:
                    return int(match.group(1))
            except Exception:
                continue

        return None
