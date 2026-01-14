#!/usr/bin/env python3
"""
Initialize the database with schema and seed data.
"""

import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.db import Database
from config.settings import DATABASE_PATH


def main():
    """Initialize the database."""
    print(f"Initializing database at: {DATABASE_PATH}")

    db = Database(DATABASE_PATH)
    db.init()

    print("Database initialized successfully!")
    print("\nTables created:")
    print("  - changes (ServiceNow/Mantis tickets)")
    print("  - alerts (ID exceptions)")
    print("  - validations (correlation results)")
    print("  - wsus_patches (approved KB articles)")
    print("  - assets (asset name mappings)")
    print("  - sync_status (data source status)")
    print("  - audit_log (compliance trail)")
    print("  - changes_fts (full-text search)")

    # Initialize sync status for data sources
    sources = ['servicenow', 'wsus', 'email', 'syslog', 'csv_import']
    for source in sources:
        db.update_sync_status(source, 0, 'not_configured')

    print(f"\nInitialized sync status for: {', '.join(sources)}")
    print("\nDatabase ready! Run the dashboard with: streamlit run app/dashboard.py")


if __name__ == "__main__":
    main()
