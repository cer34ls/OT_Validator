"""
Validation Processor
Orchestrates the full validation workflow.
"""

from typing import Dict, List, Optional
from datetime import datetime
import logging
import re

from .correlator import CorrelationEngine, CorrelationResult

logger = logging.getLogger(__name__)


class ValidationProcessor:
    """Processes ID exceptions and creates validation records."""

    def __init__(self, database, snow_connector=None, wsus_importer=None):
        self.db = database
        self.correlator = CorrelationEngine(database)
        self.snow = snow_connector

        if snow_connector:
            self.correlator.snow_connector = snow_connector

    def process_exception(self, exception: Dict) -> Dict:
        """
        Process a single ID exception through the validation pipeline.

        Returns validation result with correlation details.
        """
        result = {
            'exception_type': exception.get('exception_type', 'unknown'),
            'detected_at': exception.get('detected_at'),
            'asset_group': exception.get('asset_group', ''),
            'correlation_method': None,
            'is_validated': False,
            'confidence': 0.0,
            'matched_tickets': [],
            'notes': [],
        }

        # Extract CHG numbers from comment
        comment = exception.get('comment', '')
        chg_numbers = self._extract_chg_numbers(comment)

        # Step 1: Try direct CHG lookup (PRIMARY PATH)
        if chg_numbers:
            logger.info(f"Found CHG numbers in comment: {chg_numbers}")
            result['notes'].append(f"CHG numbers found: {chg_numbers}")

            if self.snow:
                correlation = self._correlate_with_direct_lookup(chg_numbers)

                if correlation and correlation.get('is_validated'):
                    result['correlation_method'] = 'direct_chg_lookup'
                    result['is_validated'] = True
                    result['confidence'] = 1.0
                    result['matched_tickets'] = chg_numbers
                    result['notes'].append("Auto-validated via direct CHG lookup")

                    return result

        # Step 2: Try WSUS KB match (for patches)
        if exception.get('exception_type') == 'patches_installed':
            kb_numbers = exception.get('kb_numbers', [])
            patch_id = exception.get('patch_id', '')

            # Also extract KB from patch_id field
            if patch_id:
                kb_match = re.search(r'KB\d{6,7}', patch_id, re.IGNORECASE)
                if kb_match:
                    kb_numbers.append(kb_match.group().upper())

            for kb in kb_numbers:
                if self.db.is_kb_approved(kb):
                    result['correlation_method'] = 'wsus_approved'
                    result['is_validated'] = True
                    result['confidence'] = 1.0
                    result['matched_tickets'] = [kb]
                    result['notes'].append(f"Auto-validated: {kb} in WSUS approved list")

                    return result

        # Step 3: Try asset + time window correlation (SECONDARY PATH)
        # This requires additional context about which asset the exception is for

        # Step 4: No correlation found - flag for manual review
        result['correlation_method'] = 'none'
        result['is_validated'] = False
        result['confidence'] = 0.0
        result['notes'].append("No matching change ticket found - manual review required")

        return result

    def process_batch(self, exceptions: List[Dict]) -> Dict:
        """Process a batch of exceptions and return summary."""
        summary = {
            'total': len(exceptions),
            'auto_validated': 0,
            'pending_review': 0,
            'by_type': {},
            'results': [],
        }

        for exc in exceptions:
            result = self.process_exception(exc)
            summary['results'].append(result)

            if result['is_validated']:
                summary['auto_validated'] += 1
            else:
                summary['pending_review'] += 1

            exc_type = exc.get('exception_type', 'unknown')
            if exc_type not in summary['by_type']:
                summary['by_type'][exc_type] = {'validated': 0, 'pending': 0}

            if result['is_validated']:
                summary['by_type'][exc_type]['validated'] += 1
            else:
                summary['by_type'][exc_type]['pending'] += 1

        logger.info(
            f"Processed {summary['total']} exceptions: "
            f"{summary['auto_validated']} validated, "
            f"{summary['pending_review']} pending review"
        )

        return summary

    def _extract_chg_numbers(self, comment: str) -> List[str]:
        """Extract CHG ticket numbers from comment."""
        if not comment:
            return []

        pattern = r'CHG\d{10}'
        matches = re.findall(pattern, comment, re.IGNORECASE)
        return [m.upper() for m in set(matches)]

    def _correlate_with_direct_lookup(self, chg_numbers: List[str]) -> Optional[Dict]:
        """
        PRIMARY CORRELATION PATH
        Uses CHG numbers from ID comment field for direct ServiceNow lookup.
        """
        if not self.snow or not chg_numbers:
            return None

        try:
            changes = self.snow.lookup_multiple_chg(chg_numbers)

            # Filter to approved and closed successful
            approved_changes = [
                c for c in changes
                if c.get('approval_status') == 'approved'
                and 'closed' in c.get('state', '').lower()
            ]

            if approved_changes:
                return {
                    'is_validated': True,
                    'confidence': 1.0,
                    'matched_changes': approved_changes,
                    'rule': 'direct_chg_lookup'
                }

        except Exception as e:
            logger.error(f"Error during CHG lookup: {e}")

        return None


class BatchProcessor:
    """Processes batches of ID exceptions from various sources."""

    def __init__(self, database, snow_connector=None):
        self.db = database
        self.validator = ValidationProcessor(database, snow_connector)

    def process_csv_import(self, exceptions: List[Dict]) -> Dict:
        """
        Process exceptions imported from CSV.

        Args:
            exceptions: List of parsed exception dictionaries

        Returns:
            Processing summary
        """
        summary = self.validator.process_batch(exceptions)

        # Store results in database
        for i, exc in enumerate(exceptions):
            result = summary['results'][i]

            # Insert alert
            alert_data = {
                'alert_id': f"CSV-{datetime.now().strftime('%Y%m%d%H%M%S')}-{i}",
                'asset_name': exc.get('asset_group', 'Unknown'),
                'asset_name_normalized': exc.get('asset_group', '').lower(),
                'change_category': exc.get('exception_type', ''),
                'change_detail': exc.get('comment', ''),
                'detected_at': exc.get('detected_at', datetime.now().isoformat()),
                'severity': 3,
                'source_type': 'csv_import',
                'raw_email': str(exc)
            }

            alert_id = self.db.insert_alert(alert_data)

            # Create validation record
            validation = {
                'alert_id': alert_id,
                'change_id': None,
                'correlation_score': result['confidence'],
                'correlation_factors': {'method': result['correlation_method']},
                'validation_status': 'auto_validated' if result['is_validated'] else 'pending_review',
                'validated_by': 'SYSTEM' if result['is_validated'] else None,
                'validated_at': datetime.now().isoformat() if result['is_validated'] else None,
                'notes': '; '.join(result['notes']),
                'auto_validation_rule': result['correlation_method']
            }

            self.db.create_validation(validation)

            # Update alert status
            if result['is_validated']:
                self.db.update_alert_status(alert_id, 'validated', 'SYSTEM')

        # Update sync status
        self.db.update_sync_status('csv_import', summary['total'], 'success')

        return summary


if __name__ == '__main__':
    # Test the validator
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent.parent))

    from database.db import Database
    from config.settings import DATABASE_PATH

    db = Database(DATABASE_PATH)

    # Test with sample exception
    test_exception = {
        'exception_type': 'patches_installed',
        'change_action': 'removed',
        'asset_group': 'All_Windows, Domain Controllers',
        'comment': 'Activity from DSCADA Monthly Patching: CHG0000338290 CHG0000338289',
        'detected_at': '2025-12-24T02:00:19',
        'patch_id': 'KB5062070',
    }

    processor = ValidationProcessor(db)
    result = processor.process_exception(test_exception)

    print("Validation Result:")
    print(f"  Method: {result['correlation_method']}")
    print(f"  Validated: {result['is_validated']}")
    print(f"  Confidence: {result['confidence']}")
    print(f"  Notes: {result['notes']}")
