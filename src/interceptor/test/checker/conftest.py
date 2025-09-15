import time

import pytest
import requests
from common import request


def pytest_sessionstart(session):
    timeout = 30
    print("Checking if Envoy is ready...")
    for i in range(timeout):
        try:
            response = request("GET", "/bypass", timeout=1)
            if response.status_code == 200:
                return True
        except requests.RequestException:
            pass

        if i == timeout - 1:
            pytest.fail(f"Envoy failed to start within {timeout} seconds")

        time.sleep(1)

    return False
