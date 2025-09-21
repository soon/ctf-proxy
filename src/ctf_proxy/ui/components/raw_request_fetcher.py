import json
import os
import tarfile

from ctf_proxy.db import ProxyStatsDB


def fetch_raw_request(
    request_id: int, db: ProxyStatsDB, archive_folder: str = "/var/log/envoy/archive"
) -> dict | None:
    """
    Fetch raw JSON for a request by:
    1. Getting batch_id and tap_id from database
    2. Finding the archive file for that batch
    3. Extracting the JSON file from the archive
    """
    with db.connect() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT batch_id, tap_id FROM http_request WHERE id = ?", (request_id,))
        result = cursor.fetchone()

        if not result:
            return None

        batch_id, tap_id = result

        if not batch_id or not tap_id:
            return None

    archive_file = os.path.join(archive_folder, f"{batch_id}.tar.gz")

    if not os.path.exists(archive_file):
        return {"error": f"Archive file not found: {archive_file}"}

    tap_filename = f"{tap_id}.json"

    try:
        with tarfile.open(archive_file, "r:gz") as tar:
            try:
                member = tar.getmember(tap_filename)
                extracted_file = tar.extractfile(member)
                if extracted_file:
                    json_content = extracted_file.read().decode("utf-8")
                    return json.loads(json_content)
            except KeyError:
                available_files = tar.getnames()
                return {
                    "error": f"File {tap_filename} not found in archive",
                    "available_files": available_files[:10],
                }
    except Exception as e:
        return {"error": f"Error reading archive: {str(e)}"}

    return None
