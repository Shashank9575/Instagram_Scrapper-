"""
CSV Exporter
============
Saves influencer data to CSV with:
- Auto-deduplication (no duplicate usernames)
- Append mode (safe to re-run)
- Timestamped backups
- Clean field ordering
"""

import csv
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any

from utils.logger import get_logger
import config.settings as g_settings

logger = get_logger()

# Output CSV columns — exactly 7 columns as required
CSV_COLUMNS = [
    "username",
    "full_name",
    "followers",
    "email",
    "bio",
    "profile_category",
    "hashtag",
    "profile_url",
]


class CSVExporter:
    """
    Handles all CSV write operations.

    Features:
    - Creates file + header if not exists
    - Appends new rows; skips duplicates (by username)
    - Creates backup before each write session
    - Returns export statistics
    """

    def __init__(self, filepath: str = None):
        self.filepath = filepath or g_settings.OUTPUT_CSV
        self._existing_usernames: set = set()
        self._backed_up_this_session: bool = False
        Path(g_settings.OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
        self._load_existing_usernames()

    # ── Public API ────────────────────────────────────────────────────────────

    def export(self, profiles: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        Write profiles to CSV.
        Returns stats: {total, new, skipped, duplicates}
        """
        if not profiles:
            logger.warning("No profiles to export")
            return {"total": 0, "new": 0, "skipped": 0, "duplicates": 0}

        self._backup_if_exists()

        new_rows = []
        duplicates = 0
        skipped = 0

        for profile in profiles:
            username = profile.get("username", "")
            if not username:
                skipped += 1
                continue
            if username in self._existing_usernames:
                duplicates += 1
                logger.debug(f"Duplicate skipped: @{username}")
                continue

            row = self._build_row(profile)
            new_rows.append(row)
            self._existing_usernames.add(username)

        self._write_rows(new_rows)

        stats = {
            "total": len(profiles),
            "new": len(new_rows),
            "skipped": skipped,
            "duplicates": duplicates,
        }

        logger.info(
            f"CSV Export → {self.filepath} | "
            f"New: {stats['new']} | Duplicates skipped: {stats['duplicates']}"
        )
        return stats

    def get_all_records(self) -> List[Dict]:
        """Read and return all records currently in the CSV."""
        if not Path(self.filepath).exists():
            return []
        with open(self.filepath, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def total_records(self) -> int:
        return len(self._existing_usernames)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _load_existing_usernames(self):
        """Load usernames already in CSV to prevent duplicates."""
        if not Path(self.filepath).exists():
            return
        try:
            with open(self.filepath, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    username = row.get("username", "").strip()
                    if username:
                        self._existing_usernames.add(username)
            logger.info(f"Loaded {len(self._existing_usernames)} existing records from CSV")
        except Exception as e:
            logger.warning(f"Could not read existing CSV: {e}")

    def _write_rows(self, rows: List[Dict]):
        """Append rows to CSV. Creates with header if file doesn't exist."""
        if not rows:
            return

        file_exists = Path(self.filepath).exists()
        mode = "a" if file_exists else "w"

        try:
            with open(self.filepath, mode, newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
                if not file_exists:
                    writer.writeheader()
                    logger.debug(f"Created new CSV: {self.filepath}")
                writer.writerows(rows)
        except Exception as e:
            logger.error(f"CSV write failed: {e}", exc_info=True)
            raise

    def _build_row(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize a profile dict into a CSV row."""
        return {
            "username":         profile.get("username", ""),
            "full_name":        profile.get("full_name", ""),
            "followers":        profile.get("followers", 0),
            "email":            profile.get("email", ""),
            "bio":              profile.get("bio", ""),
            "profile_category": profile.get("category", "Other"),
            "hashtag":          profile.get("hashtags_used", ""),
            "profile_url":      profile.get("profile_url", ""),
        }

    def _backup_if_exists(self):
        """Create a timestamped backup of the CSV before the first write of this session."""
        if self._backed_up_this_session:
            return
        if not Path(self.filepath).exists():
            return
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = self.filepath.replace(".csv", f"_backup_{timestamp}.csv")
            shutil.copy2(self.filepath, backup_path)
            logger.debug(f"Backup created: {backup_path}")
            self._backed_up_this_session = True
        except Exception as e:
            logger.warning(f"Backup failed: {e}")
