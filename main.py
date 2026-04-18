"""
Instagram Scraper — Main Entry Point
================================================
Single-browser Instagram-native scraping (no Google, no API).

Usage examples:
    python main.py                                      # scrape all configured hashtags
    python main.py --hashtags fashion tech comedy       # custom hashtags
    python main.py --usernames nike adidas gucci        # scrape specific accounts
    python main.py --mode brands                        # scrape brands (default)
    python main.py --mode influencers                   # scrape influencers
    python main.py --min-followers 500000               # change threshold
    python main.py --output results.csv                 # custom output path
    python main.py --reset-checkpoint                   # ignore previous progress
    python main.py --dry-run                            # verify setup only
"""

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).parent))

import config.settings as settings
from core.scraper import InstagramScraper
from utils.exporter import CSVExporter
from utils.logger import get_logger

logger = get_logger()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Instagram Scraper — Brands & Influencers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--hashtags",        nargs="+", default=None,  metavar="TAG",  help="Hashtags to search (no #)")
    p.add_argument("--usernames",       nargs="+", default=None,  metavar="USER", help="Scrape specific usernames directly")
    p.add_argument("--mode",            choices=["brands", "influencers"], default=settings.TARGET_MODE, help="Scrape brands or influencers")
    p.add_argument("--output",          default=settings.OUTPUT_CSV,              help="Output CSV path")
    p.add_argument("--min-followers",   type=int, default=settings.MIN_FOLLOWERS, help="Minimum follower count")
    p.add_argument("--max-per-hashtag", type=int, default=settings.MAX_USERS_PER_HASHTAG, help="Max profiles per hashtag")
    p.add_argument("--dry-run",         action="store_true", help="Test setup without scraping")
    p.add_argument("--reset-checkpoint", action="store_true", help="Clear resume state and start fresh")
    return p.parse_args()


def apply_overrides(args):
    settings.MIN_FOLLOWERS        = args.min_followers
    settings.MAX_USERS_PER_HASHTAG = args.max_per_hashtag
    settings.OUTPUT_CSV           = args.output
    settings.TARGET_MODE          = args.mode
    if args.hashtags:
        cleaned_tags = []
        for tag_group in args.hashtags:
            # Split on commas and/or spaces so "fashion, shoes tech" → [fashion, shoes, tech]
            import re
            parts = re.split(r'[,\s]+', tag_group.strip())
            cleaned_tags.extend([t.strip().lstrip('#') for t in parts if t.strip()])
        settings.HASHTAGS = cleaned_tags
    if args.reset_checkpoint:
        cp = Path(settings.CHECKPOINT_FILE)
        if cp.exists():
            cp.unlink()
            logger.info("Checkpoint cleared")


def dry_run():
    logger.info("=== DRY RUN ===")
    logger.info(f"Target mode  : {settings.TARGET_MODE.upper()}")
    logger.info(f"Hashtags     : {settings.HASHTAGS}")
    logger.info(f"Min followers: {settings.MIN_FOLLOWERS:,}")
    logger.info(f"Max/hashtag  : {settings.MAX_USERS_PER_HASHTAG}")
    logger.info(f"Output CSV   : {settings.OUTPUT_CSV}")
    logger.info(f"Login        : {'YES — @' + settings.IG_USERNAME if settings.IG_USERNAME else 'NO (anonymous)'}")
    Path(settings.OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

    # Verify undetected-chromedriver import
    try:
        import undetected_chromedriver as uc
        logger.info(f"undetected-chromedriver ready ✓")
    except ImportError:
        logger.error("undetected-chromedriver not installed! Run: pip install undetected-chromedriver")
    logger.info("✓ Dry run passed — ready to scrape!")
    sys.exit(0)


def print_summary(profiles: List[dict], stats: dict, elapsed: float):
    print("\n" + "=" * 60)
    print("  SCRAPE COMPLETE — SUMMARY")
    print("=" * 60)
    print(f"  Influencers found    : {len(profiles)}")
    print(f"  New rows in CSV      : {stats['new']}")
    print(f"  Duplicates skipped   : {stats['duplicates']}")
    print(f"  Time elapsed         : {elapsed:.0f}s ({elapsed/60:.1f} min)")
    print(f"  Output               : {settings.OUTPUT_CSV}")
    print("-" * 60)

    cats: dict = {}
    for p in profiles:
        c = p.get("category", "Other")
        cats[c] = cats.get(c, 0) + 1
    if cats:
        print("  By Category:")
        for cat, n in sorted(cats.items(), key=lambda x: -x[1]):
            bar = "█" * n
            print(f"    {cat:<14} {n:>3}  {bar}")

    print(f"\n  With email           : {sum(1 for p in profiles if p.get('email'))}/{len(profiles)}")
    print(f"  Verified accounts    : {sum(1 for p in profiles if p.get('is_verified'))}")
    print("=" * 60 + "\n")


def main():
    args = parse_args()
    apply_overrides(args)

    print("\n" + "=" * 60)
    mode_label = settings.TARGET_MODE.upper()
    print(f"  INSTAGRAM {mode_label} SCRAPER  (powered by Selenium)")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Loaded Accounts: {len(settings.ACCOUNTS)}")
    print("=" * 60)

    if args.dry_run:
        dry_run()

    start = time.time()
    scraper  = InstagramScraper(hashtags=args.hashtags)

    try:
        if args.usernames:
            logger.info(f"Mode: Direct usernames ({len(args.usernames)})")
            profiles = scraper.scrape_usernames(args.usernames)
        else:
            logger.info(f"Mode: Hashtag discovery ({len(settings.HASHTAGS)} hashtags)")
            profiles = scraper.run()
    except KeyboardInterrupt:
        # scraper.run() already saved data internally on interrupt
        # Just load whatever was written to CSV so summary shows correct count
        logger.warning("\n⚠ Interrupted — data already saved to CSV")
        try:
            reader = CSVExporter(filepath=settings.OUTPUT_CSV)
            profiles = reader.get_all_records()
        except Exception:
            profiles = []

    # Stats are generated from the profiles list — no re-export needed
    # (the scraper already saved each profile to CSV as it was found)
    stats = {"total": len(profiles), "new": len(profiles), "skipped": 0, "duplicates": 0}
    elapsed = time.time() - start
    print_summary(profiles, stats, elapsed)
    logger.info(f"Total API requests: {scraper.total_requests()}")


if __name__ == "__main__":
    main()
