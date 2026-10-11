"""
Test isolation for every test folder (tests/ and backend/tests/).

Before any project module is imported, the database is copied to a temporary folder and the
app is pointed at the copy (MEDINEXUS_DB_PATH), and audit-log files go to a temporary folder
(MEDINEXUS_LOGS_DIR). Tests can therefore write freely — sign-in failures, blocked requests,
proposals, sweeps — without changing the developer's database or the security statistics,
and they can run while the app itself is running.
"""

import os
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
_LIVE_DB = ROOT / "database" / "healthcare.duckdb"
_TMP = Path(tempfile.mkdtemp(prefix="medinexus_test_"))

if "MEDINEXUS_DB_PATH" not in os.environ:
    test_db = _TMP / "healthcare_test.duckdb"
    if _LIVE_DB.exists():
        shutil.copy2(_LIVE_DB, test_db)
        wal = _LIVE_DB.with_suffix(".duckdb.wal")
        if wal.exists():
            shutil.copy2(wal, test_db.with_suffix(".duckdb.wal"))
        # Accounts come from the test seed file, never from the developer's real people
        import duckdb

        con = duckdb.connect(str(test_db))
        con.execute("DROP TABLE IF EXISTS app_users")
        con.close()
    os.environ["MEDINEXUS_DB_PATH"] = str(test_db)
os.environ.setdefault("MEDINEXUS_LOGS_DIR", str(_TMP / "logs"))
# No paid AI calls and no background scheduler in any test (agent tests inject a fake provider)
os.environ["NEXA_LLM_PROVIDER"] = "rules"
os.environ["NEXA_SWEEP_ENABLED"] = "0"


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_TMP, ignore_errors=True)


def pytest_report_header(config):
    return f"test database: {os.environ['MEDINEXUS_DB_PATH']} (copy; the live database is never written)"
