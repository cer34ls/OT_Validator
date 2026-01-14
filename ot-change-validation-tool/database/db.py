"""
Database module for OT Change Validation Tool.
Uses SQLite with FTS5 for full-text search.
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any
from contextlib import contextmanager
import os

class Database:
    """SQLite database abstraction layer."""
    
    SCHEMA = """
    -- Enable WAL mode for better concurrency
    PRAGMA journal_mode=WAL;
    PRAGMA foreign_keys=ON;
    
    -- Changes table: All change requests from all sources
    CREATE TABLE IF NOT EXISTS changes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source TEXT NOT NULL CHECK(source IN ('servicenow','mantis','wsus','manual','kb')),
        ticket_id TEXT NOT NULL,
        asset_name TEXT,
        asset_name_normalized TEXT,
        change_type TEXT,
        description TEXT,
        scheduled_start DATETIME,
        scheduled_end DATETIME,
        approval_status TEXT DEFAULT 'pending',
        approved_by TEXT,
        kb_articles TEXT,
        raw_data TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        deleted_at DATETIME,
        UNIQUE(source, ticket_id)
    );
    
    -- Alerts table: Industrial Defender baseline change alerts
    CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        alert_id TEXT UNIQUE,
        asset_name TEXT NOT NULL,
        asset_name_normalized TEXT,
        change_category TEXT,
        change_detail TEXT,
        detected_at DATETIME NOT NULL,
        severity INTEGER DEFAULT 3,
        validation_status TEXT DEFAULT 'pending' 
            CHECK(validation_status IN ('pending','validated','unauthorized','investigating')),
        source_type TEXT,
        raw_email TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    
    -- Validations table: Correlation results and validation decisions
    CREATE TABLE IF NOT EXISTS validations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        alert_id INTEGER NOT NULL REFERENCES alerts(id),
        change_id INTEGER REFERENCES changes(id),
        correlation_score REAL,
        correlation_factors TEXT,
        validation_status TEXT NOT NULL 
            CHECK(validation_status IN ('auto_validated','manual_validated','unauthorized','pending_review')),
        validated_by TEXT,
        validated_at DATETIME,
        notes TEXT,
        evidence_links TEXT,
        auto_validation_rule TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    
    -- Assets table: Asset name mapping and normalization
    CREATE TABLE IF NOT EXISTS assets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        canonical_name TEXT UNIQUE NOT NULL,
        aliases TEXT,
        asset_type TEXT,
        environment TEXT,
        criticality TEXT DEFAULT 'medium',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    
    -- WSUS Patches table: Approved patches from WSUS exports
    CREATE TABLE IF NOT EXISTS wsus_patches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kb_number TEXT UNIQUE NOT NULL,
        title TEXT,
        classification TEXT,
        approval_date DATETIME,
        approved_for_groups TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    
    -- Sync Status table: Track data source synchronization
    CREATE TABLE IF NOT EXISTS sync_status (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_name TEXT UNIQUE NOT NULL,
        last_sync DATETIME,
        records_synced INTEGER,
        status TEXT,
        error_message TEXT,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    
    -- Audit Log table: Complete audit trail for compliance
    CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        action TEXT NOT NULL,
        table_name TEXT,
        record_id INTEGER,
        user TEXT NOT NULL,
        old_value TEXT,
        new_value TEXT,
        ip_address TEXT,
        details TEXT
    );
    
    -- Indexes for performance
    CREATE INDEX IF NOT EXISTS idx_changes_ticket ON changes(ticket_id);
    CREATE INDEX IF NOT EXISTS idx_changes_asset ON changes(asset_name_normalized);
    CREATE INDEX IF NOT EXISTS idx_changes_source ON changes(source);
    CREATE INDEX IF NOT EXISTS idx_changes_dates ON changes(scheduled_start, scheduled_end);
    CREATE INDEX IF NOT EXISTS idx_alerts_asset ON alerts(asset_name_normalized);
    CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(validation_status);
    CREATE INDEX IF NOT EXISTS idx_alerts_detected ON alerts(detected_at);
    CREATE INDEX IF NOT EXISTS idx_wsus_kb ON wsus_patches(kb_number);
    CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp);
    
    -- FTS5 virtual table for full-text search on descriptions
    CREATE VIRTUAL TABLE IF NOT EXISTS changes_fts USING fts5(
        ticket_id, 
        asset_name, 
        description, 
        content='changes', 
        content_rowid='id'
    );
    
    -- Triggers to keep FTS in sync
    CREATE TRIGGER IF NOT EXISTS changes_ai AFTER INSERT ON changes BEGIN
        INSERT INTO changes_fts(rowid, ticket_id, asset_name, description) 
        VALUES (new.id, new.ticket_id, new.asset_name, new.description);
    END;
    
    CREATE TRIGGER IF NOT EXISTS changes_ad AFTER DELETE ON changes BEGIN
        INSERT INTO changes_fts(changes_fts, rowid, ticket_id, asset_name, description) 
        VALUES('delete', old.id, old.ticket_id, old.asset_name, old.description);
    END;
    
    CREATE TRIGGER IF NOT EXISTS changes_au AFTER UPDATE ON changes BEGIN
        INSERT INTO changes_fts(changes_fts, rowid, ticket_id, asset_name, description) 
        VALUES('delete', old.id, old.ticket_id, old.asset_name, old.description);
        INSERT INTO changes_fts(rowid, ticket_id, asset_name, description) 
        VALUES (new.id, new.ticket_id, new.asset_name, new.description);
    END;
    """
    
    def __init__(self, db_path: str = None):
        """Initialize database connection."""
        self.db_path = db_path or os.getenv('DATABASE_PATH', 'validation_tool.db')
        self._ensure_db_dir()
        
    def _ensure_db_dir(self):
        """Ensure database directory exists."""
        db_dir = Path(self.db_path).parent
        if db_dir and not db_dir.exists():
            db_dir.mkdir(parents=True, exist_ok=True)
    
    @contextmanager
    def connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def init(self):
        """Initialize database schema."""
        with self.connection() as conn:
            conn.executescript(self.SCHEMA)
        print(f"Database initialized: {self.db_path}")
    
    # ==================== CHANGES ====================
    
    def upsert_change(self, change: Dict[str, Any]) -> int:
        """Insert or update a change record."""
        with self.connection() as conn:
            cursor = conn.execute("""
                INSERT INTO changes (
                    source, ticket_id, asset_name, asset_name_normalized,
                    change_type, description, scheduled_start, scheduled_end,
                    approval_status, approved_by, kb_articles, raw_data, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(source, ticket_id) DO UPDATE SET
                    asset_name = excluded.asset_name,
                    asset_name_normalized = excluded.asset_name_normalized,
                    change_type = excluded.change_type,
                    description = excluded.description,
                    scheduled_start = excluded.scheduled_start,
                    scheduled_end = excluded.scheduled_end,
                    approval_status = excluded.approval_status,
                    approved_by = excluded.approved_by,
                    kb_articles = excluded.kb_articles,
                    raw_data = excluded.raw_data,
                    updated_at = CURRENT_TIMESTAMP
            """, (
                change.get('source'),
                change.get('ticket_id'),
                change.get('asset_name'),
                change.get('asset_name_normalized'),
                change.get('change_type'),
                change.get('description'),
                change.get('scheduled_start'),
                change.get('scheduled_end'),
                change.get('approval_status', 'pending'),
                change.get('approved_by'),
                json.dumps(change.get('kb_articles', [])),
                json.dumps(change.get('raw_data', {}))
            ))
            return cursor.lastrowid
    
    def get_changes_in_window(self, start: datetime, end: datetime, 
                              asset_name: str = None) -> List[Dict]:
        """Get changes within a time window, optionally filtered by asset."""
        with self.connection() as conn:
            if asset_name:
                cursor = conn.execute("""
                    SELECT * FROM changes 
                    WHERE deleted_at IS NULL
                    AND scheduled_start <= ? AND scheduled_end >= ?
                    AND asset_name_normalized LIKE ?
                    ORDER BY scheduled_start DESC
                """, (end, start, f'%{asset_name}%'))
            else:
                cursor = conn.execute("""
                    SELECT * FROM changes 
                    WHERE deleted_at IS NULL
                    AND scheduled_start <= ? AND scheduled_end >= ?
                    ORDER BY scheduled_start DESC
                """, (end, start))
            return [dict(row) for row in cursor.fetchall()]
    
    def search_changes(self, query: str, limit: int = 50) -> List[Dict]:
        """Full-text search on changes."""
        with self.connection() as conn:
            cursor = conn.execute("""
                SELECT c.* FROM changes c
                JOIN changes_fts fts ON c.id = fts.rowid
                WHERE changes_fts MATCH ? AND c.deleted_at IS NULL
                ORDER BY rank
                LIMIT ?
            """, (query, limit))
            return [dict(row) for row in cursor.fetchall()]
    
    # ==================== ALERTS ====================
    
    def insert_alert(self, alert: Dict[str, Any]) -> int:
        """Insert a new alert."""
        with self.connection() as conn:
            cursor = conn.execute("""
                INSERT INTO alerts (
                    alert_id, asset_name, asset_name_normalized,
                    change_category, change_detail, detected_at,
                    severity, validation_status, source_type, raw_email
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
            """, (
                alert.get('alert_id'),
                alert.get('asset_name'),
                alert.get('asset_name_normalized'),
                alert.get('change_category'),
                alert.get('change_detail'),
                alert.get('detected_at'),
                alert.get('severity', 3),
                alert.get('source_type'),
                alert.get('raw_email')
            ))
            return cursor.lastrowid
    
    def get_pending_alerts(self, limit: int = 100) -> List[Dict]:
        """Get alerts pending validation."""
        with self.connection() as conn:
            cursor = conn.execute("""
                SELECT a.*, v.correlation_score, v.change_id,
                       c.ticket_id as matched_ticket
                FROM alerts a
                LEFT JOIN validations v ON a.id = v.alert_id
                LEFT JOIN changes c ON v.change_id = c.id
                WHERE a.validation_status = 'pending'
                ORDER BY a.severity DESC, a.detected_at ASC
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]
    
    def update_alert_status(self, alert_id: int, status: str, 
                           validated_by: str = 'SYSTEM') -> None:
        """Update alert validation status."""
        with self.connection() as conn:
            conn.execute("""
                UPDATE alerts 
                SET validation_status = ?
                WHERE id = ?
            """, (status, alert_id))
            
            # Log the action
            conn.execute("""
                INSERT INTO audit_log (action, table_name, record_id, user, new_value)
                VALUES ('update_status', 'alerts', ?, ?, ?)
            """, (alert_id, validated_by, status))
    
    # ==================== VALIDATIONS ====================
    
    def create_validation(self, validation: Dict[str, Any]) -> int:
        """Create a validation record."""
        with self.connection() as conn:
            cursor = conn.execute("""
                INSERT INTO validations (
                    alert_id, change_id, correlation_score, correlation_factors,
                    validation_status, validated_by, validated_at, notes,
                    evidence_links, auto_validation_rule
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                validation.get('alert_id'),
                validation.get('change_id'),
                validation.get('correlation_score'),
                json.dumps(validation.get('correlation_factors', {})),
                validation.get('validation_status'),
                validation.get('validated_by'),
                validation.get('validated_at'),
                validation.get('notes'),
                json.dumps(validation.get('evidence_links', [])),
                validation.get('auto_validation_rule')
            ))
            return cursor.lastrowid
    
    # ==================== WSUS PATCHES ====================
    
    def upsert_wsus_patch(self, patch: Dict[str, Any]) -> int:
        """Insert or update a WSUS patch record."""
        with self.connection() as conn:
            cursor = conn.execute("""
                INSERT INTO wsus_patches (
                    kb_number, title, classification, approval_date, approved_for_groups
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(kb_number) DO UPDATE SET
                    title = excluded.title,
                    classification = excluded.classification,
                    approval_date = excluded.approval_date,
                    approved_for_groups = excluded.approved_for_groups
            """, (
                patch.get('kb_number'),
                patch.get('title'),
                patch.get('classification'),
                patch.get('approval_date'),
                json.dumps(patch.get('approved_for_groups', []))
            ))
            return cursor.lastrowid
    
    def is_kb_approved(self, kb_number: str) -> bool:
        """Check if a KB article is in the approved WSUS list."""
        with self.connection() as conn:
            cursor = conn.execute(
                "SELECT 1 FROM wsus_patches WHERE kb_number = ?", 
                (kb_number,)
            )
            return cursor.fetchone() is not None
    
    # ==================== SYNC STATUS ====================
    
    def update_sync_status(self, source: str, records: int, 
                          status: str = 'success', error: str = None) -> None:
        """Update sync status for a data source."""
        with self.connection() as conn:
            conn.execute("""
                INSERT INTO sync_status (source_name, last_sync, records_synced, status, error_message, updated_at)
                VALUES (?, CURRENT_TIMESTAMP, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(source_name) DO UPDATE SET
                    last_sync = CURRENT_TIMESTAMP,
                    records_synced = excluded.records_synced,
                    status = excluded.status,
                    error_message = excluded.error_message,
                    updated_at = CURRENT_TIMESTAMP
            """, (source, records, status, error))
    
    def get_sync_status(self) -> List[Dict]:
        """Get sync status for all sources."""
        with self.connection() as conn:
            cursor = conn.execute("SELECT * FROM sync_status ORDER BY source_name")
            return [dict(row) for row in cursor.fetchall()]
    
    # ==================== AUDIT ====================
    
    def log_audit(self, action: str, table: str, record_id: int,
                  user: str, old_value: Any = None, new_value: Any = None,
                  ip_address: str = None, details: str = None) -> None:
        """Log an audit event."""
        with self.connection() as conn:
            conn.execute("""
                INSERT INTO audit_log (action, table_name, record_id, user, 
                                       old_value, new_value, ip_address, details)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                action, table, record_id, user,
                json.dumps(old_value) if old_value else None,
                json.dumps(new_value) if new_value else None,
                ip_address, details
            ))
    
    # ==================== METRICS ====================
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get dashboard metrics."""
        with self.connection() as conn:
            metrics = {}
            
            # Pending count
            cursor = conn.execute(
                "SELECT COUNT(*) FROM alerts WHERE validation_status = 'pending'"
            )
            metrics['pending_count'] = cursor.fetchone()[0]
            
            # Today's validations
            cursor = conn.execute("""
                SELECT COUNT(*) FROM validations 
                WHERE DATE(validated_at) = DATE('now')
            """)
            metrics['validated_today'] = cursor.fetchone()[0]
            
            # Auto-validated percentage (last 30 days)
            cursor = conn.execute("""
                SELECT 
                    COUNT(CASE WHEN validation_status = 'auto_validated' THEN 1 END) * 100.0 / 
                    NULLIF(COUNT(*), 0) as auto_rate
                FROM validations 
                WHERE validated_at >= DATE('now', '-30 days')
            """)
            result = cursor.fetchone()[0]
            metrics['auto_validation_rate'] = result if result else 0
            
            # Unauthorized count (last 30 days)
            cursor = conn.execute("""
                SELECT COUNT(*) FROM alerts 
                WHERE validation_status = 'unauthorized'
                AND detected_at >= DATE('now', '-30 days')
            """)
            metrics['unauthorized_count'] = cursor.fetchone()[0]
            
            return metrics


if __name__ == '__main__':
    # Initialize database when run directly
    db = Database()
    db.init()
    print("Database ready!")
