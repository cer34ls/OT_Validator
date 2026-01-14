"""
ServiceNow REST API Connector - PSEG Long Island Configuration
Based on actual production CHG ticket field analysis.

Target Instance: psegincprod.service-now.com
"""

import requests
import re
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PSEGServiceNowConnector:
    """
    ServiceNow connector configured for PSEG Long Island environment.
    Pulls change requests from psegincprod.service-now.com
    """
    
    # PSEG-specific field mappings based on actual CHG ticket structure
    FIELDS_TO_RETRIEVE = [
        # Core identification
        'number',                    # CHG0000338771
        'sys_id',                    # Internal ID for linking
        
        # Status fields
        'state',                     # Closed Successful, Open, etc.
        'approval',                  # Approved, Rejected, Pending
        'stage',                     # Approved
        
        # Asset/CI information
        'cmdb_ci',                   # Configuration item (pccqasasm1)
        'cmdb_ci.name',              # CI display name
        
        # Classification
        'short_description',         # DSCADA QAS ID - Patch platform...
        'description',               # Full description with patch URLs
        'category',                  # Infrastructure SW
        'subcategory',               # Industrial Defender
        'u_activity',                # Enhancement (custom field)
        'u_environment',             # QA, Prod (custom field)
        
        # Schedule - CRITICAL for time correlation
        'start_date',                # Proposed Start: 01-13-2026 02:00 PM
        'end_date',                  # Proposed End: 01-14-2026 02:00 PM
        'work_start',                # Implementation Start
        'work_end',                  # Implementation End
        
        # People
        'opened_at',                 # 01-13-2026 10:29 AM
        'opened_by',                 # Ryan Collier
        'assigned_to',               # Ryan Collier
        'assignment_group',          # LI Cyber Security OT
        
        # Plans (for documentation)
        'implementation_plan',       # step 1 - contact support...
        'test_plan',                 # Within the ID web portal...
        'backout_plan',              # Rollback to a version...
        
        # Additional
        'u_nerc_cip_options',        # NERC CIP Options (custom)
        'sys_updated_on',            # Last update timestamp
    ]
    
    # Filter to OT-relevant changes
    OT_ASSIGNMENT_GROUPS = [
        'LI Cyber Security OT',
        'Cyber Security OT',
        'OT Security',
    ]
    
    OT_SUBCATEGORIES = [
        'Industrial Defender',
        'SCADA',
        'OT',
        'ICS',
    ]
    
    def __init__(self, instance_url: str = None, username: str = None, password: str = None):
        """Initialize connector with PSEG ServiceNow credentials."""
        self.base_url = (instance_url or os.getenv('SNOW_INSTANCE_URL', 
                         'https://psegincprod.service-now.com')).rstrip('/')
        self.username = username or os.getenv('SNOW_USERNAME')
        self.password = password or os.getenv('SNOW_PASSWORD')
        
        if not all([self.base_url, self.username, self.password]):
            raise ValueError("Missing ServiceNow credentials. Set SNOW_INSTANCE_URL, SNOW_USERNAME, SNOW_PASSWORD")
        
        self.session = requests.Session()
        self.session.auth = (self.username, self.password)
        self.session.headers.update({
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        })
    
    def lookup_chg_by_number(self, chg_number: str) -> Optional[Dict]:
        """
        Direct lookup of a specific CHG ticket by number.
        This is the PRIMARY correlation path when ID comment contains CHG numbers.
        
        Args:
            chg_number: CHG ticket number (e.g., "CHG0000338771")
            
        Returns:
            Change record dict or None if not found
        """
        endpoint = f'{self.base_url}/api/now/table/change_request'
        
        params = {
            'sysparm_query': f'number={chg_number}',
            'sysparm_fields': ','.join(self.FIELDS_TO_RETRIEVE),
            'sysparm_display_value': 'all',
            'sysparm_limit': 1
        }
        
        try:
            response = self.session.get(endpoint, params=params, timeout=30)
            response.raise_for_status()
            results = response.json().get('result', [])
            
            if results:
                logger.info(f"Found CHG ticket: {chg_number}")
                return self.normalize_change(results[0])
            else:
                logger.warning(f"CHG ticket not found: {chg_number}")
                return None
                
        except requests.RequestException as e:
            logger.error(f"Error looking up {chg_number}: {e}")
            return None
    
    def lookup_multiple_chg(self, chg_numbers: List[str]) -> List[Dict]:
        """
        Lookup multiple CHG tickets at once.
        
        Args:
            chg_numbers: List of CHG numbers
            
        Returns:
            List of found change records
        """
        if not chg_numbers:
            return []
        
        endpoint = f'{self.base_url}/api/now/table/change_request'
        
        # Build OR query for multiple numbers
        number_query = '^OR'.join([f'number={num}' for num in chg_numbers])
        
        params = {
            'sysparm_query': number_query,
            'sysparm_fields': ','.join(self.FIELDS_TO_RETRIEVE),
            'sysparm_display_value': 'all',
            'sysparm_limit': len(chg_numbers)
        }
        
        try:
            response = self.session.get(endpoint, params=params, timeout=30)
            response.raise_for_status()
            results = response.json().get('result', [])
            
            logger.info(f"Found {len(results)}/{len(chg_numbers)} CHG tickets")
            return [self.normalize_change(r) for r in results]
            
        except requests.RequestException as e:
            logger.error(f"Error looking up multiple CHGs: {e}")
            return []
    
    def fetch_recent_ot_changes(self, hours_ago: int = 24) -> List[Dict]:
        """
        Fetch recent changes assigned to OT security groups.
        
        Args:
            hours_ago: How far back to look
            
        Returns:
            List of normalized change records
        """
        endpoint = f'{self.base_url}/api/now/table/change_request'
        
        # Build query for OT-relevant changes
        query_parts = [
            f'sys_updated_on>javascript:gs.hoursAgoStart({hours_ago})',
        ]
        
        # Add assignment group filter
        group_filter = '^OR'.join([f'assignment_group.nameLIKE{g}' for g in self.OT_ASSIGNMENT_GROUPS])
        query_parts.append(f'({group_filter})')
        
        params = {
            'sysparm_query': '^'.join(query_parts),
            'sysparm_fields': ','.join(self.FIELDS_TO_RETRIEVE),
            'sysparm_display_value': 'all',
            'sysparm_limit': 200
        }
        
        try:
            response = self.session.get(endpoint, params=params, timeout=30)
            response.raise_for_status()
            results = response.json().get('result', [])
            
            logger.info(f"Fetched {len(results)} OT changes from last {hours_ago} hours")
            return [self.normalize_change(r) for r in results]
            
        except requests.RequestException as e:
            logger.error(f"Error fetching recent changes: {e}")
            return []
    
    def fetch_changes_in_window(self, start: datetime, end: datetime, 
                                asset_name: str = None) -> List[Dict]:
        """
        Fetch changes scheduled within a specific time window.
        Used for time-based correlation.
        
        Args:
            start: Window start time
            end: Window end time
            asset_name: Optional asset name filter
        """
        endpoint = f'{self.base_url}/api/now/table/change_request'
        
        # Format dates for ServiceNow
        start_str = start.strftime('%Y-%m-%d %H:%M:%S')
        end_str = end.strftime('%Y-%m-%d %H:%M:%S')
        
        query_parts = [
            f'start_date<={end_str}',
            f'end_date>={start_str}',
            'approval=approved',
        ]
        
        if asset_name:
            query_parts.append(f'cmdb_ci.nameLIKE{asset_name}')
        
        params = {
            'sysparm_query': '^'.join(query_parts),
            'sysparm_fields': ','.join(self.FIELDS_TO_RETRIEVE),
            'sysparm_display_value': 'all',
            'sysparm_limit': 100
        }
        
        try:
            response = self.session.get(endpoint, params=params, timeout=30)
            response.raise_for_status()
            results = response.json().get('result', [])
            
            return [self.normalize_change(r) for r in results]
            
        except requests.RequestException as e:
            logger.error(f"Error fetching changes in window: {e}")
            return []
    
    def normalize_change(self, raw: Dict) -> Dict:
        """
        Transform ServiceNow record to standard format.
        Maps PSEG-specific fields to database schema.
        """
        def get_value(field_name: str) -> str:
            """Extract display_value or value from field."""
            field = raw.get(field_name, {})
            if isinstance(field, dict):
                return field.get('display_value', field.get('value', ''))
            return str(field) if field else ''
        
        def get_datetime(field_name: str) -> Optional[str]:
            """Parse ServiceNow datetime to ISO format."""
            value = get_value(field_name)
            if not value:
                return None
            
            # PSEG format: 01-13-2026 02:00 PM
            formats = [
                '%m-%d-%Y %I:%M %p',     # 01-13-2026 02:00 PM
                '%m-%d-%Y %H:%M:%S',     # 01-13-2026 14:00:00
                '%Y-%m-%d %H:%M:%S',     # 2026-01-13 14:00:00
                '%Y-%m-%d',              # 2026-01-13
            ]
            
            for fmt in formats:
                try:
                    dt = datetime.strptime(value, fmt)
                    return dt.isoformat()
                except ValueError:
                    continue
            
            return value  # Return as-is if parsing fails
        
        # Extract CI name
        cmdb_ci = raw.get('cmdb_ci', {})
        if isinstance(cmdb_ci, dict):
            asset_name = cmdb_ci.get('display_value', '')
        else:
            asset_name = str(cmdb_ci) if cmdb_ci else ''
        
        return {
            'source': 'servicenow',
            'ticket_id': get_value('number'),
            'sys_id': get_value('sys_id'),
            
            # Asset
            'asset_name': asset_name,
            'asset_name_normalized': self._normalize_asset_name(asset_name),
            
            # Classification
            'short_description': get_value('short_description'),
            'full_description': get_value('description'),
            'category': get_value('category'),
            'subcategory': get_value('subcategory'),
            'activity': get_value('u_activity'),
            'environment': get_value('u_environment'),
            
            # Schedule
            'scheduled_start': get_datetime('start_date'),
            'scheduled_end': get_datetime('end_date'),
            'actual_start': get_datetime('work_start'),
            'actual_end': get_datetime('work_end'),
            
            # Status
            'state': get_value('state'),
            'approval_status': self._map_approval_status(get_value('approval')),
            
            # People
            'assignment_group': get_value('assignment_group'),
            'assigned_to': get_value('assigned_to'),
            'opened_by': get_value('opened_by'),
            'opened_at': get_datetime('opened_at'),
            
            # Plans
            'implementation_plan': get_value('implementation_plan'),
            'test_plan': get_value('test_plan'),
            'backout_plan': get_value('backout_plan'),
            
            # Additional
            'nerc_cip': get_value('u_nerc_cip_options'),
            
            # Raw data for debugging
            'raw_data': raw
        }
    
    def _map_approval_status(self, snow_approval: str) -> str:
        """Map ServiceNow approval value to standard status."""
        if not snow_approval:
            return 'unknown'
        
        mapping = {
            'approved': 'approved',
            'requested': 'pending',
            'not requested': 'pending',
            'rejected': 'rejected',
            'cancelled': 'cancelled',
            'not yet requested': 'pending'
        }
        return mapping.get(snow_approval.lower(), 'pending')
    
    def _normalize_asset_name(self, name: str) -> str:
        """Normalize asset name for fuzzy matching."""
        if not name:
            return ''
        
        normalized = name.lower().strip()
        
        # Remove PSEG-specific domain suffixes
        normalized = re.sub(r'\.(local|internal|corp|domain|psegli\.com)$', '', normalized)
        
        # Remove common PSEG prefixes
        normalized = re.sub(r'^(pcc|bcc|srv|wks|vm|host)[-_]?', '', normalized)
        
        return normalized
    
    def is_change_approved_and_closed(self, chg_number: str) -> bool:
        """
        Quick check if a CHG ticket is approved and successfully closed.
        Used for fast validation of CHG numbers found in ID comments.
        """
        change = self.lookup_chg_by_number(chg_number)
        
        if not change:
            return False
        
        return (
            change.get('approval_status') == 'approved' and
            'closed' in change.get('state', '').lower() and
            'successful' in change.get('state', '').lower()
        )


def extract_chg_numbers_from_comment(comment: str) -> List[str]:
    """
    Extract CHG ticket numbers from ID exception comment field.
    
    The ID comment field contains direct references to ServiceNow tickets:
    "Activity from DSCADA Monthly Patching: CHG0000338290 CHG0000338289 CHG0000338288 CHG0000338287"
    
    Args:
        comment: ID exception comment text
        
    Returns:
        List of CHG numbers found
    """
    if not comment:
        return []
    
    # PSEG CHG format: CHG followed by 10 digits
    pattern = r'CHG\d{10}'
    matches = re.findall(pattern, comment, re.IGNORECASE)
    
    # Deduplicate while preserving order
    seen = set()
    unique = []
    for m in matches:
        upper_m = m.upper()
        if upper_m not in seen:
            seen.add(upper_m)
            unique.append(upper_m)
    
    return unique


if __name__ == '__main__':
    # Test the connector
    from dotenv import load_dotenv
    load_dotenv()
    
    # Test CHG extraction from comment
    test_comment = "Activity from DSCADA Monthly Patching: CHG0000338290 CHG0000338289 CHG0000338288 CHG0000338287"
    chg_numbers = extract_chg_numbers_from_comment(test_comment)
    print(f"Extracted CHG numbers: {chg_numbers}")
    
    # Test ServiceNow connection (if credentials available)
    try:
        connector = PSEGServiceNowConnector()
        
        # Test direct lookup
        if chg_numbers:
            change = connector.lookup_chg_by_number(chg_numbers[0])
            if change:
                print(f"\nFound: {change['ticket_id']}")
                print(f"  Asset: {change['asset_name']}")
                print(f"  Status: {change['approval_status']}")
                print(f"  State: {change['state']}")
                print(f"  Window: {change['scheduled_start']} to {change['scheduled_end']}")
    except ValueError as e:
        print(f"ServiceNow not configured: {e}")
