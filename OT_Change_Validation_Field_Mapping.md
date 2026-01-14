# OT Change Validation Tool - Technical Field Mapping Specification

## Document Purpose
This document provides exact field mappings between Industrial Defender (ID), ServiceNow, and the validation tool database based on actual production screenshots from PSEG Long Island environment.

---

## 1. INDUSTRIAL DEFENDER BULK EXCEPTIONS - FIELD REFERENCE

### 1.1 Common Fields (All Tabs)
| ID Field | Data Type | Example | Database Column | Notes |
|----------|-----------|---------|-----------------|-------|
| Type | Enum | New, Removed, Changed | `change_type` | Action performed |
| Asset Groups | String | Dragos, All_Linux, All_Windows | `asset_group` | Maps to WSUS groups |
| Assets | Integer | 1, 2 | `asset_count` | Number of affected assets |
| Comment | Text | "Activity from DSCADA Monthly Patching: CHG0000338290..." | `comment` | **CONTAINS CHG NUMBERS!** |
| Exception Detection Date | DateTime | 8/29/2025 11:47:47 AM | `detected_at` | Correlation timestamp |

### 1.2 Asset Details Tab
| ID Field | Example | Database Column |
|----------|---------|-----------------|
| Attribute Name | [Group]_chrony, [Group]_ssh, [Group] adm | `attribute_name` |
| Attribute Value | Group ID: 112, Group ID: 111 | `attribute_value` |

### 1.3 Software Installed Tab
| ID Field | Example | Database Column |
|----------|---------|-----------------|
| Software Name | adduser, amd64-microcode, apparmor | `software_name` |
| Software Version | 3.134, 3.20191021.1+really3.20181128.1~ubuntu0.18.0 | `software_version` |

### 1.4 Patches Installed Tab (HIGH VALUE)
| ID Field | Example | Database Column | Correlation Use |
|----------|---------|-----------------|-----------------|
| Patch ID | KB5062070, KB5063871, KB5065427, KB5066781 | `patch_id` | **Match to WSUS approved list** |
| Service Pack In Effect | (blank in examples) | `service_pack` | |
| Comment | "Activity from DSCADA Monthly Patching: CHG0000338290 CHG0000338289 CHG0000338288 CHG0000338287" | `comment` | **DIRECT CHG TICKET LINK** |

### 1.5 Ports And Services Tab
| ID Field | Example | Database Column |
|----------|---------|-----------------|
| Port | 8080, 18923, 15579, 9042, 323 | `port` |
| Protocol | TCP, UDP | `protocol` |
| IP Version | 4, 6 | `ip_version` |
| Interface | 0.0.0.0, 127.0.0.1, 10.80.74.206 | `interface` |
| Process | app, AppProvider, broker, cassandra, chronyd, containerd | `process_name` |
| Comment | "ephemeral port changes" | `comment` |

### 1.6 Firewall Rules Tab
| ID Field | Example | Database Column |
|----------|---------|-----------------|
| Policy ID | 103, 104, 105, 106, 1078, 1079, 1080 | `policy_id` |
| Type | Changed | `change_type` |
| Source IF | (configurable column) | `source_if` |
| Destination IF | (configurable column) | `dest_if` |
| Action | permit, ufw-u | `action` |
| Status | enabled, ENAB | `status` |
| Comment | "accept firewall rules changes to Windows HIDS baselines" | `comment` |

### 1.7 User Accounts Tab
| ID Field | Example | Database Column |
|----------|---------|-----------------|
| User ID | _apt, _chrony, 3pserv_act, Access Cont..., Administrator | `user_id` |
| User Type | Local User, Domain User, Local Group | `user_type` |
| Domain | bccdrbase01, DSCADA, BCCPRDCDP01, BCCPRDCDP02 | `domain` |
| Member of | nogroup, _chrony, Administrators | `member_of` |
| Enabled | True, False | `enabled` |

### 1.8 Device Interfaces Tab
| ID Field | Example | Database Column |
|----------|---------|-----------------|
| Interface Name | cni0, disabled, eno8303, flannel.1, Interface.1 | `interface_name` |
| IP Address | 10.42.0.1 | `ip_address` |
| Subnet Mask | 255.255.255.0 | `subnet_mask` |
| MAC Address | fa:fb:f0:fb:18:e5, b0:4f:13:b6:48:05 | `mac_address` |
| Comment | "Switch replacements" | `comment` |

---

## 2. SERVICENOW CHANGE REQUEST - FIELD REFERENCE

### 2.1 Header Fields
| ServiceNow Field | API Field | Example | Database Column | Required |
|------------------|-----------|---------|-----------------|----------|
| Number | `number` | CHG0000338771 | `ticket_id` | **YES** |
| Opened | `opened_at` | 01-13-2026 10:29 AM | `created_at` | YES |
| Opened by | `opened_by` | Ryan Collier | `opened_by` | |
| State | `state` | Closed Successful | `state` | YES |
| Approval Status | `approval` | Approved | `approval_status` | **YES** |
| Stage | `stage` | Approved | `stage` | |
| Assignment group | `assignment_group` | LI Cyber Security OT | `assignment_group` | Filter |
| Assigned to | `assigned_to` | Ryan Collier | `assigned_to` | |
| Configuration item | `cmdb_ci` | pccqasasm1 | `asset_name` | **YES** |

### 2.2 Classification Tab Fields
| ServiceNow Field | API Field | Example | Database Column |
|------------------|-----------|---------|-----------------|
| Short description | `short_description` | DSCADA QAS ID - Patch platform based on supports guidance | `description` |
| Category | `category` | Infrastructure SW | `category` |
| Subcategory | `subcategory` | Industrial Defender | `subcategory` |
| Activity | `u_activity` | Enhancement | `activity` |
| CI Filter Type | `ci_filter_type` | Category/Subcategory | |
| NERC CIP Options | `u_nerc_cip_options` | --None-- | `nerc_cip` |

### 2.3 Change Details Tab Fields
| ServiceNow Field | API Field | Example | Database Column |
|------------------|-----------|---------|-----------------|
| Environment | `u_environment` | QA | `environment` |
| Description | `description` | (Full patch list with URLs) | `full_description` |
| Implementation plan | `implementation_plan` | step 1 - contact support... | `implementation_plan` |
| Test plan | `test_plan` | Within the ID web portal... | `test_plan` |
| Backout plan | `backout_plan` | Rollback to a version of ID ASM... | `backout_plan` |

### 2.4 Schedule Tab Fields (CRITICAL FOR TIME CORRELATION)
| ServiceNow Field | API Field | Example | Database Column |
|------------------|-----------|---------|-----------------|
| Proposed Start Date/Time | `start_date` | 01-13-2026 02:00 PM | `scheduled_start` |
| Proposed End Date/Time | `end_date` | 01-14-2026 02:00 PM | `scheduled_end` |
| Implementation Start | `work_start` | 01-13-2026 02:00 PM | `actual_start` |
| Implementation End | `work_end` | 01-14-2026 02:00 PM | `actual_end` |

### 2.5 Approval Fields
| ServiceNow Field | API Field | Example | Database Column |
|------------------|-----------|---------|-----------------|
| Approver | `approver.name` | Anthony LaRosa | `approver` |
| Approval State | `approval_state` | Approved | `approval_state` |
| Assignment group | `approval_group` | Firewall Mgmt Approval PSEGLI | `approval_group` |

---

## 3. CORRELATION LOGIC - EXACT ALGORITHM

### 3.1 Primary Correlation Path (FASTEST - Direct CHG Lookup)
```
IF ID_Exception.Comment CONTAINS "CHG" pattern:
    EXTRACT all CHG numbers from comment (regex: CHG\d{10})
    LOOKUP each CHG in ServiceNow
    IF ServiceNow.approval_status == "Approved" AND ServiceNow.state == "Closed Successful":
        RETURN auto_validated = TRUE, confidence = 100%
```

**Example:**
- ID Comment: "Activity from DSCADA Monthly Patching: CHG0000338290 CHG0000338289 CHG0000338288 CHG0000338287"
- Extract: ['CHG0000338290', 'CHG0000338289', 'CHG0000338288', 'CHG0000338287']
- Lookup each → All approved → Auto-validate

### 3.2 Secondary Correlation Path (Asset + Time Window)
```
IF no CHG in comment:
    MATCH ID_Exception.Asset_Name ≈ ServiceNow.cmdb_ci
    AND ID_Exception.detected_at BETWEEN (ServiceNow.start_date - 24h) AND (ServiceNow.end_date + 24h)
    AND ServiceNow.approval_status == "Approved"
    CALCULATE confidence score based on factors
```

### 3.3 Tertiary Correlation Path (KB Article Match)
```
IF ID_Exception.patch_id MATCHES WSUS_Approved.kb_number:
    RETURN auto_validated = TRUE, rule = "wsus_approved_patch"
```

**Example:**
- ID Patch ID: KB5062070
- WSUS Approved List contains KB5062070
- Auto-validate without needing CHG ticket

---

## 4. SERVICENOW API QUERY SPECIFICATION

### 4.1 Base Endpoint
```
GET https://psegincprod.service-now.com/api/now/table/change_request
```

### 4.2 Recommended Query Parameters
```python
params = {
    # Get changes updated in last 24 hours
    'sysparm_query': '^'.join([
        'sys_updated_on>javascript:gs.hoursAgoStart(24)',
        'assignment_group.nameLIKECyber Security OT',  # Filter to OT team
        'subcategoryLIKEIndustrial Defender',  # Filter to ID-related
    ]),
    
    # Fields to retrieve
    'sysparm_fields': ','.join([
        'number',
        'short_description',
        'description',
        'cmdb_ci',
        'cmdb_ci.name',
        'start_date',
        'end_date',
        'work_start',
        'work_end',
        'state',
        'approval',
        'opened_at',
        'opened_by',
        'assigned_to',
        'assignment_group',
        'category',
        'subcategory',
        'u_environment',
        'implementation_plan',
        'backout_plan',
    ]),
    
    'sysparm_display_value': 'all',
    'sysparm_limit': 200
}
```

### 4.3 Query for Specific CHG Number (Direct Lookup)
```python
def lookup_chg(chg_number: str):
    params = {
        'sysparm_query': f'number={chg_number}',
        'sysparm_fields': 'number,state,approval,cmdb_ci.name,start_date,end_date',
        'sysparm_limit': 1
    }
    # Returns single record or empty
```

---

## 5. DATABASE SCHEMA - UPDATED WITH ACTUAL FIELDS

### 5.1 changes table
```sql
CREATE TABLE changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    -- Source identification
    source TEXT NOT NULL CHECK(source IN ('servicenow','mantis','wsus','manual')),
    ticket_id TEXT NOT NULL,  -- CHG0000338771
    
    -- Asset information
    asset_name TEXT,          -- pccqasasm1
    asset_name_normalized TEXT,
    cmdb_ci_sys_id TEXT,      -- ServiceNow sys_id for linking
    
    -- Classification
    category TEXT,            -- Infrastructure SW
    subcategory TEXT,         -- Industrial Defender
    activity TEXT,            -- Enhancement
    environment TEXT,         -- QA, Prod
    
    -- Descriptions
    short_description TEXT,
    full_description TEXT,
    implementation_plan TEXT,
    test_plan TEXT,
    backout_plan TEXT,
    
    -- Schedule (CRITICAL)
    scheduled_start DATETIME,  -- Proposed Start Date/Time
    scheduled_end DATETIME,    -- Proposed End Date/Time
    actual_start DATETIME,     -- Implementation Start
    actual_end DATETIME,       -- Implementation End
    
    -- Status
    state TEXT,               -- Closed Successful, Open, etc.
    approval_status TEXT,     -- Approved, Rejected, Pending
    approver TEXT,
    approval_group TEXT,
    
    -- Assignment
    assignment_group TEXT,    -- LI Cyber Security OT
    assigned_to TEXT,
    opened_by TEXT,
    
    -- Metadata
    raw_data TEXT,            -- Full JSON from API
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(source, ticket_id)
);
```

### 5.2 id_exceptions table (NEW - Based on ID Screenshots)
```sql
CREATE TABLE id_exceptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    -- Exception identification
    exception_type TEXT NOT NULL,  -- Software, Patch, Port, Firewall, User, Interface
    change_action TEXT,            -- New, Removed, Changed
    
    -- Asset information
    asset_name TEXT,
    asset_name_normalized TEXT,
    asset_group TEXT,              -- Dragos, All_Linux, All_Windows, etc.
    asset_count INTEGER DEFAULT 1,
    
    -- Type-specific fields (nullable based on type)
    -- Software
    software_name TEXT,
    software_version TEXT,
    
    -- Patches
    patch_id TEXT,                 -- KB5062070
    service_pack TEXT,
    
    -- Ports
    port INTEGER,
    protocol TEXT,
    ip_version INTEGER,
    interface TEXT,
    process_name TEXT,
    
    -- Firewall
    policy_id TEXT,
    source_if TEXT,
    dest_if TEXT,
    action TEXT,
    status TEXT,
    
    -- User Accounts
    user_id TEXT,
    user_type TEXT,
    domain TEXT,
    member_of TEXT,
    enabled BOOLEAN,
    
    -- Network Interfaces
    interface_name TEXT,
    ip_address TEXT,
    subnet_mask TEXT,
    mac_address TEXT,
    
    -- Comment (CRITICAL - contains CHG numbers)
    comment TEXT,
    extracted_chg_numbers TEXT,    -- JSON array: ["CHG0000338290", "CHG0000338289"]
    
    -- Timestamps
    detected_at DATETIME NOT NULL,
    
    -- Validation status
    validation_status TEXT DEFAULT 'pending',
    
    -- Metadata
    raw_data TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Index for fast CHG lookups
CREATE INDEX idx_id_exceptions_comment ON id_exceptions(comment);
CREATE INDEX idx_id_exceptions_patch ON id_exceptions(patch_id);
CREATE INDEX idx_id_exceptions_status ON id_exceptions(validation_status);
CREATE INDEX idx_id_exceptions_detected ON id_exceptions(detected_at);
```

### 5.3 wsus_patches table
```sql
CREATE TABLE wsus_patches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kb_number TEXT UNIQUE NOT NULL,  -- KB5062070
    title TEXT,
    classification TEXT,             -- Security, Critical, Definition
    approval_date DATETIME,
    approved_for_groups TEXT,        -- JSON: ["OT Servers", "SCADA", "All_Windows"]
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

## 6. CORRELATION SCORING MATRIX

### 6.1 Weight Configuration
| Factor | Weight | Description |
|--------|--------|-------------|
| CHG in Comment | 0.50 | Direct CHG number found in ID comment field |
| Asset Name Match | 0.25 | cmdb_ci matches asset name (fuzzy) |
| Time Window | 0.15 | Detection within scheduled change window |
| KB Article | 0.10 | Patch ID matches WSUS approved list |

### 6.2 Auto-Validation Thresholds
| Condition | Threshold | Action |
|-----------|-----------|--------|
| CHG found + Approved | 100% | Auto-validate immediately |
| Asset + Time + Approved | ≥95% | Auto-validate |
| KB in WSUS approved | 100% | Auto-validate with WSUS rule |
| Partial match | 50-94% | Flag for manual review |
| No match | <50% | Flag as potentially unauthorized |

---

## 7. REGEX PATTERNS FOR PARSING

### 7.1 Extract CHG Numbers from Comment
```python
import re

def extract_chg_numbers(comment: str) -> list:
    """Extract all CHG ticket numbers from ID comment field."""
    if not comment:
        return []
    pattern = r'CHG\d{10}'
    return re.findall(pattern, comment, re.IGNORECASE)

# Example:
# Input: "Activity from DSCADA Monthly Patching: CHG0000338290 CHG0000338289 CHG0000338288"
# Output: ['CHG0000338290', 'CHG0000338289', 'CHG0000338288']
```

### 7.2 Extract KB Numbers from Text
```python
def extract_kb_numbers(text: str) -> list:
    """Extract KB article numbers from any text field."""
    if not text:
        return []
    pattern = r'KB\d{6,7}'
    return re.findall(pattern, text, re.IGNORECASE)
```

### 7.3 Normalize Asset Names
```python
def normalize_asset_name(name: str) -> str:
    """Normalize asset name for fuzzy matching."""
    if not name:
        return ''
    
    normalized = name.lower().strip()
    
    # Remove domain suffixes
    normalized = re.sub(r'\.(local|internal|corp|domain|psegli\.com)$', '', normalized)
    
    # Remove common prefixes
    normalized = re.sub(r'^(srv|wks|vm|host|pcc|bcc)[-_]?', '', normalized)
    
    # Remove special characters
    normalized = re.sub(r'[^a-z0-9]', '', normalized)
    
    return normalized
```

---

## 8. ID EXPORT INTEGRATION OPTIONS

### 8.1 Option A: Manual CSV Export (No Cost)
1. User clicks "Export" button in ID Bulk Exceptions
2. Saves CSV to shared network folder
3. Validation tool monitors folder for new files
4. Imports and processes on detection

### 8.2 Option B: Email Forwarding (No Cost)
1. Configure ID to email alert summaries
2. Tool monitors mailbox via IMAP
3. Parses email body for exception details

### 8.3 Option C: Syslog Integration (No Cost)
1. Configure ID to send syslog to validation tool
2. Tool listens on UDP 514 or custom port
3. Parses CEF/syslog format in real-time

### 8.4 Option D: API (If Available)
1. Check if ID has REST API enabled
2. Query `/api/exceptions` endpoint
3. Best option if available

---

## 9. IMPLEMENTATION PRIORITIES

### Phase 1 (Week 1-2): Core Infrastructure
1. ✅ Database schema with actual fields
2. ✅ ServiceNow connector with correct API fields
3. ✅ CHG number extraction from comments
4. ⬜ Basic Streamlit dashboard

### Phase 2 (Week 3-4): Data Ingestion
1. ⬜ ID CSV import parser
2. ⬜ WSUS approved patches import
3. ⬜ Email listener for ID alerts

### Phase 3 (Week 5-6): Correlation Engine
1. ⬜ Direct CHG lookup (primary path)
2. ⬜ Asset + time window correlation
3. ⬜ KB article matching
4. ⬜ Confidence scoring

### Phase 4 (Week 7-8): Polish
1. ⬜ Audit report generation
2. ⬜ Metrics dashboard
3. ⬜ Notification integration
4. ⬜ Production deployment

---

## 10. APPENDIX: DRAGOS RULES REFERENCE

From the DRAGOS_PROD_RULES Excel export, key detection rules include:
- Port Scan Detected
- RDP traffic false positives  
- SMB Command Shell Activity
- Telnet Command (multiple rules)

These generate alerts that may also need validation against change tickets.
Columns: Action, Name, Criteria, Skip Processing, Close

---

*Document Version: 1.1*
*Last Updated: January 2026*
*Based on: PSEG Long Island ID ASM and ServiceNow production screenshots*
