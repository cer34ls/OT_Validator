"""Tests for correlation engine."""

import pytest
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from connectors.servicenow_pseg import extract_chg_numbers_from_comment
from connectors.id_parser import IDExceptionParser, ExceptionType
from database.db import Database
from engine.correlator import CorrelationEngine


class TestCHGExtraction:
    """Test CHG number extraction from ID comments."""

    def test_extract_multiple_chg(self):
        comment = "Activity from DSCADA Monthly Patching: CHG0000338290 CHG0000338289 CHG0000338288 CHG0000338287"

        result = extract_chg_numbers_from_comment(comment)

        assert len(result) == 4
        assert 'CHG0000338290' in result
        assert 'CHG0000338289' in result
        assert 'CHG0000338288' in result
        assert 'CHG0000338287' in result

    def test_extract_single_chg(self):
        comment = "Related to CHG0000123456"

        result = extract_chg_numbers_from_comment(comment)

        assert len(result) == 1
        assert 'CHG0000123456' in result

    def test_extract_no_chg(self):
        comment = "Just a regular comment with no ticket numbers"

        result = extract_chg_numbers_from_comment(comment)

        assert len(result) == 0

    def test_extract_empty_comment(self):
        result = extract_chg_numbers_from_comment("")
        assert len(result) == 0

        result = extract_chg_numbers_from_comment(None)
        assert len(result) == 0

    def test_extract_lowercase_chg(self):
        comment = "See chg0000338290 for details"

        result = extract_chg_numbers_from_comment(comment)

        assert len(result) == 1
        assert 'CHG0000338290' in result

    def test_extract_duplicates_removed(self):
        comment = "CHG0000338290 and CHG0000338290 again"

        result = extract_chg_numbers_from_comment(comment)

        assert len(result) == 1


class TestIDParser:
    """Test ID exception parser."""

    def test_detect_patches_type(self):
        parser = IDExceptionParser()

        headers = ['Type', 'Patch ID', 'Service Pack In Effect', 'Asset Groups', 'Assets', 'Comment', 'Exception Detection Date']

        result = parser.detect_exception_type(headers)

        assert result == ExceptionType.PATCHES_INSTALLED

    def test_detect_software_type(self):
        parser = IDExceptionParser()

        headers = ['Type', 'Software Name', 'Software Version', 'Asset Groups', 'Assets', 'Comment', 'Exception Detection Date']

        result = parser.detect_exception_type(headers)

        assert result == ExceptionType.SOFTWARE_INSTALLED

    def test_detect_ports_type(self):
        parser = IDExceptionParser()

        headers = ['Type', 'Port', 'Protocol', 'IP Version', 'Interface', 'Process', 'Asset Groups', 'Assets', 'Comment']

        result = parser.detect_exception_type(headers)

        assert result == ExceptionType.PORTS_AND_SERVICES

    def test_detect_user_accounts_type(self):
        parser = IDExceptionParser()

        headers = ['Type', 'User ID', 'User Type', 'Domain', 'Member of', 'Enabled', 'Asset Groups']

        result = parser.detect_exception_type(headers)

        assert result == ExceptionType.USER_ACCOUNTS

    def test_parse_csv(self):
        parser = IDExceptionParser()

        # Create temp CSV
        csv_content = """Type,Patch ID,Service Pack In Effect,Asset Groups,Assets,Comment,Exception Detection Date
Removed,KB5062070,,All_Windows,5,Activity from DSCADA Monthly Patching: CHG0000338290,12/24/2025 2:00:19 AM
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(csv_content)
            temp_path = f.name

        exceptions = parser.parse_csv(temp_path)

        assert len(exceptions) == 1
        exc = exceptions[0]
        assert exc.exception_type == ExceptionType.PATCHES_INSTALLED
        assert exc.asset_group == 'All_Windows'
        assert 'CHG0000338290' in exc.extracted_chg_numbers

        # Cleanup
        Path(temp_path).unlink()


class TestDatabase:
    """Test database operations."""

    @pytest.fixture
    def db(self):
        """Create temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name

        db = Database(db_path)
        db.init()
        yield db

        # Cleanup
        Path(db_path).unlink()

    def test_upsert_change(self, db):
        change = {
            'source': 'servicenow',
            'ticket_id': 'CHG0000338771',
            'asset_name': 'pccqasasm1',
            'asset_name_normalized': 'qasasm1',
            'description': 'Test change',
            'scheduled_start': '2026-01-13T14:00:00',
            'scheduled_end': '2026-01-14T14:00:00',
            'approval_status': 'approved',
        }

        row_id = db.upsert_change(change)
        assert row_id > 0

        # Verify we can search for it
        results = db.search_changes('CHG0000338771')
        assert len(results) == 1
        assert results[0]['ticket_id'] == 'CHG0000338771'

    def test_wsus_patch_approval(self, db):
        patch = {
            'kb_number': 'KB5062070',
            'title': 'Security Update',
            'classification': 'Security',
            'approval_date': '2025-01-13T10:00:00',
            'approved_for_groups': ['OT Servers'],
        }

        db.upsert_wsus_patch(patch)

        # Check approval
        assert db.is_kb_approved('KB5062070') == True
        assert db.is_kb_approved('KB9999999') == False

    def test_insert_alert(self, db):
        alert = {
            'alert_id': 'TEST-001',
            'asset_name': 'server01',
            'asset_name_normalized': 'server01',
            'change_category': 'patches_installed',
            'change_detail': 'KB5062070 installed',
            'detected_at': '2025-12-24T02:00:00',
            'severity': 3,
            'source_type': 'csv_import',
        }

        alert_id = db.insert_alert(alert)
        assert alert_id > 0

        # Check pending
        pending = db.get_pending_alerts()
        assert len(pending) >= 1

    def test_metrics(self, db):
        metrics = db.get_metrics()

        assert 'pending_count' in metrics
        assert 'validated_today' in metrics
        assert 'auto_validation_rate' in metrics
        assert 'unauthorized_count' in metrics


class TestCorrelationEngine:
    """Test correlation engine."""

    @pytest.fixture
    def db(self):
        """Create temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name

        db = Database(db_path)
        db.init()
        yield db

        Path(db_path).unlink()

    def test_wsus_auto_validator(self, db):
        from engine.correlator import WSUSAutoValidator

        # Add approved patch
        db.upsert_wsus_patch({
            'kb_number': 'KB5062070',
            'title': 'Security Update',
            'classification': 'Security',
        })

        validator = WSUSAutoValidator(db)

        # Test with matching KB
        alert = {'change_detail': 'KB5062070 installed'}
        result = validator.check_wsus_approval(alert)

        assert result is not None
        assert result['auto_validated'] == True
        assert result['kb_number'] == 'KB5062070'

        # Test with non-matching KB
        alert = {'change_detail': 'KB9999999 installed'}
        result = validator.check_wsus_approval(alert)

        assert result is None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
