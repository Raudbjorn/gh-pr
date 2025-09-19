#!/bin/bash
# Installation script for gh-pr

set -e

echo "Installing gh-pr Python tool..."

# Check for uv
if ! command -v uv &> /dev/null; then
    echo "Error: uv is required but not installed."
    echo "Install it with: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

# Create a virtual environment
echo "Creating virtual environment..."
uv venv .venv

# Install dependencies
echo "Installing dependencies..."
.venv/bin/uv pip install -e . --index-url https://pypi.org/simple

# Create wrapper script
echo "Creating executable wrapper..."
cat > gh-pr << 'EOF'
#!/bin/bash
# gh-pr wrapper script

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Run the Python module with the virtual environment
exec "$SCRIPT_DIR/.venv/bin/python" -m gh_pr "$@"
EOF

chmod +x gh-pr

echo ""
echo "Installation complete!"
echo ""
echo "To use gh-pr, you can either:"
echo "  1. Add $(pwd) to your PATH"
echo "  2. Create a symlink: sudo ln -s $(pwd)/gh-pr /usr/local/bin/gh-pr"
echo "  3. Run it directly: $(pwd)/gh-pr"
echo ""
echo "Example usage:"
echo "  gh-pr --help"
echo "  gh-pr 123"
echo "  gh-pr -i"