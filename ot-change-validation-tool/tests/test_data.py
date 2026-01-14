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

TEST_WSUS_PATCHES = [
    {
        'kb_number': 'KB5062070',
        'title': 'Security Update for Windows Server 2019',
        'classification': 'Security Updates',
        'approval_date': '2025-01-13 10:00:00',
        'approved_for_groups': ['OT Servers', 'SCADA', 'All_Windows'],
    },
    {
        'kb_number': 'KB5063871',
        'title': 'Cumulative Update for Windows 10',
        'classification': 'Updates',
        'approval_date': '2025-01-12 08:00:00',
        'approved_for_groups': ['All_Windows'],
    },
]

TEST_ID_CSV_CONTENT = """Type,Patch ID,Service Pack In Effect,Asset Groups,Assets,Comment,Exception Detection Date
Removed,KB5062070,,All_Windows,5,Activity from DSCADA Monthly Patching: CHG0000338290,12/24/2025 2:00:19 AM
New,KB5063871,,Domain Controllers,2,Scheduled maintenance,12/24/2025 3:15:00 AM
"""
