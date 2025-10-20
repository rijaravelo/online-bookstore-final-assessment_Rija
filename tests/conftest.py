import os
import sys
import pathlib
import pytest

# Ensure repository root is on sys.path for imports like `from app import app`
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

@pytest.fixture(scope="session")
def app():
    """
    Import your Flask app once and share it.
    """
    try:
        from app import app as flask_app  # your repo's Flask instance
    except Exception as e:
        pytest.fail(f"Could not import Flask app from app.py: {e}")

    flask_app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        # If your app reads a simple in-memory database,
        # tests won't persist data across sessions.
    )
    return flask_app

@pytest.fixture()
def client(app):
    return app.test_client()

@pytest.fixture()
def runner(app):
    return app.test_cli_runner()
