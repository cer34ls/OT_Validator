"""
Mantis Bug Tracker Connector
Supports REST API or direct database access.
"""

import requests
from typing import List, Dict, Optional
import os
import re
import logging

logger = logging.getLogger(__name__)


class MantisConnector:
    """Connector for Mantis Bug Tracker REST API."""

    def __init__(self, base_url: str = None, api_token: str = None):
        self.base_url = (base_url or os.getenv('MANTIS_URL', '')).rstrip('/')
        self.api_token = api_token or os.getenv('MANTIS_API_TOKEN', '')

        self.headers = {'Authorization': self.api_token}

    def is_configured(self) -> bool:
        """Check if Mantis is configured."""
        return bool(self.base_url and self.api_token)

    def fetch_issues(self, project_id: int = None,
                     filter_id: int = None,
                     page_size: int = 50) -> List[Dict]:
        """Fetch issues from Mantis REST API."""

        if not self.is_configured():
            logger.warning("Mantis not configured, skipping")
            return []

        endpoint = f'{self.base_url}/api/rest/issues'
        params = {'page_size': page_size}

        if project_id:
            params['project_id'] = project_id
        if filter_id:
            params['filter_id'] = filter_id

        try:
            response = requests.get(endpoint, headers=self.headers, params=params, timeout=30)
            response.raise_for_status()
            return response.json().get('issues', [])
        except requests.RequestException as e:
            logger.error(f"Mantis API error: {e}")
            return []

    def fetch_issue_by_id(self, issue_id: int) -> Optional[Dict]:
        """Fetch a specific Mantis issue by ID."""
        if not self.is_configured():
            return None

        endpoint = f'{self.base_url}/api/rest/issues/{issue_id}'

        try:
            response = requests.get(endpoint, headers=self.headers, timeout=30)
            response.raise_for_status()
            issues = response.json().get('issues', [])
            return issues[0] if issues else None
        except requests.RequestException as e:
            logger.error(f"Error fetching Mantis issue {issue_id}: {e}")
            return None

    def normalize_issue(self, raw: Dict) -> Dict:
        """Transform Mantis issue to standard change format."""
        return {
            'source': 'mantis',
            'ticket_id': f"MANTIS-{raw.get('id')}",
            'asset_name': self._extract_asset(raw),
            'asset_name_normalized': self._extract_asset(raw).lower(),
            'description': raw.get('description', ''),
            'short_description': raw.get('summary', ''),
            'scheduled_start': raw.get('created_at'),
            'scheduled_end': raw.get('updated_at'),
            'approval_status': self._map_status(raw.get('status', {})),
            'category': raw.get('category', {}).get('name', ''),
            'assigned_to': raw.get('handler', {}).get('name', ''),
            'raw_data': raw,
        }

    def _extract_asset(self, raw: Dict) -> str:
        """Extract asset name from Mantis issue."""
        # Try custom field first
        for field in raw.get('custom_fields', []):
            if field.get('field', {}).get('name', '').lower() in ('asset', 'server', 'host'):
                return field.get('value', '')

        # Fall back to parsing summary
        summary = raw.get('summary', '')
        # Add custom parsing logic based on your Mantis ticket format
        return ''

    def _map_status(self, status: Dict) -> str:
        """Map Mantis status to standard approval status."""
        name = status.get('name', '').lower()

        if name in ('resolved', 'closed', 'approved'):
            return 'approved'
        elif name in ('new', 'assigned', 'confirmed'):
            return 'pending'
        elif name in ('rejected'):
            return 'rejected'

        return 'pending'


class MantisSyncer:
    """Syncs Mantis issues to database."""

    def __init__(self, connector: MantisConnector, database):
        self.connector = connector
        self.db = database

    def sync(self, project_id: int = None) -> int:
        """Sync Mantis issues to local database."""
        if not self.connector.is_configured():
            logger.info("Mantis not configured, skipping sync")
            return 0

        try:
            issues = self.connector.fetch_issues(project_id=project_id)

            count = 0
            for raw in issues:
                normalized = self.connector.normalize_issue(raw)
                self.db.upsert_change(normalized)
                count += 1

            self.db.update_sync_status('mantis', count, 'success')
            logger.info(f"Synced {count} Mantis issues")
            return count

        except Exception as e:
            self.db.update_sync_status('mantis', 0, 'failed', str(e))
            logger.error(f"Mantis sync failed: {e}")
            return 0


if __name__ == '__main__':
    # Test connector
    from dotenv import load_dotenv
    load_dotenv()

    connector = MantisConnector()

    if connector.is_configured():
        issues = connector.fetch_issues(page_size=5)
        print(f"Found {len(issues)} issues")
        for issue in issues:
            normalized = connector.normalize_issue(issue)
            print(f"  - {normalized['ticket_id']}: {normalized['short_description'][:50]}...")
    else:
        print("Mantis not configured. Set MANTIS_URL and MANTIS_API_TOKEN.")
