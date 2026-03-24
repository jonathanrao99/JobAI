"""
backend/db/migrate.py
=====================
Prints where to run the canonical schema (Supabase has no generic “run this SQL file” API
on the REST surface the Python client uses).

Usage:
    python backend/db/migrate.py
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def run_migration() -> None:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY")
    schema_path = (Path(__file__).parent / "schema.sql").resolve()

    if not url or not key:
        print("❌ Missing SUPABASE_URL or SUPABASE_SERVICE_KEY in .env")
        sys.exit(1)

    if not schema_path.exists():
        print(f"❌ Schema file not found: {schema_path}")
        sys.exit(1)

    print("Supabase schema is applied in the dashboard (or CLI), not via a magic HTTP RPC.")
    print()
    print("  1. Supabase → SQL Editor → New query")
    print(f"  2. Paste: {schema_path}")
    print("  3. Run")
    print()
    print("Optional: use Supabase MCP `apply_migration` / `execute_sql` from Cursor.")
    print(f"Project URL (from .env): {url}")
    mig = schema_path.parent / "migrations" / "add_jd_keywords.sql"
    if mig.exists():
        print()
        print("If your database predates newer columns, also run forward migrations, e.g.:")
        print(f"  {mig}")


if __name__ == "__main__":
    run_migration()
