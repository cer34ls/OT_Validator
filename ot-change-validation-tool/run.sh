#!/bin/bash
# run.sh - Start the OT Change Validation Tool

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check for virtual environment
if [ -d "venv" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
fi

# Check Python version
python_version=$(python3 --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1,2)
required_version="3.10"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
    echo "Error: Python 3.10+ required (found $python_version)"
    exit 1
fi

# Initialize database if needed
echo "Initializing database..."
python3 scripts/init_db.py

# Check for .env file
if [ ! -f ".env" ]; then
    echo "Warning: No .env file found. Copy .env.example to .env and configure your settings."
fi

# Parse arguments
ACTION=${1:-dashboard}

case $ACTION in
    dashboard)
        echo "Starting dashboard on port ${DASHBOARD_PORT:-8501}..."
        streamlit run app/dashboard.py --server.port ${DASHBOARD_PORT:-8501} --server.address 0.0.0.0
        ;;
    sync)
        echo "Running data sync..."
        python3 scripts/sync_all.py
        ;;
    init)
        echo "Database initialized."
        ;;
    test)
        echo "Running tests..."
        pytest tests/ -v
        ;;
    help|--help|-h)
        echo "OT Change Validation Tool"
        echo ""
        echo "Usage: ./run.sh [command]"
        echo ""
        echo "Commands:"
        echo "  dashboard  Start the Streamlit dashboard (default)"
        echo "  sync       Run data synchronization"
        echo "  init       Initialize database only"
        echo "  test       Run tests"
        echo "  help       Show this help message"
        ;;
    *)
        echo "Unknown command: $ACTION"
        echo "Run './run.sh help' for usage."
        exit 1
        ;;
esac
