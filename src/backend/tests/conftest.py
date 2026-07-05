"""Test configuration and fixtures for CTF Proxy tests."""

import shutil
import tempfile
from pathlib import Path

import psycopg
import pytest

from ctf_proxy.db import connection
from ctf_proxy.db.models import make_db


@pytest.fixture(autouse=True)
def reset_schemas():
    conn = psycopg.connect(connection.dsn())
    conn.execute("DROP SCHEMA IF EXISTS logs CASCADE")
    conn.execute("DROP SCHEMA IF EXISTS analytics CASCADE")
    conn.execute("DROP SCHEMA IF EXISTS dashboard CASCADE")
    conn.commit()
    conn.close()
    yield


@pytest.fixture
def test_data_dir():
    """Provide path to test data directory."""
    current_dir = Path(__file__).parent
    data_dir = current_dir / "data"
    return data_dir


@pytest.fixture
def temp_directories():
    """Create temporary directories for testing."""
    temp_dir = Path(tempfile.mkdtemp())
    tap_folder = temp_dir / "taps"
    archive_folder = temp_dir / "archive"

    tap_folder.mkdir()
    archive_folder.mkdir()

    yield {
        "temp_dir": temp_dir,
        "tap_folder": tap_folder,
        "archive_folder": archive_folder,
    }

    if temp_dir.exists():
        shutil.rmtree(temp_dir)


@pytest.fixture
def sample_tap_files(test_data_dir, temp_directories):
    """Copy sample test data files to temp directory."""
    tap_folder = temp_directories["tap_folder"]

    data_files = [f for f in test_data_dir.iterdir() if f.suffix == ".json"]

    copied_files = []
    for data_file in data_files[:5]:
        dest_file = tap_folder / data_file.name
        shutil.copy2(data_file, dest_file)
        copied_files.append(dest_file)

    for data_file in data_files[:5]:
        assert data_file.exists(), f"Original test data file {data_file} was affected!"

    return copied_files


@pytest.fixture
def db():
    return make_db()
