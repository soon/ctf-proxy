import pytest
import requests
from common import https_request


def test_https_bypass_not_intercepted():
    response = https_request("GET", "/bypass", timeout=5)
    assert response.status_code == 200
    assert response.text == "Test backend response\n"


def test_https_blocked():
    response = https_request("GET", "/blocked", timeout=5)
    assert response.status_code == 418
    assert response.text == "hey you"


def test_https_modified():
    response = https_request("GET", "/modified", timeout=5)
    assert response.status_code == 200
    assert response.text == "TEST BACKEND RESPONSE\n"


def test_https_replaced():
    response = https_request("GET", "/replaced", timeout=5)
    assert response.status_code == 200
    assert response.text == "new response body"


def test_https_paused():
    with pytest.raises(requests.ReadTimeout):
        https_request("GET", "/paused", timeout=2)
