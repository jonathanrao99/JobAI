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
mkdir -p frontend/src/{pages,components,lib,hooks}
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

# ── Node / React setup ───────────────────────────────────
echo ""
echo "⚛️  Setting up React frontend..."
cd frontend
npm create vite@latest . -- --template react --force -y 2>/dev/null || true
npm install
npm install @tanstack/react-query axios recharts react-router-dom lucide-react date-fns
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p 2>/dev/null || true
cd ..
echo "   ✅ React + Vite + Tailwind installed"

echo ""
echo "=================================================="
echo "  ✅ Setup complete!"
echo ""
echo "  Next steps:"
echo "  1. conda activate job-agent  (or source .venv/bin/activate)"
echo "  2. pip install -r backend/requirements.txt"
echo "     npm install && npm run dev   → API + frontend"
echo "  3. cp .env.example .env  →  fill in your keys"
echo "  4. Run backend/db/schema.sql in Supabase SQL Editor (migrate.py prints steps)"
echo "  5. uvicorn backend.main:app --reload"
echo "  6. cd frontend && npm run dev"
echo "=================================================="
