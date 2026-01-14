"""
Industrial Defender Bulk Exceptions Parser
Based on actual ID ASM Bulk Exceptions UI from PSEG Long Island.

Parses CSV exports from the ID Bulk Exceptions page across all tabs:
- Asset Details
- Software Installed
- Patches Installed
- Ports And Services
- Firewall Rules
- User Accounts
- Device Interfaces
"""

import csv
import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from enum import Enum
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ExceptionType(Enum):
    """Types of ID exceptions based on Bulk Exceptions tabs."""
    ASSET_DETAILS = "asset_details"
    SOFTWARE_INSTALLED = "software_installed"
    PATCHES_INSTALLED = "patches_installed"
    PORTS_AND_SERVICES = "ports_and_services"
    FIREWALL_RULES = "firewall_rules"
    USER_ACCOUNTS = "user_accounts"
    DEVICE_INTERFACES = "device_interfaces"


class ChangeAction(Enum):
    """Change action types from ID Type column."""
    NEW = "new"
    REMOVED = "removed"
    CHANGED = "changed"


@dataclass
class IDException:
    """Represents a single ID baseline exception."""
    exception_type: ExceptionType
    change_action: ChangeAction
    asset_group: str
    asset_count: int
    comment: str
    detected_at: datetime
    extracted_chg_numbers: List[str]
    
    # Type-specific fields
    details: Dict[str, Any]
    
    # Raw data
    raw_row: Dict[str, str]


class IDExceptionParser:
    """
    Parser for Industrial Defender Bulk Exceptions CSV exports.
    """
    
    # Common column mappings (appear in all tabs)
    COMMON_COLUMNS = {
        'Type': 'change_action',
        'Asset Groups': 'asset_group',
        'Assets': 'asset_count',
        'Comment': 'comment',
        'Exception Detection Date': 'detected_at',
    }
    
    # Tab-specific column mappings
    TAB_COLUMNS = {
        ExceptionType.ASSET_DETAILS: {
            'Attribute Name': 'attribute_name',
            'Attribute Value': 'attribute_value',
        },
        ExceptionType.SOFTWARE_INSTALLED: {
            'Software Name': 'software_name',
            'Software Version': 'software_version',
        },
        ExceptionType.PATCHES_INSTALLED: {
            'Patch ID': 'patch_id',
            'Service Pack In Effect': 'service_pack',
        },
        ExceptionType.PORTS_AND_SERVICES: {
            'Port': 'port',
            'Protocol': 'protocol',
            'IP Version': 'ip_version',
            'Interface': 'interface',
            'Process': 'process_name',
        },
        ExceptionType.FIREWALL_RULES: {
            'Policy ID': 'policy_id',
            'Source IF': 'source_if',
            'Destination IF': 'dest_if',
            'Action': 'action',
            'Status': 'status',
            'S...': 'source_config',  # Truncated columns
            'D...': 'dest_config',
            'A...': 'actual_config',
        },
        ExceptionType.USER_ACCOUNTS: {
            'User ID': 'user_id',
            'User Type': 'user_type',
            'Domain': 'domain',
            'Member of': 'member_of',
            'Enabled': 'enabled',
        },
        ExceptionType.DEVICE_INTERFACES: {
            'Interface Name': 'interface_name',
            'IP Address': 'ip_address',
            'Subnet Mask': 'subnet_mask',
            'MAC Address': 'mac_address',
        },
    }
    
    def __init__(self):
        self.chg_pattern = re.compile(r'CHG\d{10}', re.IGNORECASE)
        self.kb_pattern = re.compile(r'KB\d{6,7}', re.IGNORECASE)
    
    def detect_exception_type(self, headers: List[str]) -> ExceptionType:
        """Detect the exception type based on CSV column headers."""
        headers_lower = [h.lower() for h in headers]
        
        if 'patch id' in headers_lower:
            return ExceptionType.PATCHES_INSTALLED
        elif 'software name' in headers_lower:
            return ExceptionType.SOFTWARE_INSTALLED
        elif 'port' in headers_lower and 'protocol' in headers_lower:
            return ExceptionType.PORTS_AND_SERVICES
        elif 'policy id' in headers_lower:
            return ExceptionType.FIREWALL_RULES
        elif 'user id' in headers_lower and 'user type' in headers_lower:
            return ExceptionType.USER_ACCOUNTS
        elif 'interface name' in headers_lower and 'mac address' in headers_lower:
            return ExceptionType.DEVICE_INTERFACES
        elif 'attribute name' in headers_lower:
            return ExceptionType.ASSET_DETAILS
        else:
            # Default to asset details
            return ExceptionType.ASSET_DETAILS
    
    def parse_csv(self, csv_path: str) -> List[IDException]:
        """
        Parse an ID Bulk Exceptions CSV export.
        
        Args:
            csv_path: Path to CSV file
            
        Returns:
            List of parsed IDException objects
        """
        exceptions = []
        path = Path(csv_path)
        
        if not path.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_path}")
        
        with open(path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames or []
            
            exception_type = self.detect_exception_type(headers)
            logger.info(f"Detected exception type: {exception_type.value}")
            
            for row in reader:
                try:
                    exception = self._parse_row(row, exception_type)
                    if exception:
                        exceptions.append(exception)
                except Exception as e:
                    logger.warning(f"Error parsing row: {e}")
                    continue
        
        logger.info(f"Parsed {len(exceptions)} exceptions from {path.name}")
        return exceptions
    
    def _parse_row(self, row: Dict[str, str], exception_type: ExceptionType) -> Optional[IDException]:
        """Parse a single CSV row into an IDException."""
        
        # Parse common fields
        change_action = self._parse_change_action(row.get('Type', ''))
        asset_group = row.get('Asset Groups', '')
        asset_count = self._parse_int(row.get('Assets', '1'))
        comment = row.get('Comment', '')
        detected_at = self._parse_datetime(row.get('Exception Detection Date', ''))
        
        if not detected_at:
            logger.warning("Missing detection date, skipping row")
            return None
        
        # Extract CHG numbers from comment (CRITICAL for correlation)
        chg_numbers = self.chg_pattern.findall(comment)
        chg_numbers = [c.upper() for c in chg_numbers]
        
        # Parse type-specific fields
        details = self._parse_type_specific_fields(row, exception_type)
        
        return IDException(
            exception_type=exception_type,
            change_action=change_action,
            asset_group=asset_group,
            asset_count=asset_count,
            comment=comment,
            detected_at=detected_at,
            extracted_chg_numbers=list(set(chg_numbers)),  # Dedupe
            details=details,
            raw_row=row
        )
    
    def _parse_type_specific_fields(self, row: Dict[str, str], 
                                    exception_type: ExceptionType) -> Dict[str, Any]:
        """Parse fields specific to the exception type."""
        details = {}
        column_map = self.TAB_COLUMNS.get(exception_type, {})
        
        for csv_col, field_name in column_map.items():
            value = row.get(csv_col, '')
            
            # Type conversions
            if field_name in ('port', 'ip_version', 'asset_count'):
                details[field_name] = self._parse_int(value)
            elif field_name == 'enabled':
                details[field_name] = value.lower() == 'true'
            else:
                details[field_name] = value
        
        # Extract KB numbers from patch_id if present
        if exception_type == ExceptionType.PATCHES_INSTALLED:
            patch_id = details.get('patch_id', '')
            kb_matches = self.kb_pattern.findall(patch_id)
            details['kb_numbers'] = [kb.upper() for kb in kb_matches]
        
        return details
    
    def _parse_change_action(self, value: str) -> ChangeAction:
        """Parse the Type column to ChangeAction enum."""
        value_lower = value.lower().strip()
        
        if 'new' in value_lower:
            return ChangeAction.NEW
        elif 'removed' in value_lower:
            return ChangeAction.REMOVED
        elif 'changed' in value_lower:
            return ChangeAction.CHANGED
        else:
            return ChangeAction.NEW  # Default
    
    def _parse_datetime(self, value: str) -> Optional[datetime]:
        """Parse ID datetime format."""
        if not value:
            return None
        
        # ID format from screenshots: 8/29/2025 11:47:47 AM
        formats = [
            '%m/%d/%Y %I:%M:%S %p',   # 8/29/2025 11:47:47 AM
            '%m/%d/%Y %H:%M:%S',      # 8/29/2025 11:47:47
            '%m/%d/%Y %I:%M %p',      # 8/29/2025 11:47 AM
            '%Y-%m-%d %H:%M:%S',      # 2025-08-29 11:47:47
            '%Y-%m-%dT%H:%M:%S',      # ISO format
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(value.strip(), fmt)
            except ValueError:
                continue
        
        logger.warning(f"Could not parse datetime: {value}")
        return None
    
    def _parse_int(self, value: str) -> int:
        """Safely parse integer value."""
        try:
            return int(value.strip())
        except (ValueError, AttributeError):
            return 0
    
    def to_database_records(self, exceptions: List[IDException]) -> List[Dict]:
        """
        Convert IDException objects to database insert format.
        """
        records = []
        
        for exc in exceptions:
            record = {
                'exception_type': exc.exception_type.value,
                'change_action': exc.change_action.value,
                'asset_group': exc.asset_group,
                'asset_count': exc.asset_count,
                'comment': exc.comment,
                'detected_at': exc.detected_at.isoformat() if exc.detected_at else None,
                'extracted_chg_numbers': exc.extracted_chg_numbers,
                'validation_status': 'pending',
            }
            
            # Merge type-specific details
            record.update(exc.details)
            
            records.append(record)
        
        return records


class IDExceptionCorrelator:
    """
    Correlates ID exceptions with ServiceNow changes.
    Uses the CHG numbers embedded in ID comments for direct lookup.
    """
    
    def __init__(self, servicenow_connector, database):
        self.snow = servicenow_connector
        self.db = database
    
    def correlate_exception(self, exception: IDException) -> Dict[str, Any]:
        """
        Attempt to correlate an ID exception with approved changes.
        
        PRIMARY PATH: Use CHG numbers from comment for direct lookup
        SECONDARY PATH: Match by asset name + time window
        TERTIARY PATH: Match KB numbers against WSUS approved list
        """
        result = {
            'exception_type': exception.exception_type.value,
            'correlation_method': None,
            'matched_changes': [],
            'is_validated': False,
            'confidence': 0.0,
        }
        
        # PRIMARY: Direct CHG lookup from comment
        if exception.extracted_chg_numbers:
            changes = self.snow.lookup_multiple_chg(exception.extracted_chg_numbers)
            
            approved_changes = [
                c for c in changes 
                if c.get('approval_status') == 'approved'
            ]
            
            if approved_changes:
                result['correlation_method'] = 'direct_chg_lookup'
                result['matched_changes'] = approved_changes
                result['is_validated'] = True
                result['confidence'] = 1.0  # 100% confidence
                
                logger.info(
                    f"Direct correlation: {len(approved_changes)} approved CHG tickets "
                    f"for {exception.exception_type.value}"
                )
                return result
        
        # SECONDARY: Asset + Time window correlation
        # (Would need asset name from context - implement based on asset tracking)
        
        # TERTIARY: KB article match for patches
        if exception.exception_type == ExceptionType.PATCHES_INSTALLED:
            kb_numbers = exception.details.get('kb_numbers', [])
            
            for kb in kb_numbers:
                if self.db.is_kb_approved(kb):
                    result['correlation_method'] = 'wsus_approved_patch'
                    result['is_validated'] = True
                    result['confidence'] = 1.0
                    result['matched_kb'] = kb
                    
                    logger.info(f"WSUS correlation: {kb} is approved")
                    return result
        
        # No correlation found
        result['correlation_method'] = 'none'
        result['is_validated'] = False
        result['confidence'] = 0.0
        
        logger.warning(
            f"No correlation found for {exception.exception_type.value} "
            f"detected at {exception.detected_at}"
        )
        
        return result


if __name__ == '__main__':
    # Test parsing
    parser = IDExceptionParser()
    
    # Test CHG extraction from comment
    test_comment = "Activity from DSCADA Monthly Patching: CHG0000338290 CHG0000338289 CHG0000338288 CHG0000338287"
    chg_pattern = re.compile(r'CHG\d{10}', re.IGNORECASE)
    chg_numbers = chg_pattern.findall(test_comment)
    print(f"Extracted CHG numbers from comment: {chg_numbers}")
    
    # Test KB extraction from patch ID
    test_patch = "KB5062070"
    kb_pattern = re.compile(r'KB\d{6,7}', re.IGNORECASE)
    kb_numbers = kb_pattern.findall(test_patch)
    print(f"Extracted KB numbers from patch ID: {kb_numbers}")
    
    print("\nParser initialized. Ready to parse ID Bulk Exceptions CSV exports.")
    print("Supported exception types:")
    for et in ExceptionType:
        print(f"  - {et.value}")
