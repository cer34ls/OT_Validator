"""
OT Change Validation Tool - Configuration Settings
"""

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
    "time_buffer_hours": 24,          # +/- 24 hour window for time correlation
}

# Dashboard
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", 8501))

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
