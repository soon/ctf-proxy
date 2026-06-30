import time

import pytest
import requests
from common import https_request, request, tcp_roundtrip


def wait_for_http(timeout):
    print("Checking if Envoy (HTTP) is ready...")
    for i in range(timeout):
        try:
            response = request("GET", "/bypass", timeout=1)
            if response.status_code == 200:
                return
        except requests.RequestException:
            pass

        if i == timeout - 1:
            pytest.fail(f"Envoy (HTTP) failed to start within {timeout} seconds")

        time.sleep(1)


def wait_for_tcp(timeout):
    print("Checking if Envoy (TCP) is ready...")
    for i in range(timeout):
        try:
            if tcp_roundtrip(b"ready\n") == b"ready\n":
                return
        except OSError:
            pass

        if i == timeout - 1:
            pytest.fail(f"Envoy (TCP) failed to start within {timeout} seconds")

        time.sleep(1)


def wait_for_https(timeout):
    print("Checking if Envoy (HTTPS) is ready...")
    for i in range(timeout):
        try:
            response = https_request("GET", "/bypass", timeout=1)
            if response.status_code == 200:
                return
        except requests.RequestException:
            pass

        if i == timeout - 1:
            pytest.fail(f"Envoy (HTTPS) failed to start within {timeout} seconds")

        time.sleep(1)


def pytest_sessionstart(session):
    wait_for_http(30)
    wait_for_tcp(30)
    wait_for_https(30)
