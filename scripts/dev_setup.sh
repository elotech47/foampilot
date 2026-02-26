#!/usr/bin/env bash
set -euo pipefail

echo "Setting up FoamPilot development environment..."

# Check Python version
python3 --version | grep -E "3\.(11|12|13)" || { echo "Python 3.11+ required"; exit 1; }

# Install in editable mode with dev extras
pip install -e ".[dev]"

# Copy env template if not exists
if [ ! -f .env ]; then
    cp .env.example .env
    echo "Created .env from .env.example — add your ANTHROPIC_API_KEY"
fi

echo "Done. Run 'pytest tests/unit/' to verify setup."
