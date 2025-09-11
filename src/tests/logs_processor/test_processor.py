"""Test the PostProcessor class."""

import os
import sqlite3
from pathlib import Path

from ctf_proxy.logs_processor.batch import BatchProcessor


def test_init_db(temp_directories):
    """Test database initialization."""
    db_file = temp_directories["db_file"]
    BatchProcessor(
        tap_folder=str(temp_directories["tap_folder"]),
        db_file=str(db_file),
        archive_folder=str(temp_directories["archive_folder"]),
    )

    # Verify database file exists
    assert db_file.exists()

    # Verify tables were created
    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]

    expected_tables = [
        "batches",
        "taps",
        "requests",
        "path_stats",
        "method_stats",
        "status_stats",
        "hourly_stats",
        "query_param_stats",
    ]

    for table in expected_tables:
        assert table in tables, f"Expected table {table} not found"

    conn.close()


def test_database_schema(temp_directories):
    """Test database schema has required columns."""
    db_file = temp_directories["db_file"]
    BatchProcessor(
        tap_folder=str(temp_directories["tap_folder"]),
        db_file=str(db_file),
        archive_folder=str(temp_directories["archive_folder"]),
    )

    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()

    # Check batches table
    cursor.execute("PRAGMA table_info(batches)")
    batch_columns = [row[1] for row in cursor.fetchall()]
    assert "batch_id" in batch_columns
    assert "archive_file" in batch_columns
    assert "tap_count" in batch_columns

    # Check taps table
    cursor.execute("PRAGMA table_info(taps)")
    tap_columns = [row[1] for row in cursor.fetchall()]
    assert "tap_id" in tap_columns
    assert "batch_id" in tap_columns
    assert "file_name" in tap_columns

    # Check requests table
    cursor.execute("PRAGMA table_info(requests)")
    request_columns = [row[1] for row in cursor.fetchall()]
    assert "tap_id" in request_columns
    assert "batch_id" in request_columns
    assert "method" in request_columns
    assert "path" in request_columns
    assert "status" in request_columns

    conn.close()


def test_normalize_path(temp_directories):
    """Test path normalization functionality."""
    processor = BatchProcessor(
        tap_folder=str(temp_directories["tap_folder"]),
        db_file=str(temp_directories["db_file"]),
        archive_folder=str(temp_directories["archive_folder"]),
    )

    # Test basic normalization
    assert processor.normalize_path("/api/users/123") == "/api/users/{id}"
    assert processor.normalize_path("/api/users/456/posts") == "/api/users/{id}/posts"

    # Test UUID normalization
    uuid_path = "/api/resource/550e8400-e29b-41d4-a716-446655440000"
    assert processor.normalize_path(uuid_path) == "/api/resource/{uuid}"

    # Test hash normalization
    hash_path = "/api/files/abcd1234567890abcd1234567890abcd1234567890"
    assert processor.normalize_path(hash_path) == "/api/files/{hash}"

    # Test empty path
    assert processor.normalize_path("") == "/"
    assert processor.normalize_path(None) == "/"


def test_extract_query_params(temp_directories):
    """Test query parameter extraction."""
    processor = BatchProcessor(
        tap_folder=str(temp_directories["tap_folder"]),
        db_file=str(temp_directories["db_file"]),
        archive_folder=str(temp_directories["archive_folder"]),
    )

    # Test path with query params
    path_with_params = "/api/search?q=test&limit=10&page=1"
    params = processor.extract_query_params(path_with_params)

    assert "q" in params
    assert "limit" in params
    assert "page" in params
    assert params["q"] == ["test"]
    assert params["limit"] == ["10"]

    # Test path without query params
    path_without_params = "/api/users"
    params = processor.extract_query_params(path_without_params)
    assert params == {}

    # Test empty path
    assert processor.extract_query_params("") == {}
    assert processor.extract_query_params(None) == {}


def test_get_header_value(temp_directories):
    """Test header value extraction."""
    processor = BatchProcessor(
        tap_folder=str(temp_directories["tap_folder"]),
        db_file=str(temp_directories["db_file"]),
        archive_folder=str(temp_directories["archive_folder"]),
    )

    headers = [
        {"key": ":method", "value": "GET"},
        {"key": ":path", "value": "/api/test"},
        {"key": "content-type", "value": "application/json"},
    ]

    assert processor.get_header_value(headers, ":method") == "GET"
    assert processor.get_header_value(headers, ":path") == "/api/test"
    assert processor.get_header_value(headers, "content-type") == "application/json"
    assert processor.get_header_value(headers, "not-found") is None
    assert processor.get_header_value([], ":method") is None


def test_get_tap_files(temp_directories, sample_tap_files):
    """Test getting tap files from directory."""
    processor = BatchProcessor(
        tap_folder=str(temp_directories["tap_folder"]),
        db_file=str(temp_directories["db_file"]),
        archive_folder=str(temp_directories["archive_folder"]),
    )

    tap_files = processor.get_tap_files()

    # Should find the sample files
    assert len(tap_files) > 0
    assert len(tap_files) <= processor.max_files_per_batch

    # All files should be JSON files
    for file in tap_files:
        assert file.endswith(".json")
        assert os.path.exists(file)


def test_create_batch(temp_directories, sample_tap_files):
    """Test batch creation."""
    processor = BatchProcessor(
        tap_folder=str(temp_directories["tap_folder"]),
        db_file=str(temp_directories["db_file"]),
        archive_folder=str(temp_directories["archive_folder"]),
    )

    # Use sample files as string paths (processor expects strings)
    tap_files = [str(f) for f in sample_tap_files[:3]]
    batch_id = processor.create_batch_id(tap_files)

    assert batch_id is not None
    assert isinstance(batch_id, str)

    # Verify batch was recorded in database
    conn = sqlite3.connect(str(temp_directories["db_file"]))
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM batches WHERE batch_id = ?", (batch_id,))
    batch_record = cursor.fetchone()
    assert batch_record is not None
    assert batch_record[3] == len(tap_files)  # tap_count

    # Verify taps were recorded
    cursor.execute("SELECT * FROM taps WHERE batch_id = ?", (batch_id,))
    tap_records = cursor.fetchall()
    assert len(tap_records) == len(tap_files)

    conn.close()


def test_process_tap_file(temp_directories, sample_tap_files):
    """Test processing individual tap file."""
    processor = BatchProcessor(
        tap_folder=str(temp_directories["tap_folder"]),
        db_file=str(temp_directories["db_file"]),
        archive_folder=str(temp_directories["archive_folder"]),
    )

    # Process one sample file
    tap_file = sample_tap_files[0]
    tap_id = tap_file.stem
    batch_id = "test_batch_123"

    processor.process_tap_file(str(tap_file), tap_id, batch_id)

    # Verify request was recorded
    conn = sqlite3.connect(str(temp_directories["db_file"]))
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM requests WHERE tap_id = ? AND batch_id = ?", (tap_id, batch_id))
    requests = cursor.fetchall()

    assert len(requests) == 1
    request = requests[0]

    # Verify basic request data
    assert request[1] == tap_id  # tap_id
    assert request[2] == batch_id  # batch_id
    assert request[4] in ["GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS"]  # method
    assert request[5].startswith("/")  # path starts with /

    conn.close()


def test_archive_batch(temp_directories, sample_tap_files):
    """Test batch archiving functionality."""
    processor = BatchProcessor(
        tap_folder=str(temp_directories["tap_folder"]),
        db_file=str(temp_directories["db_file"]),
        archive_folder=str(temp_directories["archive_folder"]),
    )

    # Use first 2 sample files
    tap_files = [str(f) for f in sample_tap_files[:2]]
    batch_id = "test_archive_batch"

    archive_file = processor.archive_batch(batch_id, tap_files)

    # Verify archive file was created
    assert os.path.exists(archive_file)
    assert archive_file.endswith(".tar.gz")
    assert batch_id in archive_file

    # Verify archive contains expected files
    import tarfile

    with tarfile.open(archive_file, "r:gz") as tar:
        members = tar.getnames()
        assert len(members) == len(tap_files)

        # Check that archived files match original basenames
        original_names = [os.path.basename(f) for f in tap_files]
        for member in members:
            assert member in original_names


def test_process_batch_integration(temp_directories, sample_tap_files):
    """Test full batch processing workflow."""
    processor = BatchProcessor(
        tap_folder=str(temp_directories["tap_folder"]),
        db_file=str(temp_directories["db_file"]),
        archive_folder=str(temp_directories["archive_folder"]),
    )

    # Verify original test data still exists (safety check)
    test_data_dir = Path(__file__).parent.parent / "data"
    original_count = len([f for f in test_data_dir.iterdir() if f.suffix == ".json"])

    # Process batch
    tap_files = [str(f) for f in sample_tap_files[:3]]
    batch_id = processor.create_batch_id(tap_files)
    processed_count = processor.process_batch(batch_id, tap_files)

    assert processed_count == len(tap_files)

    # Verify files were moved to archive (deleted from tap folder)
    for file in tap_files:
        assert not os.path.exists(file), f"File {file} should have been deleted"

    # Verify archive was created
    archive_files = list(temp_directories["archive_folder"].iterdir())
    assert len(archive_files) == 1
    assert archive_files[0].suffix == ".gz"

    # Verify database records
    conn = sqlite3.connect(str(temp_directories["db_file"]))
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM batches WHERE batch_id = ?", (batch_id,))
    batch_count = cursor.fetchone()[0]
    assert batch_count == 1

    cursor.execute("SELECT COUNT(*) FROM taps WHERE batch_id = ?", (batch_id,))
    tap_count = cursor.fetchone()[0]
    assert tap_count == len(tap_files)

    cursor.execute("SELECT COUNT(*) FROM requests WHERE batch_id = ?", (batch_id,))
    request_count = cursor.fetchone()[0]
    assert request_count == len(tap_files)  # Should have one request per tap file

    conn.close()

    # Verify original test data is intact (safety check)
    final_count = len([f for f in test_data_dir.iterdir() if f.suffix == ".json"])
    assert final_count == original_count, "Original test data was modified!"
