import pytest
import requests
from common import request


def test_bypass_not_intercepted():
    response = request("GET", "/bypass", timeout=5)
    assert response.status_code == 200


def test_blocked():
    response = request("GET", "/blocked", timeout=5)
    assert response.status_code == 418
    assert "hey you" in response.text


def test_blocked_as_prefix():
    response = request("POST", "/blocked-just-a-prefix", timeout=5)
    assert response.status_code == 418
    assert "hey you" in response.text


def test_paused():
    with pytest.raises(requests.ReadTimeout):
        request("GET", "/paused", timeout=2)


def test_modified():
    response = request("GET", "/modified", timeout=5)
    assert response.status_code == 200
    assert response.text == "TEST BACKEND RESPONSE\n"


def test_replaced():
    response = request("GET", "/replaced", timeout=5)
    assert response.status_code == 200
    assert response.text == "new response body"
