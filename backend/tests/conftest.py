"""Pytest bootstrap: point the app at a file-based SQLite DB before app import."""

import os

# Must be set before app.config/.database are imported anywhere.
_TEST_DB = "/tmp/fq_gate_test.db"
if os.path.exists(_TEST_DB):
    os.remove(_TEST_DB)
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB}"
os.environ.setdefault("JWT_SECRET", "test-secret")
