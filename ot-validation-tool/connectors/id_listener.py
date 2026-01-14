"""
Industrial Defender Alert Listener.
Receives baseline change alerts via email (IMAP) or syslog.
"""

import imaplib
import email
from email.header import decode_header
import re
import socketserver
import threading
from queue import Queue
from datetime import datetime
from typing import List, Dict, Optional, Any
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class IDEmailListener:
    """
    Listens for Industrial Defender alert emails via IMAP.
    Parses email content to extract alert details.
    """
    
    # Patterns to extract alert data from email body
    # Adjust these based on your actual ID email format
    PATTERNS = {
        'alert_id': r'(?:Alert ID|Reference|ID)[:\s]*([A-Z0-9-]+)',
        'asset_name': r'(?:Asset|Host|System|Device)[:\s]*([^\n\r]+)',
        'change_category': r'(?:Category|Type|Change Type)[:\s]*([^\n\r]+)',
        'change_detail': r'(?:Change|Detail|Description|Event)[:\s]*([^\n\r]+)',
        'detected_at': r'(?:Detected|Time|Timestamp|Date)[:\s]*([^\n\r]+)',
        'severity': r'(?:Severity|Priority|Level)[:\s]*(\d+|Low|Medium|High|Critical)',
    }
    
    # Severity mapping
    SEVERITY_MAP = {
        'low': 1, 'info': 1, 'informational': 1,
        'medium': 3, 'warning': 3,
        'high': 4,
        'critical': 5, 'emergency': 5
    }
    
    def __init__(self, imap_server: str = None, username: str = None, 
                 password: str = None, folder: str = 'INBOX'):
        """Initialize with IMAP credentials from environment or parameters."""
        self.imap_server = imap_server or os.getenv('IMAP_SERVER')
        self.username = username or os.getenv('IMAP_USERNAME')
        self.password = password or os.getenv('IMAP_PASSWORD')
        self.folder = folder
        
        if not all([self.imap_server, self.username, self.password]):
            raise ValueError("Missing IMAP credentials")
    
    def fetch_unread_alerts(self) -> List[Dict]:
        """
        Fetch unread ID alert emails and parse them.
        
        Returns:
            List of parsed alert dictionaries
        """
        alerts = []
        
        try:
            with imaplib.IMAP4_SSL(self.imap_server) as mail:
                mail.login(self.username, self.password)
                mail.select(self.folder)
                
                # Search for unread emails from Industrial Defender
                # Adjust the FROM filter based on your ID email sender
                search_criteria = [
                    '(UNSEEN)',
                    '(OR FROM "industrialdefender" FROM "id-alerts" FROM "baseline")'
                ]
                
                for criteria in search_criteria:
                    try:
                        _, messages = mail.search(None, criteria)
                        if messages[0]:
                            break
                    except:
                        continue
                
                if not messages[0]:
                    logger.debug("No unread ID alerts found")
                    return alerts
                
                for msg_num in messages[0].split():
                    try:
                        _, msg_data = mail.fetch(msg_num, '(RFC822)')
                        msg = email.message_from_bytes(msg_data[0][1])
                        
                        alert = self._parse_alert_email(msg)
                        if alert:
                            alerts.append(alert)
                            # Mark as read
                            mail.store(msg_num, '+FLAGS', '\\Seen')
                            logger.info(f"Parsed alert for {alert.get('asset_name')}")
                    except Exception as e:
                        logger.error(f"Error parsing email {msg_num}: {e}")
                        continue
                
        except imaplib.IMAP4.error as e:
            logger.error(f"IMAP error: {e}")
            raise
        except Exception as e:
            logger.error(f"Error fetching emails: {e}")
            raise
        
        return alerts
    
    def _parse_alert_email(self, msg) -> Optional[Dict]:
        """
        Extract alert details from email message.
        
        Args:
            msg: email.message.Message object
            
        Returns:
            Parsed alert dictionary or None if parsing fails
        """
        # Get email body
        body = self._get_email_body(msg)
        if not body:
            return None
        
        # Get subject for additional context
        subject = self._decode_header(msg.get('Subject', ''))
        
        # Parse fields from body
        result = {
            'source_type': 'email',
            'raw_email': body[:5000],  # Truncate to avoid huge storage
            'email_subject': subject,
            'email_from': msg.get('From', ''),
            'email_date': msg.get('Date', '')
        }
        
        # Extract fields using patterns
        for field, pattern in self.PATTERNS.items():
            match = re.search(pattern, body, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                
                # Special handling for severity
                if field == 'severity':
                    result[field] = self._parse_severity(value)
                elif field == 'detected_at':
                    result[field] = self._parse_datetime(value)
                else:
                    result[field] = value
        
        # Try to extract from subject if not found in body
        if not result.get('asset_name'):
            # Common subject format: "Baseline Alert: SERVER01 - Software Change"
            subject_match = re.search(r'(?:Alert|Change)[:\s]*([A-Za-z0-9_-]+)', subject)
            if subject_match:
                result['asset_name'] = subject_match.group(1)
        
        # Generate alert ID if not found
        if not result.get('alert_id'):
            result['alert_id'] = f"EMAIL-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        # Use email date if detected_at not found
        if not result.get('detected_at') and result.get('email_date'):
            result['detected_at'] = self._parse_datetime(result['email_date'])
        
        # Default to now if still no timestamp
        if not result.get('detected_at'):
            result['detected_at'] = datetime.now().isoformat()
        
        # Normalize asset name
        if result.get('asset_name'):
            result['asset_name_normalized'] = self._normalize_asset_name(result['asset_name'])
        
        # Validate we have minimum required fields
        if result.get('asset_name'):
            return result
        
        logger.warning("Could not parse asset name from email")
        return None
    
    def _get_email_body(self, msg) -> str:
        """Extract text body from email message."""
        body = ""
        
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == 'text/plain':
                    payload = part.get_payload(decode=True)
                    if payload:
                        body = payload.decode('utf-8', errors='ignore')
                        break
                elif content_type == 'text/html' and not body:
                    payload = part.get_payload(decode=True)
                    if payload:
                        # Strip HTML tags for basic parsing
                        html = payload.decode('utf-8', errors='ignore')
                        body = re.sub(r'<[^>]+>', ' ', html)
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                body = payload.decode('utf-8', errors='ignore')
        
        return body
    
    def _decode_header(self, header) -> str:
        """Decode email header value."""
        if not header:
            return ""
        
        decoded_parts = decode_header(header)
        result = []
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                result.append(part.decode(encoding or 'utf-8', errors='ignore'))
            else:
                result.append(str(part))
        return ' '.join(result)
    
    def _parse_severity(self, value: str) -> int:
        """Parse severity value to integer."""
        if value.isdigit():
            return min(5, max(1, int(value)))
        return self.SEVERITY_MAP.get(value.lower(), 3)
    
    def _parse_datetime(self, value: str) -> Optional[str]:
        """Parse datetime string to ISO format."""
        formats = [
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%d',
            '%m/%d/%Y %H:%M:%S',
            '%m/%d/%Y %I:%M:%S %p',
            '%d %b %Y %H:%M:%S',
            '%a, %d %b %Y %H:%M:%S %z',
            '%a, %d %b %Y %H:%M:%S'
        ]
        
        for fmt in formats:
            try:
                dt = datetime.strptime(value.strip(), fmt)
                return dt.isoformat()
            except ValueError:
                continue
        
        return value  # Return as-is if parsing fails
    
    def _normalize_asset_name(self, name: str) -> str:
        """Normalize asset name for matching."""
        if not name:
            return ''
        
        normalized = name.lower().strip()
        normalized = re.sub(r'\.(local|internal|corp|domain)$', '', normalized)
        normalized = re.sub(r'^(srv|wks|vm|host)[-_]', '', normalized)
        
        return normalized


class SyslogHandler(socketserver.BaseRequestHandler):
    """Handler for syslog messages from Industrial Defender."""
    
    alert_queue = Queue()
    
    def handle(self):
        """Process incoming syslog message."""
        try:
            data = self.request[0].strip().decode('utf-8', errors='ignore')
            alert = self._parse_syslog_message(data)
            if alert:
                SyslogHandler.alert_queue.put(alert)
                logger.debug(f"Received syslog alert: {alert.get('asset_name')}")
        except Exception as e:
            logger.error(f"Error handling syslog message: {e}")
    
    def _parse_syslog_message(self, message: str) -> Optional[Dict]:
        """Parse syslog message to extract alert data."""
        # Check for CEF format
        if 'CEF:' in message:
            return self._parse_cef(message)
        
        # Try custom format parsing
        return self._parse_custom(message)
    
    def _parse_cef(self, message: str) -> Optional[Dict]:
        """
        Parse CEF (Common Event Format) message.
        Format: CEF:Version|Device Vendor|Device Product|Device Version|Signature ID|Name|Severity|Extension
        """
        try:
            # Extract CEF part
            cef_match = re.search(r'CEF:(\d+)\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|(\d+)\|(.*)', message)
            if not cef_match:
                return None
            
            version, vendor, product, dev_version, sig_id, name, severity, extension = cef_match.groups()
            
            # Parse extension key=value pairs
            ext_data = {}
            for match in re.finditer(r'(\w+)=([^\s]+(?:\s+(?!\w+=)[^\s]+)*)', extension):
                ext_data[match.group(1)] = match.group(2)
            
            return {
                'alert_id': sig_id,
                'asset_name': ext_data.get('dhost', ext_data.get('dst', '')),
                'asset_name_normalized': ext_data.get('dhost', ext_data.get('dst', '')).lower(),
                'change_category': name,
                'change_detail': ext_data.get('msg', ext_data.get('cs1', '')),
                'detected_at': datetime.now().isoformat(),
                'severity': int(severity),
                'source_type': 'syslog_cef',
                'raw_email': message[:2000]
            }
        except Exception as e:
            logger.error(f"Error parsing CEF: {e}")
            return None
    
    def _parse_custom(self, message: str) -> Optional[Dict]:
        """Parse custom syslog format."""
        # Generic parsing - adjust based on your ID syslog format
        result = {
            'source_type': 'syslog',
            'raw_email': message[:2000],
            'detected_at': datetime.now().isoformat(),
            'severity': 3
        }
        
        # Try to extract asset name (common patterns)
        patterns = [
            r'host[=:\s]+([A-Za-z0-9_.-]+)',
            r'asset[=:\s]+([A-Za-z0-9_.-]+)',
            r'src[=:\s]+([A-Za-z0-9_.-]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                result['asset_name'] = match.group(1)
                result['asset_name_normalized'] = match.group(1).lower()
                break
        
        if not result.get('asset_name'):
            return None
        
        result['alert_id'] = f"SYSLOG-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        
        return result


class IDSyslogReceiver:
    """UDP Syslog receiver for Industrial Defender alerts."""
    
    def __init__(self, host: str = '0.0.0.0', port: int = None):
        """Initialize syslog receiver."""
        self.host = host
        self.port = port or int(os.getenv('SYSLOG_PORT', 10514))
        self.server = None
        self.thread = None
    
    def start(self):
        """Start the syslog receiver in a background thread."""
        self.server = socketserver.UDPServer((self.host, self.port), SyslogHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        logger.info(f"Syslog receiver started on {self.host}:{self.port}")
    
    def stop(self):
        """Stop the syslog receiver."""
        if self.server:
            self.server.shutdown()
            logger.info("Syslog receiver stopped")
    
    def get_pending_alerts(self) -> List[Dict]:
        """Get all pending alerts from the queue."""
        alerts = []
        while not SyslogHandler.alert_queue.empty():
            try:
                alerts.append(SyslogHandler.alert_queue.get_nowait())
            except:
                break
        return alerts


class IDAlertProcessor:
    """Processes ID alerts from all sources and stores in database."""
    
    def __init__(self, database, correlator=None):
        self.db = database
        self.correlator = correlator
        self.email_listener = None
        self.syslog_receiver = None
    
    def setup_email_listener(self):
        """Initialize email listener if credentials are available."""
        try:
            self.email_listener = IDEmailListener()
            logger.info("Email listener initialized")
        except ValueError as e:
            logger.warning(f"Email listener not available: {e}")
    
    def setup_syslog_receiver(self):
        """Initialize and start syslog receiver."""
        self.syslog_receiver = IDSyslogReceiver()
        self.syslog_receiver.start()
    
    def process_all_sources(self) -> Dict[str, int]:
        """
        Process alerts from all configured sources.
        
        Returns:
            Dictionary with counts per source
        """
        results = {'email': 0, 'syslog': 0, 'total': 0}
        
        # Process email alerts
        if self.email_listener:
            try:
                alerts = self.email_listener.fetch_unread_alerts()
                for alert in alerts:
                    self._process_alert(alert)
                    results['email'] += 1
            except Exception as e:
                logger.error(f"Error processing email alerts: {e}")
        
        # Process syslog alerts
        if self.syslog_receiver:
            alerts = self.syslog_receiver.get_pending_alerts()
            for alert in alerts:
                self._process_alert(alert)
                results['syslog'] += 1
        
        results['total'] = results['email'] + results['syslog']
        
        if results['total'] > 0:
            logger.info(f"Processed {results['total']} alerts ({results['email']} email, {results['syslog']} syslog)")
        
        return results
    
    def _process_alert(self, alert: Dict):
        """Process a single alert: store and correlate."""
        # Insert alert into database
        alert_id = self.db.insert_alert(alert)
        
        # Correlate with changes if correlator available
        if self.correlator:
            self.correlator.correlate_and_validate(alert_id, alert)


if __name__ == '__main__':
    # Test email listener
    from dotenv import load_dotenv
    load_dotenv()
    
    try:
        listener = IDEmailListener()
        alerts = listener.fetch_unread_alerts()
        print(f"Found {len(alerts)} unread alerts")
        for alert in alerts:
            print(f"  - {alert.get('asset_name')}: {alert.get('change_category')}")
    except ValueError as e:
        print(f"Email listener not configured: {e}")
