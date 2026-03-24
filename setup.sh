#!/bin/bash
# ============================================================
#  Job Search Agent — Session 1 Setup
#  Run this once from your project root:  bash setup.sh
# ============================================================

set -e  # Exit on any error

echo ""
echo "=================================================="
echo "  Job Search Agent — Project Scaffold Setup"
echo "=================================================="
echo ""

# ── Create full directory tree ───────────────────────────
echo "📁 Creating project structure..."

mkdir -p backend/{agents,integrations,models,prompts,routers,utils}
mkdir -p backend/agents
mkdir -p frontend/{app,components,hooks,public}
mkdir -p data/{resumes,outputs,logs,snapshots}

# Create __init__.py files for Python packages
touch backend/__init__.py
touch backend/agents/__init__.py
touch backend/integrations/__init__.py
touch backend/models/__init__.py
touch backend/prompts/__init__.py
touch backend/routers/__init__.py
touch backend/utils/__init__.py

echo "   ✅ Directory structure created"

# ── Python virtual environment ───────────────────────────
echo ""
echo "🐍 Setting up Python environment..."

if command -v conda &> /dev/null; then
    conda create -n job-agent python=3.11 -y
    echo "   ✅ Conda env 'job-agent' created"
    echo "   ⚠️  Run: conda activate job-agent"
else
    python3.11 -m venv .venv
    echo "   ✅ Venv created at .venv"
    echo "   ⚠️  Run: source .venv/bin/activate"
fi

# ── Node / Next.js setup ─────────────────────────────────
echo ""
echo "⚛️  Installing frontend dependencies..."
npm install --prefix frontend
echo "   ✅ Next.js frontend dependencies installed"

echo ""
echo "=================================================="
echo "  ✅ Setup complete!"
echo ""
echo "  Next steps:"
echo "  1. conda activate job-agent  (or source .venv/bin/activate)"
echo "  2. pip install -r backend/requirements.txt"
echo "  3. npm install                 → root dev tooling"
echo "  4. cp .env.example .env  →  fill in your keys"
echo "  5. Run backend/db/schema.sql in Supabase SQL Editor (migrate.py prints steps)"
echo "  6. npm run dev                 → API + Next.js frontend"
echo "=================================================="
