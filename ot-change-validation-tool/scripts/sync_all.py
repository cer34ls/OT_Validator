#!/usr/bin/env python3
"""
Master sync script - runs all data source syncs.
"""

import sys
from pathlib import Path
import logging
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from database.db import Database
from config.settings import DATABASE_PATH, WSUS_IMPORT_PATH, SERVICENOW_CONFIG

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def sync_wsus():
    """Sync WSUS approved patches."""
    logger.info("Starting WSUS sync...")

    try:
        from connectors.wsus_importer import WSUSImporter, WSUSSyncer

        db = Database(DATABASE_PATH)
        importer = WSUSImporter(WSUS_IMPORT_PATH)
        syncer = WSUSSyncer(importer, db)
        count = syncer.sync()
        logger.info(f"WSUS sync complete: {count} patches")
        return count
    except FileNotFoundError as e:
        logger.warning(f"WSUS sync: {e}")
        return 0
    except Exception as e:
        logger.error(f"WSUS sync failed: {e}")
        return 0


def sync_servicenow(hours_ago: int = 24):
    """Sync recent ServiceNow changes."""
    logger.info("Starting ServiceNow sync...")

    try:
        from connectors.servicenow_pseg import PSEGServiceNowConnector

        if not SERVICENOW_CONFIG['username']:
            logger.warning("ServiceNow not configured, skipping")
            return 0

        db = Database(DATABASE_PATH)
        connector = PSEGServiceNowConnector(**SERVICENOW_CONFIG)

        changes = connector.fetch_recent_ot_changes(hours_ago=hours_ago)

        count = 0
        for change in changes:
            db.upsert_change(change)
            count += 1

        db.update_sync_status('servicenow', count, 'success')
        logger.info(f"ServiceNow sync complete: {count} changes")
        return count

    except ValueError as e:
        logger.warning(f"ServiceNow not configured: {e}")
        return 0
    except Exception as e:
        logger.error(f"ServiceNow sync failed: {e}")
        return 0


def sync_mantis():
    """Sync Mantis issues."""
    logger.info("Starting Mantis sync...")

    try:
        from connectors.mantis import MantisConnector, MantisSyncer

        connector = MantisConnector()
        if not connector.is_configured():
            logger.info("Mantis not configured, skipping")
            return 0

        db = Database(DATABASE_PATH)
        syncer = MantisSyncer(connector, db)
        count = syncer.sync()
        logger.info(f"Mantis sync complete: {count} issues")
        return count

    except Exception as e:
        logger.error(f"Mantis sync failed: {e}")
        return 0


def process_emails():
    """Process ID alert emails."""
    logger.info("Processing ID alert emails...")

    try:
        from connectors.id_listener import IDEmailListener, IDAlertProcessor
        from engine.correlator import CorrelationEngine

        db = Database(DATABASE_PATH)
        correlator = CorrelationEngine(db)
        processor = IDAlertProcessor(db, correlator)

        try:
            processor.setup_email_listener()
            results = processor.process_all_sources()
            logger.info(f"Email processing complete: {results['email']} emails")
            return results['email']
        except ValueError:
            logger.info("Email listener not configured, skipping")
            return 0

    except Exception as e:
        logger.error(f"Email processing failed: {e}")
        return 0


def main():
    """Run all syncs."""
    logger.info(f"=== Starting sync at {datetime.now()} ===")

    # Initialize database if needed
    db = Database(DATABASE_PATH)
    db.init()

    results = {
        'wsus': sync_wsus(),
        'servicenow': sync_servicenow(),
        'mantis': sync_mantis(),
        'email': process_emails(),
    }

    total = sum(results.values())
    logger.info(f"=== Sync complete: {total} total records ===")
    logger.info(f"Results: {results}")

    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Sync all data sources')
    parser.add_argument('--hours', type=int, default=24,
                        help='Hours of history to sync from ServiceNow')
    parser.add_argument('--source', choices=['all', 'wsus', 'servicenow', 'mantis', 'email'],
                        default='all', help='Specific source to sync')

    args = parser.parse_args()

    if args.source == 'all':
        main()
    elif args.source == 'wsus':
        sync_wsus()
    elif args.source == 'servicenow':
        sync_servicenow(args.hours)
    elif args.source == 'mantis':
        sync_mantis()
    elif args.source == 'email':
        process_emails()
