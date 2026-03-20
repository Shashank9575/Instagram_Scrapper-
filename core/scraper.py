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
# ─────────────────────────────────────────────────────────────────────────────

from core.discovery import DiscoveryEngine
from core.profile_fetcher import SeleniumProfileFetcher
from utils.exporter import CSVExporter
from utils.logger import get_logger
from config.settings import (
    HASHTAGS, MIN_FOLLOWERS, OUTPUT_CSV,
    MAX_POSTS_PER_HASHTAG, MAX_USERS_PER_HASHTAG,
    PROFILE_DELAY_MIN, PROFILE_DELAY_MAX,
    HASHTAG_DELAY_MIN, HASHTAG_DELAY_MAX,
    CHECKPOINT_FILE, HEADLESS, GOOGLE_PAGES,
    IG_USERNAME, IG_PASSWORD,
    SEND_DM, DM_MESSAGE, DM_DELAY_MIN, DM_DELAY_MAX,
)

logger = get_logger()


class InstagramScraper:

    def __init__(self, hashtags: Optional[List[str]] = None):
        self.hashtags = hashtags or HASHTAGS
        self._seen_usernames: Set[str] = set()
        self._load_checkpoint()
        self._discovery = DiscoveryEngine(headless=HEADLESS, google_pages=GOOGLE_PAGES)
        self._fetcher: Optional[SeleniumProfileFetcher] = None
        self._request_count = 0
        self._exporter = CSVExporter(filepath=OUTPUT_CSV)
        self._total_saved = 0
        self._total_dm_sent = 0
        self._dm_failed: List[str] = []
        self._insta_driver = None

    # ── Public ────────────────────────────────────────────────────────────────

    def run(self) -> List[Dict[str, Any]]:
        all_profiles: List[Dict] = []
        logger.info(f"Starting — {len(self.hashtags)} hashtags | min {MIN_FOLLOWERS:,} followers")
        logger.info("Mode: 100% Selenium — no Instagram API calls")
        logger.info(f"DM Sending: {'ENABLED' if SEND_DM else 'DISABLED'}")
        logger.info(f"Output: {OUTPUT_CSV}")

        self._instagram_login()

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
                    delay = random.uniform(HASHTAG_DELAY_MIN, HASHTAG_DELAY_MAX)
                    logger.info(f"  Waiting {delay:.0f}s before next hashtag...")
                    time.sleep(delay)

        except KeyboardInterrupt:
            logger.warning("\n⚠ Interrupted by user.")

        self._discovery.close()
        if self._insta_driver:
            try:
                self._insta_driver.quit()
                logger.info("Instagram Chrome browser closed")
            except Exception:
                pass
            self._insta_driver = None
        logger.info(f"Total profiles saved: {self._total_saved}")
        if SEND_DM:
            logger.info(f"Total DMs sent: {self._total_dm_sent}")
            if self._dm_failed:
                logger.warning(f"DMs failed for: {', '.join(self._dm_failed)}")
        return self._deduplicate(all_profiles)

    def scrape_usernames(self, usernames: List[str]) -> List[Dict[str, Any]]:
        logger.info(f"Direct scrape: {len(usernames)} usernames")
        self._instagram_login()
        fetcher = self._get_fetcher()
        profiles = []
        for u in usernames:
            p = fetcher.fetch(u, source="manual")
            if p:
                profiles.append(p)
                self._save_profile_now(p)
                if SEND_DM:
                    self._send_dm(p["username"])
            self._rate_limit()
        self._discovery.close()
        if self._insta_driver:
            try:
                self._insta_driver.quit()
                logger.info("Instagram Chrome browser closed")
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

    def _dismiss_popups(self, driver):
        """Dismiss common Instagram popups (cookie consent, notifications, save login, etc.)."""
        from selenium.webdriver.common.by import By
        from selenium.common.exceptions import NoSuchElementException
        popup_xpaths = [
            "//button[contains(text(),'Allow')]",
            "//button[contains(text(),'Accept')]",
            "//button[contains(text(),'Allow all cookies')]",
            "//button[contains(text(),'Only allow essential cookies')]",
            "//button[contains(text(),'Save Info')]",
            "//button[contains(text(),'Save info')]",
            "//button[text()='Save Info']",
            "//button[contains(text(),'Not Now')]",
            "//button[text()='Not Now']",
        ]
        for xpath in popup_xpaths:
            try:
                btn = driver.find_element(By.XPATH, xpath)
                btn.click()
                time.sleep(1)
                logger.debug(f"Dismissed popup: {xpath}")
            except NoSuchElementException:
                continue

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

    def _save_cookies(self, driver):
        """Save current session cookies to ig_cookies.json."""
        try:
            with open("ig_cookies.json", "w", encoding="utf-8") as f:
                json.dump(driver.get_cookies(), f)
            logger.info("💾 Session saved")
        except Exception as e:
            logger.warning(f"Could not save cookies: {e}")

    # ── Instagram Login ───────────────────────────────────────────────────────

    def _instagram_login(self):
        from pathlib import Path
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.common.exceptions import TimeoutException, NoSuchElementException

        driver = self._get_instagram_driver()
        self._insta_driver = driver

        # ── Try loading saved session first ──────────────────────────────────
        cookies_path = Path("ig_cookies.json")

        if cookies_path.exists():
            logger.info("Loading saved Instagram session...")
            driver.get("https://www.instagram.com/")
            time.sleep(3)

            with open(cookies_path, "r", encoding="utf-8") as f:
                cookies = json.load(f)

            # L7 FIX: Sanitize cookies before restoring
            safe_cookies = self._sanitize_cookies(cookies)
            for cookie in safe_cookies:
                try:
                    driver.add_cookie(cookie)
                except Exception as e:
                    logger.debug(f"Skipped cookie {cookie.get('name')}: {e}")

            driver.refresh()
            time.sleep(4)

            if self._is_logged_in(driver):
                logger.info("✅ Logged in via saved cookies")
                return
            else:
                logger.warning("Saved session expired — logging in with credentials")

        if not IG_USERNAME or not IG_PASSWORD:
            if SEND_DM:
                logger.error("DM sending requires login. Set IG_USERNAME + IG_PASSWORD environment variables")
            else:
                logger.warning("No login — running without credentials")
            return

        try:
            # L1 FIX: Go directly to login page (no redundant homepage loads)
            logger.info("Opening Instagram login page...")
            driver.get("https://www.instagram.com/accounts/login/")

            # L8 FIX: Wait for element instead of force-reloading
            wait = WebDriverWait(driver, 30)
            time.sleep(3)

            # Dismiss cookie/consent popup if present
            self._dismiss_popups(driver)

            logger.info("Login page loaded")

            # ── Wait for username field ───────────────────────────────────────
            logger.info("Waiting for username field...")
            try:
                username_field = wait.until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "input[name='username']"))
                )
            except TimeoutException:
                # L2 FIX: Use a genuinely different selector as fallback
                try:
                    username_field = wait.until(
                        EC.element_to_be_clickable((By.XPATH, "//input[@aria-label='Phone number, username, or email']"))
                    )
                except TimeoutException:
                    logger.error("Username field not found — Instagram page may not have loaded")
                    logger.error("Try setting HEADLESS = False in settings.py to debug visually")
                    return

            # ── Type username ──────────────────────────────────────────────
            driver.execute_script("arguments[0].scrollIntoView(true);", username_field)
            time.sleep(0.3)
            username_field.click()
            time.sleep(0.3)
            username_field.clear()
            time.sleep(0.2)

            logger.info(f"Typing username: @{IG_USERNAME}")
            for char in IG_USERNAME:
                username_field.send_keys(char)
                time.sleep(random.uniform(0.05, 0.15))

            time.sleep(0.5)

            # ── Find and fill password field ─────────────────────────────
            try:
                password_field = wait.until(
                    EC.element_to_be_clickable((By.NAME, "password"))
                )
            except TimeoutException:
                # L3 FIX: Use a genuinely different selector as fallback
                try:
                    password_field = wait.until(
                        EC.element_to_be_clickable((By.XPATH, "//input[@aria-label='Password']"))
                    )
                except TimeoutException:
                    logger.error("Password field not found")
                    return

            driver.execute_script("arguments[0].scrollIntoView(true);", password_field)
            time.sleep(0.3)
            password_field.click()
            time.sleep(0.3)
            password_field.clear()
            time.sleep(0.2)

            logger.info("Typing password...")
            for char in IG_PASSWORD:
                password_field.send_keys(char)
                time.sleep(random.uniform(0.05, 0.15))

            # L4 FIX: Reduced from 8-15s to 1-2s — natural human pause
            time.sleep(random.uniform(1.0, 2.0))

            # ── Click submit ─────────────────────────────────────────────
            try:
                submit_btn = wait.until(
                    EC.element_to_be_clickable((By.XPATH, "//button[@type='submit']"))
                )
                submit_btn.click()
            except TimeoutException:
                from selenium.webdriver.common.keys import Keys
                password_field.send_keys(Keys.RETURN)

            logger.info("Login submitted — waiting for redirect...")
            time.sleep(8)  # Instagram takes time to process login

            # ── Check result ─────────────────────────────────────────────
            if self._is_logged_in(driver):
                logger.info(f"✓ Logged in successfully as @{IG_USERNAME}")

                # L5 FIX: Dismiss "Save Your Login Info?" popup
                time.sleep(2)
                self._dismiss_popups(driver)
                time.sleep(2)
                # L6 FIX: Dismiss "Turn on Notifications?" popup
                self._dismiss_popups(driver)

                self._save_cookies(driver)

            # ⚠️ Instagram checkpoint / 2FA
            elif "challenge" in driver.current_url or "checkpoint" in driver.current_url:
                logger.warning("⚠ Instagram requires verification (2FA/checkpoint)")
                logger.warning("👉 Complete it manually in browser (60 sec)")

                time.sleep(60)

                if self._is_logged_in(driver):
                    logger.info("✅ Verification completed")
                    time.sleep(2)
                    self._dismiss_popups(driver)
                    time.sleep(2)
                    self._dismiss_popups(driver)
                    self._save_cookies(driver)
                else:
                    logger.warning("❌ Verification failed — login not established")

            # ❌ LOGIN FAILED
            else:
                logger.warning(f"❌ Login failed — current URL: {driver.current_url}")
                # One more check — sometimes login succeeds but popup blocks detection
                time.sleep(3)
                self._dismiss_popups(driver)
                time.sleep(2)
                if self._is_logged_in(driver):
                    logger.info("✓ Login succeeded after popup dismissal")
                    self._save_cookies(driver)
                else:
                    logger.warning("Possible reasons:")
                    logger.warning("- Wrong credentials")
                    logger.warning("- Instagram blocked automation")
                    logger.warning("- Page not loaded properly")

        except Exception as e:
            logger.warning(f"Login error: {e}")
            logger.warning("Continuing without login")
    # ── Hashtag Scraping ──────────────────────────────────────────────────────

    def _scrape_hashtag(self, hashtag: str) -> List[Dict]:
        candidates = self._discovery.discover(hashtag, max_users=MAX_POSTS_PER_HASHTAG)

        if not candidates:
            logger.warning(f"  No candidates found for #{hashtag}")
            return []

        logger.info(f"  Visiting {len(candidates)} profiles in Chrome...")
        fetcher  = self._get_fetcher()
        profiles = []

        for username in candidates:
            if len(profiles) >= MAX_USERS_PER_HASHTAG:
                break
            if username in self._seen_usernames:
                continue
            self._seen_usernames.add(username)

            try:
                # Step 1: Scrape the profile
                data = fetcher.fetch(username, source=hashtag)

                if data:
                    profiles.append(data)

                    # Step 2: Save to CSV immediately
                    self._save_profile_now(data)

                    # Step 3: Send DM if enabled
                    if SEND_DM:
                        self._send_dm(data)

            except KeyboardInterrupt:
                logger.warning(f"  Interrupted during @{username} — all saved data is safe")
                raise
            except Exception as e:
                logger.debug(f"  Error on @{username}: {e}")

            self._rate_limit()

        logger.info(f"  #{hashtag} done: {len(profiles)} influencers found")
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

            personalized_message = DM_MESSAGE.format(username=username, full_name=full_name)

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
                except Exception as e:
                    logger.warning(f"ENTER failed: {e}")

            # Step 9: Wait before next DM
            dm_delay = random.uniform(DM_DELAY_MIN, DM_DELAY_MAX)
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
                min_followers=MIN_FOLLOWERS
            )
        return self._fetcher

    def _rate_limit(self):
        delay = random.uniform(PROFILE_DELAY_MIN, PROFILE_DELAY_MAX)
        logger.debug(f"  Waiting {delay:.1f}s between profiles")
        time.sleep(delay)

    def _save_checkpoint(self):
        try:
            Path(CHECKPOINT_FILE).parent.mkdir(parents=True, exist_ok=True)
            with open(CHECKPOINT_FILE, "w") as f:
                json.dump({"seen": list(self._seen_usernames)}, f)
        except Exception as e:
            logger.warning(f"Checkpoint error: {e}")

    def _load_checkpoint(self):
        try:
            if Path(CHECKPOINT_FILE).exists():
                with open(CHECKPOINT_FILE) as f:
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
    # Dedicated Driver for Instagram 
    def _get_instagram_driver(self):
        if self._insta_driver:
            return self._insta_driver

        import undetected_chromedriver as uc
        from config.settings import HEADLESS

        options = uc.ChromeOptions()
        
        if HEADLESS:
            options.add_argument("--headless=new")
            
        options.add_argument("--start-maximized")
        options.add_argument("--disable-background-timer-throttling")
        options.add_argument("--disable-backgrounding-occluded-windows")
        options.add_argument("--disable-renderer-backgrounding")

        driver = uc.Chrome(options=options)

        driver.execute_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)

        self._insta_driver = driver
        return driver
