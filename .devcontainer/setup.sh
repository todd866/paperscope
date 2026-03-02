#!/bin/bash
set -e

echo "Setting up Research Engine development environment..."

# Install Python dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Install development tools
pip install pytest black ruff

echo "Setup complete!"
