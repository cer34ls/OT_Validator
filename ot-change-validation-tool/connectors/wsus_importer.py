"""
WSUS Approved Patches Importer
Imports CSV exports from WSUS PowerShell script.
"""

import csv
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class WSUSImporter:
    """Imports WSUS approved patches from CSV exports."""

    def __init__(self, import_path: str):
        self.import_path = Path(import_path)

    def find_latest_export(self) -> Path:
        """Find the most recent WSUS export file."""
        if not self.import_path.exists():
            self.import_path.mkdir(parents=True, exist_ok=True)
            raise FileNotFoundError(f"No CSV files found in {self.import_path}")

        csv_files = list(self.import_path.glob("*.csv"))

        if not csv_files:
            raise FileNotFoundError(f"No CSV files found in {self.import_path}")

        # Sort by modification time, newest first
        csv_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return csv_files[0]

    def import_patches(self, csv_path: str = None) -> List[Dict]:
        """
        Import approved patches from WSUS CSV export.

        Expected columns (from PowerShell export):
        - KBNumber: KB5062070
        - Title: Security Update for Windows...
        - Classification: Security, Critical, etc.
        - ApprovalDate: 2025-01-13 10:00:00
        - TargetGroups: OT Servers;SCADA;All_Windows
        """
        if csv_path:
            path = Path(csv_path)
        else:
            path = self.find_latest_export()

        logger.info(f"Importing WSUS patches from: {path}")

        patches = []

        with open(path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)

            for row in reader:
                patch = {
                    'kb_number': self._normalize_kb(row.get('KBNumber', '')),
                    'title': row.get('Title', ''),
                    'classification': row.get('Classification', ''),
                    'approval_date': self._parse_date(row.get('ApprovalDate', '')),
                    'approved_for_groups': self._parse_groups(row.get('TargetGroups', '')),
                }

                if patch['kb_number']:
                    patches.append(patch)

        logger.info(f"Imported {len(patches)} approved patches")
        return patches

    def _normalize_kb(self, value: str) -> str:
        """Normalize KB number format."""
        if not value:
            return ''

        value = value.strip().upper()

        # Ensure KB prefix
        if not value.startswith('KB'):
            value = f'KB{value}'

        return value

    def _parse_date(self, value: str) -> Optional[str]:
        """Parse date string to ISO format."""
        if not value:
            return None

        formats = [
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d',
            '%m/%d/%Y %H:%M:%S',
            '%m/%d/%Y',
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(value.strip(), fmt)
                return dt.isoformat()
            except ValueError:
                continue

        return value

    def _parse_groups(self, value: str) -> List[str]:
        """Parse semicolon-separated group list."""
        if not value:
            return []

        return [g.strip() for g in value.split(';') if g.strip()]


class WSUSSyncer:
    """Syncs WSUS patches to database."""

    def __init__(self, importer: WSUSImporter, database):
        self.importer = importer
        self.db = database

    def sync(self, csv_path: str = None) -> int:
        """Import WSUS patches and sync to database."""
        try:
            patches = self.importer.import_patches(csv_path)

            count = 0
            for patch in patches:
                self.db.upsert_wsus_patch(patch)
                count += 1

            self.db.update_sync_status('wsus', count, 'success')
            logger.info(f"Synced {count} WSUS patches")
            return count

        except FileNotFoundError as e:
            self.db.update_sync_status('wsus', 0, 'no_files', str(e))
            logger.warning(f"WSUS sync: {e}")
            return 0

        except Exception as e:
            self.db.update_sync_status('wsus', 0, 'failed', str(e))
            logger.error(f"WSUS sync failed: {e}")
            raise


if __name__ == '__main__':
    # Test importer
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent.parent))

    from config.settings import WSUS_IMPORT_PATH

    print(f"WSUS import path: {WSUS_IMPORT_PATH}")

    try:
        importer = WSUSImporter(WSUS_IMPORT_PATH)
        patches = importer.import_patches()
        print(f"Found {len(patches)} patches")
        for patch in patches[:5]:
            print(f"  - {patch['kb_number']}: {patch['title'][:50]}...")
    except FileNotFoundError as e:
        print(f"No WSUS exports found: {e}")
