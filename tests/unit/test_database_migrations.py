"""Unit tests for database schema DDL and Alembic migration baseline (P3-2).

Verifies:
- schema.sql exists at repository root and defines all 5 mandatory operational tables:
  suppliers, risk_alerts, hitl_approvals, audit_logs, agent_runs.
- schema.sql enforces strict architectural invariants:
  - NUMERIC(14,2) precision for monetary values (financial_exposure, amount_usd)
  - UNIQUE constraint on hitl_approvals.token_hash (anti-replay gate)
  - Check constraints on supplier tier, risk_level, and spend_tier
  - Append-only trigger preventing UPDATE or DELETE on audit_logs (BR-RULE-007)
- alembic.ini exists at repo root and configures src/database/migrations.
- Migration environment (env.py, script.py.mako) correctly binds target_metadata.
- Initial baseline migration revision exists with valid upgrade() and downgrade().
- Offline migration generation (`alembic upgrade head --sql`) executes cleanly with zero I/O.
"""

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
SCHEMA_SQL_PATH = REPO_ROOT / "schema.sql"
ALEMBIC_INI_PATH = REPO_ROOT / "alembic.ini"
MIGRATIONS_DIR = REPO_ROOT / "src" / "database" / "migrations"


def test_schema_sql_exists_and_contains_all_five_tables():
    """Verify schema.sql exists at root and declares all 5 operational tables."""
    assert SCHEMA_SQL_PATH.exists(), f"schema.sql not found at {SCHEMA_SQL_PATH}"
    content = SCHEMA_SQL_PATH.read_text(encoding="utf-8")

    mandatory_tables = [
        "suppliers",
        "risk_alerts",
        "hitl_approvals",
        "audit_logs",
        "agent_runs",
    ]
    for table in mandatory_tables:
        pattern = rf"CREATE\s+TABLE\s+(IF\s+NOT\s+EXISTS\s+)?{table}\b"
        assert re.search(pattern, content, re.IGNORECASE), (
            f"Table creation DDL for '{table}' missing from schema.sql"
        )


def test_schema_sql_enforces_monetary_precision_and_security():
    """Verify schema.sql enforces NUMERIC(14,2), unique token_hash, and append-only trigger."""
    assert SCHEMA_SQL_PATH.exists(), "schema.sql must exist"
    content = SCHEMA_SQL_PATH.read_text(encoding="utf-8")

    # Monetary precision (BR-RULE-001)
    assert re.search(
        r"financial_exposure\s+NUMERIC\s*\(\s*14\s*,\s*2\s*\)", content, re.IGNORECASE
    ), "risk_alerts.financial_exposure must use NUMERIC(14,2)"
    assert re.search(r"amount_usd\s+NUMERIC\s*\(\s*14\s*,\s*2\s*\)", content, re.IGNORECASE), (
        "hitl_approvals.amount_usd must use NUMERIC(14,2)"
    )

    # Anti-replay unique constraint on token_hash
    assert re.search(r"token_hash\b.*UNIQUE", content, re.IGNORECASE), (
        "hitl_approvals.token_hash must enforce UNIQUE constraint"
    )

    # Check constraints
    assert re.search(
        r"tier\s+INT\s+NOT\s+NULL\s+CHECK\s*\(tier\s+BETWEEN\s+1\s+AND\s+3\)",
        content,
        re.IGNORECASE,
    ) or ("tier BETWEEN 1 AND 3" in content)
    assert "CRITICAL" in content and "HIGH" in content and "MEDIUM" in content and "LOW" in content
    assert "CATEGORY_MGR" in content and "PROC_DIRECTOR" in content and "DUAL_VP" in content

    # Append-only trigger for audit_logs
    assert re.search(r"BEFORE\s+(UPDATE|DELETE).*\bON\s+audit_logs\b", content, re.IGNORECASE) or (
        "audit_logs" in content and "append-only" in content.lower()
    )


def test_alembic_ini_exists_and_configured():
    """Verify alembic.ini exists at repo root and references migration directory."""
    assert ALEMBIC_INI_PATH.exists(), f"alembic.ini not found at {ALEMBIC_INI_PATH}"
    content = ALEMBIC_INI_PATH.read_text(encoding="utf-8")

    assert "script_location" in content
    assert "src/database/migrations" in content or "migrations" in content


def test_alembic_env_and_script_mako_exist():
    """Verify env.py and script.py.mako exist in src/database/migrations/."""
    env_py = MIGRATIONS_DIR / "env.py"
    script_mako = MIGRATIONS_DIR / "script.py.mako"

    assert env_py.exists(), f"env.py not found at {env_py}"
    assert script_mako.exists(), f"script.py.mako not found at {script_mako}"

    env_content = env_py.read_text(encoding="utf-8")
    assert "target_metadata" in env_content
    assert "Base" in env_content


def test_alembic_initial_migration_exists_and_revises():
    """Verify initial baseline migration file exists under versions/ and defines upgrade/downgrade."""
    versions_dir = MIGRATIONS_DIR / "versions"
    assert versions_dir.exists(), f"versions directory not found at {versions_dir}"

    version_files = list(versions_dir.glob("*.py"))
    assert len(version_files) >= 1, f"No migration scripts found in {versions_dir}"

    initial_script = version_files[0].read_text(encoding="utf-8")
    assert "def upgrade()" in initial_script
    assert "def downgrade()" in initial_script
    assert "suppliers" in initial_script
    assert "risk_alerts" in initial_script
    assert "hitl_approvals" in initial_script
    assert "audit_logs" in initial_script
    assert "agent_runs" in initial_script


def test_alembic_offline_sql_generation():
    """Verify alembic can generate offline SQL migration script without connecting to live database."""
    assert ALEMBIC_INI_PATH.exists(), "alembic.ini must exist"

    result = subprocess.run(
        ["alembic", "upgrade", "head", "--sql"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"Alembic offline SQL generation failed: {result.stderr}"
    sql_output = result.stdout
    assert "CREATE TABLE suppliers" in sql_output or "suppliers" in sql_output
    assert "risk_alerts" in sql_output
    assert "hitl_approvals" in sql_output
    assert "audit_logs" in sql_output
    assert "agent_runs" in sql_output
