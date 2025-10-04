"""Test configuration and fixtures for CTF Proxy tests."""

import shutil
import sqlite3
import tempfile
from contextlib import contextmanager
from pathlib import Path

import pytest

from ctf_proxy.db.models import make_db


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
    db_file = temp_dir / "test.db"

    tap_folder.mkdir()
    archive_folder.mkdir()

    yield {
        "temp_dir": temp_dir,
        "tap_folder": tap_folder,
        "archive_folder": archive_folder,
        "db_file": db_file,
    }

    # Cleanup
    if temp_dir.exists():
        shutil.rmtree(temp_dir)


@pytest.fixture
def sample_tap_files(test_data_dir, temp_directories):
    """Copy sample test data files to temp directory."""
    tap_folder = temp_directories["tap_folder"]

    # Get available test data files
    data_files = [f for f in test_data_dir.iterdir() if f.suffix == ".json"]

    copied_files = []
    for data_file in data_files[:5]:  # Use first 5 files
        dest_file = tap_folder / data_file.name
        shutil.copy2(data_file, dest_file)
        copied_files.append(dest_file)

    # Verify original files still exist (safety check)
    for data_file in data_files[:5]:
        assert data_file.exists(), f"Original test data file {data_file} was affected!"

    return copied_files


@contextmanager
def persisted_connection(connection):
    yield connection


class PersistedDbProvider:
    def __init__(self, path: str):
        self.path = path
        self.connection = sqlite3.connect(path)

    def connect(self) -> sqlite3.Connection:
        return persisted_connection(self.connection)

    def close(self):
        self.connection.close()


@pytest.fixture
def db():
    db = make_db(":memory:", db_provider=PersistedDbProvider)
    yield db
    db.db_provider.close()
