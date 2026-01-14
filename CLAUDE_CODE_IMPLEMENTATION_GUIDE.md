# OT Change Validation Tool - Claude Code Implementation Guide

## Overview

This guide provides step-by-step instructions for Claude Code to build the OT Change Validation Tool from the provided starter code and field mappings.

**Goal:** Build a tool that automatically correlates Industrial Defender baseline change alerts with approved ServiceNow change tickets, WSUS patches, and Mantis tickets.

**Budget:** $0 - All open source technologies

**Timeline:** 4-6 hours of Claude Code work

---

## Prerequisites

Before starting, ensure you have:
- [ ] Python 3.10+ installed
- [ ] The `ot-validation-tool-v2.zip` extracted to your project directory
- [ ] The `OT_Change_Validation_Field_Mapping.md` file for reference
- [ ] Access to ServiceNow API credentials (or mock data for testing)

---

## Phase 1: Project Setup (30 minutes)

### Step 1.1: Create Project Structure

```bash
# Create the full project structure
mkdir -p ot-change-validation-tool/{config,database,connectors,engine,app,app/pages,scripts,tests,data,logs}

cd ot-change-validation-tool

# Create __init__.py files
touch config/__init__.py
touch database/__init__.py
touch connectors/__init__.py
touch engine/__init__.py
touch app/__init__.py
touch tests/__init__.py
```

### Step 1.2: Create requirements.txt

```
# requirements.txt

# Web UI
streamlit>=1.28.0

# Data processing
pandas>=2.0.0
python-dateutil>=2.8.0

# HTTP requests
requests>=2.31.0

# API (optional REST API)
fastapi>=0.104.0
uvicorn>=0.24.0

# Scheduling
apscheduler>=3.10.0

# Email parsing (for ID alerts)
imapclient>=2.3.0

# Environment management
python-dotenv>=1.0.0

# Excel export for reports
openpyxl>=3.1.0
xlsxwriter>=3.1.0

# Testing
pytest>=7.4.0
pytest-cov>=4.1.0

# CLI
click>=8.1.0
rich>=13.0.0
```

### Step 1.3: Create Environment Configuration

```python
# config/settings.py

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Base paths
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

# Database
DATABASE_PATH = os.getenv("DATABASE_PATH", str(DATA_DIR / "validation_tool.db"))

# ServiceNow Configuration
SERVICENOW_CONFIG = {
    "instance_url": os.getenv("SNOW_INSTANCE_URL", "https://your-instance.service-now.com"),
    "username": os.getenv("SNOW_USERNAME", ""),
    "password": os.getenv("SNOW_PASSWORD", ""),
}

# Email Configuration (for ID alerts)
EMAIL_CONFIG = {
    "imap_server": os.getenv("IMAP_SERVER", ""),
    "username": os.getenv("IMAP_USERNAME", ""),
    "password": os.getenv("IMAP_PASSWORD", ""),
    "folder": os.getenv("IMAP_FOLDER", "INBOX"),
}

# WSUS Import Path
WSUS_IMPORT_PATH = os.getenv("WSUS_IMPORT_PATH", str(DATA_DIR / "wsus_imports"))

# ID Export Path (for CSV imports)
ID_EXPORT_PATH = os.getenv("ID_EXPORT_PATH", str(DATA_DIR / "id_exports"))

# Correlation Settings
CORRELATION_CONFIG = {
    "auto_validate_threshold": 0.95,  # 95% confidence = auto-validate
    "minimum_match_threshold": 0.50,  # Below 50% = no match
    "time_buffer_hours": 24,          # ±24 hour window for time correlation
}

# Dashboard
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", 8501))
```

### Step 1.4: Create .env.example

```bash
# config/.env.example

# ServiceNow API
SNOW_INSTANCE_URL=https://your-instance.service-now.com
SNOW_USERNAME=api_user
SNOW_PASSWORD=your_password

# Email for ID Alerts (IMAP)
IMAP_SERVER=mail.yourcompany.com
IMAP_USERNAME=id-alerts@yourcompany.com
IMAP_PASSWORD=your_email_password
IMAP_FOLDER=INBOX

# WSUS Import Path
WSUS_IMPORT_PATH=/path/to/wsus/exports

# ID Export Path
ID_EXPORT_PATH=/path/to/id/exports

# Database
DATABASE_PATH=/path/to/validation_tool.db

# Dashboard
DASHBOARD_PORT=8501
```

---

## Phase 2: Database Layer (45 minutes)

### Step 2.1: Copy and Update Database Module

Copy `database/db.py` from the starter zip, then update the schema to include all fields from the field mapping document.

### Step 2.2: Create Database Initialization Script

```python
# scripts/init_db.py

"""Initialize the database with schema and seed data."""

import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.db import Database
from config.settings import DATABASE_PATH

def main():
    print(f"Initializing database at: {DATABASE_PATH}")
    
    db = Database(DATABASE_PATH)
    db.init()
    
    # Add some default asset group mappings
    print("Database initialized successfully!")
    print("\nTables created:")
    print("  - changes (ServiceNow/Mantis tickets)")
    print("  - alerts (ID exceptions)")  
    print("  - validations (correlation results)")
    print("  - wsus_patches (approved KB articles)")
    print("  - assets (asset name mappings)")
    print("  - sync_status (data source status)")
    print("  - audit_log (compliance trail)")

if __name__ == "__main__":
    main()
```

### Step 2.3: Run Database Initialization

```bash
python scripts/init_db.py
```

---

## Phase 3: Connectors (1.5 hours)

### Step 3.1: ServiceNow Connector

Copy `connectors/servicenow_pseg.py` from the starter zip. This is already configured with PSEG field mappings.

**Key functions to verify:**
- `lookup_chg_by_number(chg_number)` - Direct CHG lookup
- `lookup_multiple_chg(chg_numbers)` - Batch lookup
- `fetch_recent_ot_changes(hours_ago)` - Get recent changes
- `extract_chg_numbers_from_comment(comment)` - Parse CHG from ID comments

### Step 3.2: ID Exception Parser

Copy `connectors/id_parser.py` from the starter zip.

**Key functions to verify:**
- `parse_csv(csv_path)` - Parse ID Bulk Exceptions export
- `detect_exception_type(headers)` - Auto-detect tab type
- `to_database_records(exceptions)` - Convert to DB format

### Step 3.3: Create WSUS Importer

```python
# connectors/wsus_importer.py

"""
WSUS Approved Patches Importer
Imports CSV exports from WSUS PowerShell script.
"""

import csv
from pathlib import Path
from datetime import datetime
from typing import List, Dict
import logging

logger = logging.getLogger(__name__)


class WSUSImporter:
    """Imports WSUS approved patches from CSV exports."""
    
    def __init__(self, import_path: str):
        self.import_path = Path(import_path)
    
    def find_latest_export(self) -> Path:
        """Find the most recent WSUS export file."""
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
    
    def _parse_date(self, value: str) -> str:
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
    
    def sync(self) -> int:
        """Import WSUS patches and sync to database."""
        try:
            patches = self.importer.import_patches()
            
            count = 0
            for patch in patches:
                self.db.upsert_wsus_patch(patch)
                count += 1
            
            self.db.update_sync_status('wsus', count, 'success')
            logger.info(f"Synced {count} WSUS patches")
            return count
            
        except Exception as e:
            self.db.update_sync_status('wsus', 0, 'failed', str(e))
            logger.error(f"WSUS sync failed: {e}")
            raise
```

### Step 3.4: Create Mantis Connector (Optional)

```python
# connectors/mantis.py

"""
Mantis Bug Tracker Connector
Supports REST API or direct database access.
"""

import requests
from typing import List, Dict, Optional
import os
import logging

logger = logging.getLogger(__name__)


class MantisConnector:
    """Connector for Mantis Bug Tracker REST API."""
    
    def __init__(self, base_url: str = None, api_token: str = None):
        self.base_url = (base_url or os.getenv('MANTIS_URL', '')).rstrip('/')
        self.api_token = api_token or os.getenv('MANTIS_API_TOKEN', '')
        
        self.headers = {'Authorization': self.api_token}
    
    def fetch_issues(self, project_id: int = None, 
                    filter_id: int = None,
                    page_size: int = 50) -> List[Dict]:
        """Fetch issues from Mantis REST API."""
        
        if not self.base_url or not self.api_token:
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
```

---

## Phase 4: Correlation Engine (1 hour)

### Step 4.1: Copy and Update Correlation Engine

Copy `engine/correlator.py` from the starter zip, then update to use the exact correlation logic:

```python
# engine/correlator.py - Key update for direct CHG lookup

def correlate_with_direct_lookup(self, exception: Dict) -> Optional[CorrelationResult]:
    """
    PRIMARY CORRELATION PATH
    Uses CHG numbers from ID comment field for direct ServiceNow lookup.
    
    This is the fastest and most accurate correlation method.
    """
    comment = exception.get('comment', '')
    
    # Extract CHG numbers from comment
    chg_numbers = extract_chg_numbers_from_comment(comment)
    
    if not chg_numbers:
        return None
    
    # Lookup all CHG tickets
    changes = self.snow_connector.lookup_multiple_chg(chg_numbers)
    
    # Filter to approved and closed successful
    approved_changes = [
        c for c in changes
        if c.get('approval_status') == 'approved'
        and 'closed' in c.get('state', '').lower()
    ]
    
    if approved_changes:
        # Use the first approved change as the match
        change = approved_changes[0]
        
        return CorrelationResult(
            change_id=change.get('sys_id'),
            ticket_id=change.get('ticket_id'),
            score=1.0,  # 100% confidence
            factors={'direct_chg_match': 1.0},
            is_auto_validated=True,
            validation_rule='direct_chg_lookup',
            matched_chg_numbers=chg_numbers,
            all_matched_changes=approved_changes,
        )
    
    return None
```

### Step 4.2: Create Validation Processor

```python
# engine/validator.py

"""
Validation Processor
Orchestrates the full validation workflow.
"""

from typing import Dict, List, Optional
from datetime import datetime
import logging

from .correlator import CorrelationEngine, CorrelationResult
from connectors.id_parser import IDException, ExceptionType

logger = logging.getLogger(__name__)


class ValidationProcessor:
    """Processes ID exceptions and creates validation records."""
    
    def __init__(self, database, snow_connector=None, wsus_importer=None):
        self.db = database
        self.correlator = CorrelationEngine(database)
        self.snow = snow_connector
        
        if snow_connector:
            self.correlator.snow_connector = snow_connector
    
    def process_exception(self, exception: IDException) -> Dict:
        """
        Process a single ID exception through the validation pipeline.
        
        Returns validation result with correlation details.
        """
        result = {
            'exception_type': exception.exception_type.value,
            'detected_at': exception.detected_at.isoformat() if exception.detected_at else None,
            'asset_group': exception.asset_group,
            'correlation_method': None,
            'is_validated': False,
            'confidence': 0.0,
            'matched_tickets': [],
            'notes': [],
        }
        
        # Step 1: Try direct CHG lookup (PRIMARY PATH)
        if exception.extracted_chg_numbers:
            logger.info(f"Found CHG numbers in comment: {exception.extracted_chg_numbers}")
            result['notes'].append(f"CHG numbers found: {exception.extracted_chg_numbers}")
            
            if self.snow:
                correlation = self.correlator.correlate_with_direct_lookup({
                    'comment': exception.comment,
                })
                
                if correlation and correlation.is_auto_validated:
                    result['correlation_method'] = 'direct_chg_lookup'
                    result['is_validated'] = True
                    result['confidence'] = 1.0
                    result['matched_tickets'] = correlation.matched_chg_numbers
                    result['notes'].append("Auto-validated via direct CHG lookup")
                    
                    return result
        
        # Step 2: Try WSUS KB match (for patches)
        if exception.exception_type == ExceptionType.PATCHES_INSTALLED:
            kb_numbers = exception.details.get('kb_numbers', [])
            
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
    
    def process_batch(self, exceptions: List[IDException]) -> Dict:
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
            
            exc_type = exc.exception_type.value
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
```

---

## Phase 5: Streamlit Dashboard (1.5 hours)

### Step 5.1: Create Main Dashboard App

```python
# app/dashboard.py

"""
OT Change Validation Tool - Main Dashboard
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.db import Database
from config.settings import DATABASE_PATH, DASHBOARD_PORT

# Page configuration
st.set_page_config(
    page_title="OT Change Validation Tool",
    page_icon="🔒",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize database
@st.cache_resource
def get_database():
    return Database(DATABASE_PATH)

db = get_database()

# Sidebar
st.sidebar.title("🔒 OT Validation Tool")
st.sidebar.markdown("---")

# Navigation
page = st.sidebar.radio(
    "Navigate",
    [
        "📋 Pending Validations",
        "🔍 Search",
        "📊 Dashboard",
        "📥 Import Data",
        "📄 Reports",
        "⚙️ Settings",
    ]
)

st.sidebar.markdown("---")

# Sync status
st.sidebar.subheader("Sync Status")
sync_status = db.get_sync_status()
for status in sync_status:
    icon = "✅" if status['status'] == 'success' else "❌"
    st.sidebar.text(f"{icon} {status['source_name']}: {status['last_sync'] or 'Never'}")

# Main content based on page selection
if page == "📋 Pending Validations":
    st.header("Pending Validation Queue")
    
    # Get pending alerts
    pending = db.get_pending_alerts()
    
    if not pending:
        st.success("✅ No pending validations! All caught up.")
    else:
        st.warning(f"⚠️ {len(pending)} items pending review")
        
        # Display as table
        df = pd.DataFrame(pending)
        
        # Add action buttons
        for idx, row in df.iterrows():
            with st.expander(f"**{row.get('asset_name', 'Unknown')}** - {row.get('change_category', 'N/A')}", expanded=False):
                col1, col2 = st.columns([3, 1])
                
                with col1:
                    st.write(f"**Detected:** {row.get('detected_at')}")
                    st.write(f"**Change:** {row.get('change_detail', 'N/A')}")
                    st.write(f"**Asset Group:** {row.get('asset_group', 'N/A')}")
                    
                    if row.get('matched_ticket'):
                        st.info(f"🔗 Suggested Match: {row['matched_ticket']} (Score: {row.get('correlation_score', 0):.0%})")
                
                with col2:
                    if st.button("✅ Validate", key=f"val_{row['id']}"):
                        db.update_alert_status(row['id'], 'validated', 'manual')
                        st.rerun()
                    
                    if st.button("⚠️ Unauthorized", key=f"unauth_{row['id']}"):
                        db.update_alert_status(row['id'], 'unauthorized', 'manual')
                        st.rerun()
                    
                    if st.button("🔍 Investigate", key=f"inv_{row['id']}"):
                        db.update_alert_status(row['id'], 'investigating', 'manual')
                        st.rerun()

elif page == "🔍 Search":
    st.header("Search All Sources")
    
    search_query = st.text_input("Search tickets, assets, KB articles...", placeholder="CHG0000338771 or KB5062070 or server01")
    
    if search_query:
        # Search changes
        results = db.search_changes(search_query)
        
        if results:
            st.subheader(f"Found {len(results)} results")
            
            for r in results:
                with st.expander(f"**{r['ticket_id']}** - {r['source']}"):
                    st.write(f"**Asset:** {r.get('asset_name', 'N/A')}")
                    st.write(f"**Description:** {r.get('description', 'N/A')[:200]}...")
                    st.write(f"**Status:** {r.get('approval_status', 'N/A')}")
                    st.write(f"**Window:** {r.get('scheduled_start')} to {r.get('scheduled_end')}")
        else:
            st.info("No results found")

elif page == "📊 Dashboard":
    st.header("Validation Metrics")
    
    metrics = db.get_metrics()
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Pending", metrics.get('pending_count', 0))
    
    with col2:
        st.metric("Validated Today", metrics.get('validated_today', 0))
    
    with col3:
        st.metric("Auto-Validation Rate", f"{metrics.get('auto_validation_rate', 0):.0f}%")
    
    with col4:
        st.metric("Unauthorized (30d)", metrics.get('unauthorized_count', 0), delta_color="inverse")

elif page == "📥 Import Data":
    st.header("Import Data")
    
    st.subheader("Import ID Bulk Exceptions CSV")
    
    uploaded_file = st.file_uploader("Upload ID Export CSV", type=['csv'])
    
    if uploaded_file:
        # Save and process
        import tempfile
        from connectors.id_parser import IDExceptionParser
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.csv') as tmp:
            tmp.write(uploaded_file.getvalue())
            tmp_path = tmp.name
        
        try:
            parser = IDExceptionParser()
            exceptions = parser.parse_csv(tmp_path)
            
            st.success(f"Parsed {len(exceptions)} exceptions")
            
            # Show preview
            if exceptions:
                preview_data = []
                for exc in exceptions[:10]:
                    preview_data.append({
                        'Type': exc.exception_type.value,
                        'Action': exc.change_action.value,
                        'Asset Group': exc.asset_group,
                        'CHG Numbers': ', '.join(exc.extracted_chg_numbers) if exc.extracted_chg_numbers else 'None',
                        'Detected': exc.detected_at,
                    })
                
                st.dataframe(pd.DataFrame(preview_data))
                
                if st.button("Process and Validate"):
                    from engine.validator import ValidationProcessor
                    processor = ValidationProcessor(db)
                    summary = processor.process_batch(exceptions)
                    
                    st.success(f"Processed {summary['total']} exceptions")
                    st.write(f"- Auto-validated: {summary['auto_validated']}")
                    st.write(f"- Pending review: {summary['pending_review']}")
        
        except Exception as e:
            st.error(f"Error processing file: {e}")

elif page == "📄 Reports":
    st.header("Audit Reports")
    
    st.subheader("Generate CIP-010 Validation Report")
    
    col1, col2 = st.columns(2)
    
    with col1:
        start_date = st.date_input("Start Date", datetime.now() - timedelta(days=30))
    
    with col2:
        end_date = st.date_input("End Date", datetime.now())
    
    if st.button("Generate Report"):
        st.info("Report generation coming soon...")
        # TODO: Implement report generation

elif page == "⚙️ Settings":
    st.header("Settings")
    
    st.subheader("Data Source Configuration")
    st.info("Configure data sources in the .env file")
    
    st.subheader("Correlation Thresholds")
    auto_threshold = st.slider("Auto-Validation Threshold", 0.5, 1.0, 0.95)
    time_buffer = st.number_input("Time Buffer (hours)", 1, 72, 24)
    
    if st.button("Save Settings"):
        st.success("Settings saved!")
```

### Step 5.2: Create Additional Pages

Create these files in `app/pages/`:

```python
# app/pages/1_📋_Pending.py
# (Move pending validations logic here for multi-page app)

# app/pages/2_🔍_Search.py  
# (Move search logic here)

# app/pages/3_📊_Metrics.py
# (Move dashboard metrics here)

# app/pages/4_📥_Import.py
# (Move import logic here)

# app/pages/5_📄_Reports.py
# (Move reports logic here)
```

---

## Phase 6: Scheduled Jobs (30 minutes)

### Step 6.1: Create Sync Scripts

```python
# scripts/sync_all.py

"""
Master sync script - runs all data source syncs.
"""

import sys
from pathlib import Path
import logging
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from database.db import Database
from config.settings import DATABASE_PATH, WSUS_IMPORT_PATH, ID_EXPORT_PATH
from connectors.wsus_importer import WSUSImporter, WSUSSyncer

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def sync_wsus():
    """Sync WSUS approved patches."""
    logger.info("Starting WSUS sync...")
    
    try:
        db = Database(DATABASE_PATH)
        importer = WSUSImporter(WSUS_IMPORT_PATH)
        syncer = WSUSSyncer(importer, db)
        count = syncer.sync()
        logger.info(f"WSUS sync complete: {count} patches")
        return count
    except Exception as e:
        logger.error(f"WSUS sync failed: {e}")
        return 0


def sync_servicenow():
    """Sync recent ServiceNow changes."""
    logger.info("Starting ServiceNow sync...")
    
    try:
        from connectors.servicenow_pseg import PSEGServiceNowConnector
        from config.settings import SERVICENOW_CONFIG
        
        if not SERVICENOW_CONFIG['username']:
            logger.warning("ServiceNow not configured, skipping")
            return 0
        
        db = Database(DATABASE_PATH)
        connector = PSEGServiceNowConnector(**SERVICENOW_CONFIG)
        
        changes = connector.fetch_recent_ot_changes(hours_ago=24)
        
        count = 0
        for change in changes:
            db.upsert_change(change)
            count += 1
        
        db.update_sync_status('servicenow', count, 'success')
        logger.info(f"ServiceNow sync complete: {count} changes")
        return count
        
    except Exception as e:
        logger.error(f"ServiceNow sync failed: {e}")
        return 0


def main():
    """Run all syncs."""
    logger.info(f"=== Starting sync at {datetime.now()} ===")
    
    results = {
        'wsus': sync_wsus(),
        'servicenow': sync_servicenow(),
    }
    
    logger.info(f"=== Sync complete: {results} ===")
    return results


if __name__ == "__main__":
    main()
```

### Step 6.2: Create Cron Configuration

```bash
# crontab entries (add with: crontab -e)

# Sync ServiceNow every 15 minutes
*/15 * * * * cd /path/to/ot-change-validation-tool && python scripts/sync_all.py >> logs/sync.log 2>&1

# Process ID emails every 5 minutes
*/5 * * * * cd /path/to/ot-change-validation-tool && python scripts/process_emails.py >> logs/email.log 2>&1

# Daily database backup at 2 AM
0 2 * * * cp /path/to/data/validation_tool.db /path/to/backups/validation_tool_$(date +\%Y\%m\%d).db
```

---

## Phase 7: Testing (30 minutes)

### Step 7.1: Create Test Data

```python
# tests/test_data.py

"""Test data generators."""

TEST_ID_COMMENT_WITH_CHG = """Activity from DSCADA Monthly Patching: CHG0000338290 CHG0000338289 CHG0000338288 CHG0000338287"""

TEST_ID_EXCEPTION = {
    'exception_type': 'patches_installed',
    'change_action': 'removed',
    'asset_group': 'All_Windows, Domain Controllers',
    'asset_count': 2,
    'comment': TEST_ID_COMMENT_WITH_CHG,
    'detected_at': '12/24/2025 2:00:19 AM',
    'patch_id': 'KB5062070',
}

TEST_SERVICENOW_CHANGE = {
    'number': 'CHG0000338771',
    'state': 'Closed Successful',
    'approval': 'Approved',
    'cmdb_ci': {'display_value': 'pccqasasm1'},
    'start_date': '01-13-2026 02:00 PM',
    'end_date': '01-14-2026 02:00 PM',
    'short_description': 'DSCADA QAS ID - Patch platform based on supports guidance',
    'subcategory': 'Industrial Defender',
}
```

### Step 7.2: Create Unit Tests

```python
# tests/test_correlator.py

"""Tests for correlation engine."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from connectors.servicenow_pseg import extract_chg_numbers_from_comment
from connectors.id_parser import IDExceptionParser


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
    
    def test_extract_no_chg(self):
        comment = "Just a regular comment with no ticket numbers"
        
        result = extract_chg_numbers_from_comment(comment)
        
        assert len(result) == 0
    
    def test_extract_empty_comment(self):
        result = extract_chg_numbers_from_comment("")
        assert len(result) == 0
        
        result = extract_chg_numbers_from_comment(None)
        assert len(result) == 0


class TestIDParser:
    """Test ID exception parser."""
    
    def test_detect_patches_type(self):
        parser = IDExceptionParser()
        
        headers = ['Type', 'Patch ID', 'Service Pack In Effect', 'Asset Groups', 'Assets', 'Comment', 'Exception Detection Date']
        
        result = parser.detect_exception_type(headers)
        
        from connectors.id_parser import ExceptionType
        assert result == ExceptionType.PATCHES_INSTALLED


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
```

### Step 7.3: Run Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=. --cov-report=html
```

---

## Phase 8: Deployment (30 minutes)

### Step 8.1: Create Run Script

```bash
#!/bin/bash
# run.sh - Start the validation tool

# Activate virtual environment
source venv/bin/activate

# Initialize database if needed
python scripts/init_db.py

# Run initial sync
python scripts/sync_all.py

# Start dashboard
streamlit run app/dashboard.py --server.port 8501 --server.address 0.0.0.0
```

### Step 8.2: Create Systemd Service (Linux)

```ini
# /etc/systemd/system/ot-validation-tool.service

[Unit]
Description=OT Change Validation Tool
After=network.target

[Service]
Type=simple
User=otvalidation
WorkingDirectory=/opt/ot-change-validation-tool
ExecStart=/opt/ot-change-validation-tool/venv/bin/streamlit run app/dashboard.py --server.port 8501
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Step 8.3: Final Checklist

```markdown
## Deployment Checklist

- [ ] Python 3.10+ installed
- [ ] Virtual environment created and activated
- [ ] All dependencies installed (`pip install -r requirements.txt`)
- [ ] `.env` file configured with credentials
- [ ] Database initialized (`python scripts/init_db.py`)
- [ ] WSUS export path accessible
- [ ] ServiceNow API credentials tested
- [ ] Initial sync completed (`python scripts/sync_all.py`)
- [ ] Dashboard accessible at http://localhost:8501
- [ ] Cron jobs configured for scheduled syncs
- [ ] Log rotation configured
- [ ] Backup schedule in place
```

---

## Quick Start Commands

```bash
# 1. Clone/extract project
unzip ot-validation-tool-v2.zip
cd ot-validation-tool

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp config/.env.example config/.env
# Edit .env with your credentials

# 5. Initialize database
python scripts/init_db.py

# 6. Run initial sync (if ServiceNow configured)
python scripts/sync_all.py

# 7. Start dashboard
streamlit run app/dashboard.py

# 8. Open browser to http://localhost:8501
```

---

## Troubleshooting

### Common Issues

**Issue:** ServiceNow API returns 401 Unauthorized
- **Solution:** Verify SNOW_USERNAME and SNOW_PASSWORD in .env file

**Issue:** CSV import fails with encoding error
- **Solution:** Ensure CSV is saved with UTF-8 encoding from ID export

**Issue:** No CHG numbers extracted from comment
- **Solution:** Verify the comment field format matches `CHG\d{10}` pattern

**Issue:** Database locked error
- **Solution:** Ensure only one process is writing to SQLite at a time

---

## Next Steps After Initial Build

1. **Test with real data:** Import actual ID Bulk Exceptions CSV
2. **Verify correlation:** Confirm CHG lookup returns expected results
3. **Tune thresholds:** Adjust auto-validation threshold based on results
4. **Add notifications:** Email/Teams alerts for unauthorized changes
5. **Build audit reports:** CIP-010 compliance evidence packages

---

*Document Version: 1.0*
*For Claude Code Implementation*
