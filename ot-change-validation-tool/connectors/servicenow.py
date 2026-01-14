"""
ServiceNow REST API Connector for OT Change Validation Tool.
Pulls change requests (CHG tickets) from ServiceNow Table API.
"""

import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
import os
import re
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ServiceNowConnector:
    """Connector for ServiceNow REST API."""
    
    def __init__(self):
        """Initialize connector with environment variables."""
        self.base_url = os.getenv('SNOW_INSTANCE_URL', '').rstrip('/')
        self.username = os.getenv('SNOW_USERNAME')
        self.password = os.getenv('SNOW_PASSWORD')
        
        if not all([self.base_url, self.username, self.password]):
            raise ValueError("Missing ServiceNow credentials in environment variables")
        
        self.session = requests.Session()
        self.session.auth = (self.username, self.password)
        self.session.headers.update({
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        })
    
    def fetch_recent_changes(self, minutes_ago: int = 30, 
                            assignment_group: str = None) -> List[Dict]:
        """
        Fetch change requests updated in the last N minutes.
        
        Args:
            minutes_ago: How far back to look for changes
            assignment_group: Optional filter by assignment group
            
        Returns:
            List of change request dictionaries
        """
        endpoint = f'{self.base_url}/api/now/table/change_request'
        
        # Build query
        query_parts = [f'sys_updated_on>javascript:gs.minutesAgoStart({minutes_ago})']
        
        if assignment_group:
            query_parts.append(f'assignment_group.name={assignment_group}')
        
        params = {
            'sysparm_query': '^'.join(query_parts),
            'sysparm_fields': ','.join([
                'number', 'short_description', 'description',
                'cmdb_ci', 'cmdb_ci.name', 'start_date', 'end_date',
                'state', 'approval', 'assigned_to', 'assignment_group',
                'sys_created_on', 'sys_updated_on', 'close_code',
                'u_change_type', 'category', 'type'
            ]),
            'sysparm_limit': 200,
            'sysparm_display_value': 'all'
        }
        
        try:
            response = self.session.get(endpoint, params=params, timeout=30)
            response.raise_for_status()
            results = response.json().get('result', [])
            logger.info(f"Fetched {len(results)} changes from ServiceNow")
            return results
        except requests.RequestException as e:
            logger.error(f"ServiceNow API error: {e}")
            raise
    
    def fetch_change_by_number(self, change_number: str) -> Optional[Dict]:
        """Fetch a specific change by its number (e.g., CHG0012345)."""
        endpoint = f'{self.base_url}/api/now/table/change_request'
        params = {
            'sysparm_query': f'number={change_number}',
            'sysparm_limit': 1,
            'sysparm_display_value': 'all'
        }
        
        try:
            response = self.session.get(endpoint, params=params, timeout=30)
            response.raise_for_status()
            results = response.json().get('result', [])
            return results[0] if results else None
        except requests.RequestException as e:
            logger.error(f"Error fetching change {change_number}: {e}")
            return None
    
    def normalize_change(self, raw: Dict) -> Dict:
        """
        Transform ServiceNow record to standard format for our database.
        
        Args:
            raw: Raw ServiceNow API response for a change request
            
        Returns:
            Normalized change dictionary
        """
        # Extract CI name (configuration item / asset)
        cmdb_ci = raw.get('cmdb_ci', {})
        if isinstance(cmdb_ci, dict):
            asset_name = cmdb_ci.get('display_value', '')
        else:
            asset_name = str(cmdb_ci) if cmdb_ci else ''
        
        # Extract KB articles from description
        description = raw.get('description', {})
        if isinstance(description, dict):
            description_text = description.get('display_value', '')
        else:
            description_text = str(description) if description else ''
        
        kb_articles = self._extract_kb_articles(description_text)
        
        # Map approval status
        approval = raw.get('approval', {})
        if isinstance(approval, dict):
            approval_value = approval.get('value', '')
        else:
            approval_value = str(approval) if approval else ''
        
        return {
            'source': 'servicenow',
            'ticket_id': self._get_value(raw, 'number'),
            'asset_name': asset_name,
            'asset_name_normalized': self._normalize_asset_name(asset_name),
            'change_type': self._determine_change_type(raw),
            'description': description_text,
            'scheduled_start': self._parse_date(self._get_value(raw, 'start_date')),
            'scheduled_end': self._parse_date(self._get_value(raw, 'end_date')),
            'approval_status': self._map_approval_status(approval_value),
            'approved_by': self._get_value(raw, 'assigned_to'),
            'kb_articles': kb_articles,
            'raw_data': raw
        }
    
    def _get_value(self, data: Dict, key: str) -> str:
        """Extract display_value or value from ServiceNow field."""
        field = data.get(key, {})
        if isinstance(field, dict):
            return field.get('display_value', field.get('value', ''))
        return str(field) if field else ''
    
    def _parse_date(self, date_str: str) -> Optional[str]:
        """Parse ServiceNow date string to ISO format."""
        if not date_str:
            return None
        
        # ServiceNow typically returns: 2024-01-15 10:30:00
        formats = [
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d',
            '%m/%d/%Y %H:%M:%S',
            '%m/%d/%Y'
        ]
        
        for fmt in formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                return dt.isoformat()
            except ValueError:
                continue
        
        return date_str  # Return as-is if parsing fails
    
    def _map_approval_status(self, snow_approval: str) -> str:
        """Map ServiceNow approval values to standard status."""
        mapping = {
            'approved': 'approved',
            'requested': 'pending',
            'not requested': 'pending',
            'rejected': 'rejected',
            'cancelled': 'cancelled',
            'not yet requested': 'pending'
        }
        return mapping.get(snow_approval.lower(), 'pending')
    
    def _determine_change_type(self, raw: Dict) -> str:
        """Determine the type of change from ServiceNow fields."""
        # Check custom field first
        change_type = self._get_value(raw, 'u_change_type').lower()
        if change_type:
            if 'patch' in change_type or 'update' in change_type:
                return 'patch'
            elif 'config' in change_type:
                return 'config'
            elif 'software' in change_type or 'install' in change_type:
                return 'software'
        
        # Check description for keywords
        desc = self._get_value(raw, 'short_description').lower()
        if any(kw in desc for kw in ['patch', 'update', 'kb', 'hotfix']):
            return 'patch'
        elif any(kw in desc for kw in ['config', 'setting', 'parameter']):
            return 'config'
        elif any(kw in desc for kw in ['install', 'software', 'application']):
            return 'software'
        elif any(kw in desc for kw in ['user', 'account', 'access']):
            return 'user'
        
        return 'general'
    
    def _extract_kb_articles(self, text: str) -> List[str]:
        """Extract KB article numbers from text."""
        if not text:
            return []
        
        # Match patterns like KB1234567, KB 1234567, KB-1234567
        pattern = r'KB[- ]?(\d{6,7})'
        matches = re.findall(pattern, text, re.IGNORECASE)
        return [f'KB{m}' for m in matches]
    
    def _normalize_asset_name(self, name: str) -> str:
        """Normalize asset name for matching."""
        if not name:
            return ''
        
        # Convert to lowercase, remove extra whitespace
        normalized = name.lower().strip()
        
        # Remove common prefixes/suffixes
        prefixes = ['srv-', 'wks-', 'vm-', 'host-']
        for prefix in prefixes:
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix):]
        
        # Remove domain suffixes
        normalized = re.sub(r'\.(local|internal|corp|domain)$', '', normalized)
        
        return normalized


class ServiceNowSyncer:
    """Handles syncing ServiceNow data to local database."""
    
    def __init__(self, connector: ServiceNowConnector, database):
        self.connector = connector
        self.db = database
    
    def sync(self, minutes_ago: int = 30) -> int:
        """
        Sync recent changes from ServiceNow to local database.
        
        Returns:
            Number of records synced
        """
        try:
            # Fetch from ServiceNow
            raw_changes = self.connector.fetch_recent_changes(minutes_ago)
            
            # Normalize and upsert each change
            count = 0
            for raw in raw_changes:
                normalized = self.connector.normalize_change(raw)
                self.db.upsert_change(normalized)
                count += 1
            
            # Update sync status
            self.db.update_sync_status('servicenow', count, 'success')
            logger.info(f"Synced {count} changes from ServiceNow")
            return count
            
        except Exception as e:
            self.db.update_sync_status('servicenow', 0, 'failed', str(e))
            logger.error(f"ServiceNow sync failed: {e}")
            raise


if __name__ == '__main__':
    # Test the connector
    from dotenv import load_dotenv
    load_dotenv()
    
    connector = ServiceNowConnector()
    changes = connector.fetch_recent_changes(minutes_ago=60)
    
    for change in changes[:5]:
        normalized = connector.normalize_change(change)
        print(f"\n{normalized['ticket_id']}: {normalized['asset_name']}")
        print(f"  Type: {normalized['change_type']}")
        print(f"  Status: {normalized['approval_status']}")
        print(f"  KB Articles: {normalized['kb_articles']}")
