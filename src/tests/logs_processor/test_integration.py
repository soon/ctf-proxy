# """Integration tests for complete workflows."""

# import os
# import sqlite3
# import tarfile

# from ctf_proxy.logs_processor.batch import BatchProcessor


# def test_complete_batch_workflow(temp_directories, sample_tap_files):
#     """Test the complete batch processing workflow."""
#     processor = BatchProcessor(
#         tap_folder=str(temp_directories["tap_folder"]),
#         db_file=str(temp_directories["db_file"]),
#         archive_folder=str(temp_directories["archive_folder"]),
#     )

#     # Get initial counts for verification
#     initial_tap_files = processor.get_tap_files()
#     initial_count = len(initial_tap_files)

#     assert initial_count > 0, "Should have sample tap files to process"

#     # Create and process batch
#     batch_id = processor.create_batch_id(initial_tap_files)
#     processed_count = processor.process_batch(batch_id, initial_tap_files)

#     assert processed_count == initial_count

#     # Verify database state
#     conn = sqlite3.connect(str(temp_directories["db_file"]))
#     cursor = conn.cursor()

#     # Check batch record
#     cursor.execute("SELECT * FROM batches WHERE batch_id = ?", (batch_id,))
#     batch_record = cursor.fetchone()
#     assert batch_record is not None
#     assert batch_record[0] == batch_id  # batch_id
#     assert batch_record[3] == initial_count  # tap_count
#     assert batch_record[4] is not None  # archive_file should be set

#     # Check tap records
#     cursor.execute("SELECT COUNT(*) FROM taps WHERE batch_id = ?", (batch_id,))
#     tap_count = cursor.fetchone()[0]
#     assert tap_count == initial_count

#     # Check request records
#     cursor.execute("SELECT COUNT(*) FROM requests WHERE batch_id = ?", (batch_id,))
#     request_count = cursor.fetchone()[0]
#     assert request_count == initial_count

#     # Verify tap-to-batch mapping
#     cursor.execute("SELECT tap_id, batch_id FROM taps WHERE batch_id = ?", (batch_id,))
#     mappings = cursor.fetchall()
#     assert len(mappings) == initial_count

#     for tap_id, mapped_batch_id in mappings:
#         assert mapped_batch_id == batch_id
#         assert tap_id is not None
#         assert len(tap_id) > 0

#     conn.close()

#     # Verify archive file
#     archive_files = list(temp_directories["archive_folder"].iterdir())
#     assert len(archive_files) == 1

#     archive_file = archive_files[0]
#     assert archive_file.suffix == ".gz"
#     assert batch_id in archive_file.name

#     # Verify archive contents
#     with tarfile.open(archive_file, "r:gz") as tar:
#         archived_names = tar.getnames()
#         assert len(archived_names) == initial_count

#     # Verify original tap files were cleaned up
#     remaining_tap_files = processor.get_tap_files()
#     assert len(remaining_tap_files) == 0, "All tap files should be processed and removed"


# def test_batch_to_archive_mapping(temp_directories, sample_tap_files):
#     """Test that tap_id to batch_id mapping works correctly for archive retrieval."""
#     processor = BatchProcessor(
#         tap_folder=str(temp_directories["tap_folder"]),
#         db_file=str(temp_directories["db_file"]),
#         archive_folder=str(temp_directories["archive_folder"]),
#     )

#     # Process files
#     tap_files = [str(f) for f in sample_tap_files[:3]]
#     batch_id = processor.create_batch_id(tap_files)
#     processor.process_batch(batch_id, tap_files)

#     # Verify we can retrieve batch info for any tap_id
#     conn = sqlite3.connect(str(temp_directories["db_file"]))
#     cursor = conn.cursor()

#     cursor.execute("SELECT tap_id FROM taps WHERE batch_id = ?", (batch_id,))
#     tap_ids = [row[0] for row in cursor.fetchall()]

#     assert len(tap_ids) == 3

#     # For each tap_id, we should be able to find its batch and archive
#     for tap_id in tap_ids:
#         cursor.execute(
#             """
#             SELECT b.batch_id, b.archive_file
#             FROM taps t
#             JOIN batches b ON t.batch_id = b.batch_id
#             WHERE t.tap_id = ?
#         """,
#             (tap_id,),
#         )

#         result = cursor.fetchone()
#         assert result is not None

#         found_batch_id, archive_file = result
#         assert found_batch_id == batch_id
#         assert archive_file is not None
#         assert os.path.exists(archive_file)

#     conn.close()


# def test_stats_generation(temp_directories, sample_tap_files):
#     """Test that processing generates appropriate statistics."""
#     processor = BatchProcessor(
#         tap_folder=str(temp_directories["tap_folder"]),
#         db_file=str(temp_directories["db_file"]),
#         archive_folder=str(temp_directories["archive_folder"]),
#     )

#     # Process files
#     tap_files = [str(f) for f in sample_tap_files]
#     batch_id = processor.create_batch_id(tap_files)
#     processor.process_batch(batch_id, tap_files)

#     # Check that stats tables have data
#     conn = sqlite3.connect(str(temp_directories["db_file"]))
#     cursor = conn.cursor()

#     # Should have path stats
#     cursor.execute("SELECT COUNT(*) FROM path_stats")
#     path_stats_count = cursor.fetchone()[0]
#     assert path_stats_count > 0

#     # Should have method stats
#     cursor.execute("SELECT COUNT(*) FROM method_stats")
#     method_stats_count = cursor.fetchone()[0]
#     assert method_stats_count > 0

#     # Should have status stats
#     cursor.execute("SELECT COUNT(*) FROM status_stats")
#     status_stats_count = cursor.fetchone()[0]
#     assert status_stats_count > 0

#     # Verify some basic data integrity
#     cursor.execute("SELECT method, count FROM method_stats")
#     method_stats = cursor.fetchall()

#     for method, count in method_stats:
#         assert method in ["GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS"]
#         assert count > 0

#     conn.close()


# def test_empty_tap_folder(temp_directories):
#     """Test behavior when tap folder is empty."""
#     # Remove all sample files to simulate empty folder
#     for file in temp_directories["tap_folder"].iterdir():
#         file.unlink()

#     processor = BatchProcessor(
#         tap_folder=str(temp_directories["tap_folder"]),
#         db_file=str(temp_directories["db_file"]),
#         archive_folder=str(temp_directories["archive_folder"]),
#     )

#     tap_files = processor.get_tap_files()
#     assert len(tap_files) == 0


# def test_max_files_per_batch_limit(temp_directories, test_data_dir):
#     """Test that max files per batch is respected."""
#     processor = BatchProcessor(
#         tap_folder=str(temp_directories["tap_folder"]),
#         db_file=str(temp_directories["db_file"]),
#         archive_folder=str(temp_directories["archive_folder"]),
#     )

#     # Set a low limit for testing
#     processor.max_files_per_batch = 2

#     # Copy more files than the limit
#     data_files = list(test_data_dir.iterdir())[:5]  # Get 5 files
#     for i, data_file in enumerate(data_files):
#         if data_file.suffix == ".json":
#             dest_file = temp_directories["tap_folder"] / f"test_{i}.json"
#             dest_file.write_text(data_file.read_text())

#     tap_files = processor.get_tap_files()

#     # Should respect the limit
#     assert len(tap_files) <= processor.max_files_per_batch
#     assert len(tap_files) == 2  # Our set limit
