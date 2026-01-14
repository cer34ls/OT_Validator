"""
Correlation Engine for OT Change Validation Tool.
Matches Industrial Defender alerts against approved change records.
"""

from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple, Any
from difflib import SequenceMatcher
from datetime import datetime, timedelta
import re
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class CorrelationResult:
    """Result of correlating an alert with a change."""
    change_id: int
    ticket_id: str
    score: float
    factors: Dict[str, float]
    is_auto_validated: bool
    validation_rule: Optional[str] = None


class CorrelationEngine:
    """
    Correlates ID alerts with approved changes from multiple sources.
    
    Uses weighted scoring based on:
    - Asset name similarity (40%)
    - Time window match (30%)
    - Change type match (20%)
    - KB article match (10%)
    """
    
    # Correlation factor weights
    WEIGHTS = {
        'asset': 0.40,
        'time': 0.30,
        'type': 0.20,
        'kb': 0.10
    }
    
    # Thresholds
    AUTO_VALIDATE_THRESHOLD = 0.95  # Auto-validate if score >= 95%
    MINIMUM_MATCH_THRESHOLD = 0.50  # Don't consider matches below 50%
    TIME_BUFFER_HOURS = 24  # Allow changes within ±24 hours of window
    
    # Change type mappings (ID category -> ticket change types)
    CHANGE_TYPE_MAPPINGS = {
        'software': ['patch', 'software', 'install', 'update'],
        'service': ['config', 'software', 'service'],
        'user': ['user', 'access', 'account'],
        'config': ['config', 'setting', 'parameter'],
        'file': ['config', 'software', 'patch'],
        'registry': ['config', 'software'],
        'firewall': ['config', 'network', 'firewall'],
        'patch': ['patch', 'update', 'hotfix']
    }
    
    def __init__(self, database):
        """Initialize with database connection."""
        self.db = database
    
    def correlate(self, alert: Dict[str, Any]) -> Optional[CorrelationResult]:
        """
        Find the best matching change for an alert.
        
        Args:
            alert: Alert dictionary with asset_name, change_category, 
                   change_detail, detected_at
        
        Returns:
            CorrelationResult if match found above threshold, else None
        """
        # Get candidate changes within expanded time window
        candidates = self._get_candidate_changes(alert)
        
        if not candidates:
            logger.debug(f"No candidate changes found for alert on {alert.get('asset_name')}")
            return None
        
        best_match = None
        best_score = 0
        
        for change in candidates:
            score, factors = self._calculate_score(alert, change)
            
            if score > best_score and score >= self.MINIMUM_MATCH_THRESHOLD:
                best_score = score
                best_match = CorrelationResult(
                    change_id=change['id'],
                    ticket_id=change['ticket_id'],
                    score=score,
                    factors=factors,
                    is_auto_validated=score >= self.AUTO_VALIDATE_THRESHOLD,
                    validation_rule=self._get_validation_rule(score, factors, change)
                )
        
        if best_match:
            logger.info(
                f"Correlated alert on {alert.get('asset_name')} with "
                f"{best_match.ticket_id} (score: {best_match.score:.2%})"
            )
        
        return best_match
    
    def correlate_and_validate(self, alert_id: int, alert: Dict[str, Any]) -> Dict[str, Any]:
        """
        Correlate an alert and create validation record.
        
        Returns:
            Dictionary with correlation results and validation status
        """
        result = self.correlate(alert)
        
        if result:
            # Create validation record
            validation = {
                'alert_id': alert_id,
                'change_id': result.change_id,
                'correlation_score': result.score,
                'correlation_factors': result.factors,
                'validation_status': 'auto_validated' if result.is_auto_validated else 'pending_review',
                'validated_by': 'SYSTEM' if result.is_auto_validated else None,
                'validated_at': datetime.now().isoformat() if result.is_auto_validated else None,
                'auto_validation_rule': result.validation_rule
            }
            
            self.db.create_validation(validation)
            
            # Update alert status
            if result.is_auto_validated:
                self.db.update_alert_status(alert_id, 'validated', 'SYSTEM')
            
            return {
                'matched': True,
                'ticket_id': result.ticket_id,
                'score': result.score,
                'auto_validated': result.is_auto_validated,
                'factors': result.factors
            }
        else:
            # No match - flag for review
            validation = {
                'alert_id': alert_id,
                'change_id': None,
                'correlation_score': 0,
                'correlation_factors': {},
                'validation_status': 'pending_review',
                'validated_by': None,
                'validated_at': None,
                'notes': 'No matching change ticket found'
            }
            
            self.db.create_validation(validation)
            
            return {
                'matched': False,
                'ticket_id': None,
                'score': 0,
                'auto_validated': False,
                'factors': {}
            }
    
    def _get_candidate_changes(self, alert: Dict[str, Any]) -> List[Dict]:
        """Get potential matching changes from database."""
        detected_at = alert.get('detected_at')
        
        if isinstance(detected_at, str):
            try:
                detected_at = datetime.fromisoformat(detected_at.replace('Z', '+00:00'))
            except ValueError:
                detected_at = datetime.now()
        elif not isinstance(detected_at, datetime):
            detected_at = datetime.now()
        
        # Expand time window for search
        search_start = detected_at - timedelta(hours=self.TIME_BUFFER_HOURS * 2)
        search_end = detected_at + timedelta(hours=self.TIME_BUFFER_HOURS)
        
        # Get changes in window, optionally filtered by asset
        asset_name = alert.get('asset_name_normalized', '')
        
        return self.db.get_changes_in_window(
            start=search_start,
            end=search_end,
            asset_name=asset_name[:3] if asset_name else None  # Partial match
        )
    
    def _calculate_score(self, alert: Dict, change: Dict) -> Tuple[float, Dict[str, float]]:
        """
        Calculate correlation score between alert and change.
        
        Returns:
            Tuple of (total_score, factor_scores)
        """
        factors = {}
        
        # 1. Asset name similarity (40%)
        factors['asset'] = self._asset_similarity(
            alert.get('asset_name_normalized', ''),
            change.get('asset_name_normalized', '')
        )
        
        # 2. Time window match (30%)
        factors['time'] = self._time_score(
            alert.get('detected_at'),
            change.get('scheduled_start'),
            change.get('scheduled_end')
        )
        
        # 3. Change type match (20%)
        factors['type'] = self._type_match(
            alert.get('change_category'),
            change.get('change_type')
        )
        
        # 4. KB article match (10%)
        factors['kb'] = self._kb_match(
            alert.get('change_detail', ''),
            change.get('kb_articles', '[]')
        )
        
        # Calculate weighted sum
        total = sum(factors[k] * self.WEIGHTS[k] for k in factors)
        
        return total, factors
    
    def _asset_similarity(self, alert_asset: str, change_asset: str) -> float:
        """
        Calculate similarity between asset names.
        Uses sequence matching for fuzzy comparison.
        """
        if not alert_asset or not change_asset:
            return 0.0
        
        # Exact match
        if alert_asset == change_asset:
            return 1.0
        
        # Check if one contains the other
        if alert_asset in change_asset or change_asset in alert_asset:
            return 0.9
        
        # Fuzzy match using sequence matcher
        ratio = SequenceMatcher(None, alert_asset, change_asset).ratio()
        
        # Also check individual tokens
        alert_tokens = set(alert_asset.replace('-', ' ').replace('_', ' ').split())
        change_tokens = set(change_asset.replace('-', ' ').replace('_', ' ').split())
        
        if alert_tokens and change_tokens:
            token_overlap = len(alert_tokens & change_tokens) / len(alert_tokens | change_tokens)
            # Use the better of the two scores
            ratio = max(ratio, token_overlap)
        
        return ratio
    
    def _time_score(self, detected_at: Any, 
                    scheduled_start: Any, 
                    scheduled_end: Any) -> float:
        """
        Score based on whether detection falls within change window.
        """
        # Parse dates
        def parse_dt(dt):
            if isinstance(dt, datetime):
                return dt
            if isinstance(dt, str):
                try:
                    return datetime.fromisoformat(dt.replace('Z', '+00:00'))
                except ValueError:
                    return None
            return None
        
        detected = parse_dt(detected_at)
        start = parse_dt(scheduled_start)
        end = parse_dt(scheduled_end)
        
        if not detected or not start:
            return 0.0
        
        # If no end time, assume 24-hour window
        if not end:
            end = start + timedelta(hours=24)
        
        # Expand window by buffer
        buffer = timedelta(hours=self.TIME_BUFFER_HOURS)
        window_start = start - buffer
        window_end = end + buffer
        
        # Perfect score if within original window
        if start <= detected <= end:
            return 1.0
        
        # Partial score if within buffer zone
        if window_start <= detected <= window_end:
            # Calculate how far outside the core window
            if detected < start:
                hours_outside = (start - detected).total_seconds() / 3600
            else:
                hours_outside = (detected - end).total_seconds() / 3600
            
            # Linear decay based on hours outside
            return max(0, 1 - (hours_outside / self.TIME_BUFFER_HOURS) * 0.5)
        
        return 0.0
    
    def _type_match(self, alert_category: str, change_type: str) -> float:
        """
        Score based on whether change types align.
        """
        if not alert_category or not change_type:
            return 0.5  # Neutral score if type unknown
        
        alert_cat = alert_category.lower()
        change_t = change_type.lower()
        
        # Direct match
        if alert_cat == change_t:
            return 1.0
        
        # Check mapping
        expected_types = self.CHANGE_TYPE_MAPPINGS.get(alert_cat, [])
        if change_t in expected_types:
            return 1.0
        
        # Partial match - any word overlap
        alert_words = set(alert_cat.split())
        change_words = set(change_t.split())
        if alert_words & change_words:
            return 0.7
        
        return 0.3  # Low score for type mismatch
    
    def _kb_match(self, alert_detail: str, kb_articles_json: str) -> float:
        """
        Score based on KB article match.
        """
        if not alert_detail:
            return 0.5  # Neutral if no detail
        
        # Extract KB from alert detail
        kb_pattern = r'KB[- ]?(\d{6,7})'
        alert_kbs = set(re.findall(kb_pattern, alert_detail, re.IGNORECASE))
        
        if not alert_kbs:
            return 0.5  # Neutral if no KB in alert
        
        # Parse KB articles from change
        try:
            change_kbs = set(json.loads(kb_articles_json))
        except (json.JSONDecodeError, TypeError):
            change_kbs = set()
        
        # Normalize change KBs
        change_kbs = {re.sub(r'^KB[- ]?', '', kb) for kb in change_kbs}
        
        if not change_kbs:
            # Check if KB is in WSUS approved list
            for kb in alert_kbs:
                if self.db.is_kb_approved(f'KB{kb}'):
                    return 1.0
            return 0.5
        
        # Check for overlap
        if alert_kbs & change_kbs:
            return 1.0
        
        return 0.3  # KB mentioned but doesn't match
    
    def _get_validation_rule(self, score: float, factors: Dict[str, float], 
                            change: Dict) -> Optional[str]:
        """Determine which auto-validation rule applied."""
        if score < self.AUTO_VALIDATE_THRESHOLD:
            return None
        
        rules = []
        
        if factors['asset'] >= 0.95:
            rules.append('exact_asset_match')
        
        if factors['time'] >= 1.0:
            rules.append('within_change_window')
        
        if factors['kb'] >= 1.0:
            rules.append('kb_article_match')
        
        if change.get('approval_status') == 'approved':
            rules.append('ticket_approved')
        
        return '+'.join(rules) if rules else 'high_confidence_match'


class WSUSAutoValidator:
    """
    Special validator for WSUS patch installations.
    Auto-validates if KB is in approved WSUS list.
    """
    
    def __init__(self, database):
        self.db = database
    
    def check_wsus_approval(self, alert: Dict[str, Any]) -> Optional[Dict]:
        """
        Check if alert refers to a WSUS-approved patch.
        
        Returns:
            Validation result if WSUS-approved, else None
        """
        detail = alert.get('change_detail', '')
        
        # Extract KB number
        kb_match = re.search(r'KB[- ]?(\d{6,7})', detail, re.IGNORECASE)
        if not kb_match:
            return None
        
        kb_number = f'KB{kb_match.group(1)}'
        
        # Check WSUS approval
        if self.db.is_kb_approved(kb_number):
            return {
                'auto_validated': True,
                'validation_rule': 'wsus_approved_patch',
                'kb_number': kb_number,
                'notes': f'Patch {kb_number} is in WSUS approved list'
            }
        
        return None


if __name__ == '__main__':
    # Test correlation
    print("Correlation Engine loaded successfully")
    print(f"Auto-validate threshold: {CorrelationEngine.AUTO_VALIDATE_THRESHOLD:.0%}")
    print(f"Time buffer: ±{CorrelationEngine.TIME_BUFFER_HOURS} hours")
