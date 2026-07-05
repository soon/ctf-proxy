import pytest
import requests
from common import request

DEFAULT_HEADERS = frozenset({"server", "date", "content-type", "content-length"})
MODIFIED_HEADERS = frozenset({"server", "date", "content-type", "transfer-encoding"})


def assert_headers(response, expected_headers):
    assert {k.lower() for k in response.headers.keys()} == expected_headers


def test_bypass_not_intercepted():
    response = request("GET", "/bypass", timeout=5)
    assert response.status_code == 200
    assert_headers(response, DEFAULT_HEADERS)


def test_blocked():
    response = request("GET", "/blocked", timeout=5)
    assert response.status_code == 418
    assert response.text == "hey you"
    assert_headers(response, DEFAULT_HEADERS)


def test_blocked_as_prefix():
    response = request("POST", "/blocked-just-a-prefix", timeout=5)
    assert response.status_code == 418
    assert response.text == "hey you"
    assert_headers(response, DEFAULT_HEADERS)


def test_paused():
    with pytest.raises(requests.ReadTimeout):
        request("GET", "/paused", timeout=2)


def test_modified():
    response = request("GET", "/modified", timeout=5)
    assert response.status_code == 200
    assert response.text == "TEST BACKEND RESPONSE\n"
    assert_headers(response, MODIFIED_HEADERS)


def test_replaced():
    response = request("GET", "/replaced", timeout=5)
    assert response.status_code == 200
    assert response.text == "new response body"
    assert_headers(response, MODIFIED_HEADERS)
