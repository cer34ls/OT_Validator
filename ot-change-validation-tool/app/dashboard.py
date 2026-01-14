"""
OT Change Validation Tool - Main Dashboard
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import sys
from pathlib import Path
import tempfile

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
    db = Database(DATABASE_PATH)
    db.init()  # Ensure tables exist
    return db


db = get_database()

# Sidebar
st.sidebar.title("OT Validation Tool")
st.sidebar.markdown("---")

# Navigation
page = st.sidebar.radio(
    "Navigate",
    [
        "Pending Validations",
        "Search",
        "Dashboard",
        "Import Data",
        "Reports",
        "Settings",
    ]
)

st.sidebar.markdown("---")

# Sync status
st.sidebar.subheader("Sync Status")
sync_status = db.get_sync_status()
for status in sync_status:
    if status['status'] == 'success':
        icon = "OK"
    elif status['status'] == 'not_configured':
        icon = "--"
    else:
        icon = "X"
    last_sync = status['last_sync'] or 'Never'
    st.sidebar.text(f"[{icon}] {status['source_name']}: {last_sync}")

# Main content based on page selection
if page == "Pending Validations":
    st.header("Pending Validation Queue")

    # Get pending alerts
    pending = db.get_pending_alerts()

    if not pending:
        st.success("No pending validations! All caught up.")
    else:
        st.warning(f"{len(pending)} items pending review")

        # Display as table
        df = pd.DataFrame(pending)

        # Add action buttons
        for idx, row in df.iterrows():
            with st.expander(f"**{row.get('asset_name', 'Unknown')}** - {row.get('change_category', 'N/A')}", expanded=False):
                col1, col2 = st.columns([3, 1])

                with col1:
                    st.write(f"**Detected:** {row.get('detected_at')}")
                    st.write(f"**Change:** {row.get('change_detail', 'N/A')[:200]}")
                    st.write(f"**Source:** {row.get('source_type', 'N/A')}")

                    if row.get('matched_ticket'):
                        st.info(f"Suggested Match: {row['matched_ticket']} (Score: {row.get('correlation_score', 0):.0%})")

                with col2:
                    if st.button("Validate", key=f"val_{row['id']}"):
                        db.update_alert_status(row['id'], 'validated', 'manual')
                        st.rerun()

                    if st.button("Unauthorized", key=f"unauth_{row['id']}"):
                        db.update_alert_status(row['id'], 'unauthorized', 'manual')
                        st.rerun()

                    if st.button("Investigate", key=f"inv_{row['id']}"):
                        db.update_alert_status(row['id'], 'investigating', 'manual')
                        st.rerun()

elif page == "Search":
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
                    desc = r.get('description', 'N/A') or 'N/A'
                    st.write(f"**Description:** {desc[:200]}...")
                    st.write(f"**Status:** {r.get('approval_status', 'N/A')}")
                    st.write(f"**Window:** {r.get('scheduled_start')} to {r.get('scheduled_end')}")
        else:
            st.info("No results found")

elif page == "Dashboard":
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

    # Show sync status summary
    st.subheader("Data Sources")
    sync_df = pd.DataFrame(sync_status)
    if not sync_df.empty:
        st.dataframe(sync_df[['source_name', 'last_sync', 'records_synced', 'status']])

elif page == "Import Data":
    st.header("Import Data")

    tab1, tab2, tab3 = st.tabs(["ID Bulk Exceptions", "WSUS Patches", "ServiceNow"])

    with tab1:
        st.subheader("Import ID Bulk Exceptions CSV")

        uploaded_file = st.file_uploader("Upload ID Export CSV", type=['csv'], key='id_csv')

        if uploaded_file:
            from connectors.id_parser import IDExceptionParser
            from engine.validator import BatchProcessor

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
                            'Detected': str(exc.detected_at),
                        })

                    st.dataframe(pd.DataFrame(preview_data))

                    if st.button("Process and Validate"):
                        # Convert to dict format
                        exc_dicts = parser.to_database_records(exceptions)

                        processor = BatchProcessor(db)
                        summary = processor.process_csv_import(exc_dicts)

                        st.success(f"Processed {summary['total']} exceptions")
                        st.write(f"- Auto-validated: {summary['auto_validated']}")
                        st.write(f"- Pending review: {summary['pending_review']}")

            except Exception as e:
                st.error(f"Error processing file: {e}")

    with tab2:
        st.subheader("Import WSUS Approved Patches")

        wsus_file = st.file_uploader("Upload WSUS Export CSV", type=['csv'], key='wsus_csv')

        if wsus_file:
            from connectors.wsus_importer import WSUSImporter, WSUSSyncer

            with tempfile.NamedTemporaryFile(delete=False, suffix='.csv') as tmp:
                tmp.write(wsus_file.getvalue())
                tmp_path = tmp.name

            try:
                importer = WSUSImporter(str(Path(tmp_path).parent))
                patches = importer.import_patches(tmp_path)

                st.success(f"Found {len(patches)} approved patches")

                # Preview
                preview = []
                for p in patches[:10]:
                    preview.append({
                        'KB Number': p['kb_number'],
                        'Title': p['title'][:50] + '...' if p['title'] else '',
                        'Classification': p['classification'],
                        'Approval Date': p['approval_date'],
                    })

                st.dataframe(pd.DataFrame(preview))

                if st.button("Import Patches"):
                    syncer = WSUSSyncer(importer, db)
                    count = syncer.sync(tmp_path)
                    st.success(f"Imported {count} patches to database")

            except Exception as e:
                st.error(f"Error processing file: {e}")

    with tab3:
        st.subheader("ServiceNow Sync")

        st.info("Configure ServiceNow credentials in .env file")

        hours_back = st.number_input("Sync changes from last N hours", value=24, min_value=1, max_value=168)

        if st.button("Sync Now"):
            try:
                from connectors.servicenow_pseg import PSEGServiceNowConnector
                from config.settings import SERVICENOW_CONFIG

                if not SERVICENOW_CONFIG['username']:
                    st.error("ServiceNow credentials not configured")
                else:
                    connector = PSEGServiceNowConnector(**SERVICENOW_CONFIG)
                    changes = connector.fetch_recent_ot_changes(hours_ago=hours_back)

                    count = 0
                    for change in changes:
                        db.upsert_change(change)
                        count += 1

                    db.update_sync_status('servicenow', count, 'success')
                    st.success(f"Synced {count} changes from ServiceNow")

            except ValueError as e:
                st.error(f"Configuration error: {e}")
            except Exception as e:
                st.error(f"Sync failed: {e}")

elif page == "Reports":
    st.header("Audit Reports")

    st.subheader("Generate CIP-010 Validation Report")

    col1, col2 = st.columns(2)

    with col1:
        start_date = st.date_input("Start Date", datetime.now() - timedelta(days=30))

    with col2:
        end_date = st.date_input("End Date", datetime.now())

    report_type = st.selectbox("Report Type", [
        "All Validations",
        "Auto-Validated Only",
        "Manual Reviews",
        "Unauthorized Changes"
    ])

    if st.button("Generate Report"):
        # Query validations in date range
        with db.connection() as conn:
            query = """
                SELECT
                    a.asset_name,
                    a.change_category,
                    a.change_detail,
                    a.detected_at,
                    a.validation_status,
                    v.correlation_score,
                    v.validation_status as validation_result,
                    v.validated_by,
                    v.validated_at,
                    v.notes,
                    c.ticket_id as matched_ticket
                FROM alerts a
                LEFT JOIN validations v ON a.id = v.alert_id
                LEFT JOIN changes c ON v.change_id = c.id
                WHERE a.detected_at >= ? AND a.detected_at <= ?
                ORDER BY a.detected_at DESC
            """
            cursor = conn.execute(query, (
                start_date.isoformat(),
                (end_date + timedelta(days=1)).isoformat()
            ))
            results = [dict(row) for row in cursor.fetchall()]

        if results:
            df = pd.DataFrame(results)
            st.dataframe(df)

            # Download button
            csv = df.to_csv(index=False)
            st.download_button(
                "Download CSV",
                csv,
                f"validation_report_{start_date}_{end_date}.csv",
                "text/csv"
            )
        else:
            st.info("No data found for selected date range")

elif page == "Settings":
    st.header("Settings")

    st.subheader("Data Source Configuration")
    st.info("Configure data sources in the .env file")

    st.subheader("Correlation Thresholds")

    from config.settings import CORRELATION_CONFIG

    auto_threshold = st.slider(
        "Auto-Validation Threshold",
        0.5, 1.0,
        CORRELATION_CONFIG['auto_validate_threshold']
    )
    min_threshold = st.slider(
        "Minimum Match Threshold",
        0.0, 0.5,
        CORRELATION_CONFIG['minimum_match_threshold']
    )
    time_buffer = st.number_input(
        "Time Buffer (hours)",
        1, 72,
        CORRELATION_CONFIG['time_buffer_hours']
    )

    if st.button("Save Settings"):
        st.info("Settings are configured via .env file and config/settings.py")

    st.subheader("Database")
    st.write(f"Database path: `{DATABASE_PATH}`")

    if st.button("Reinitialize Database"):
        db.init()
        st.success("Database reinitialized")

# Footer
st.sidebar.markdown("---")
st.sidebar.markdown("OT Change Validation Tool v1.0")
