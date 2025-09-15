import os

import requests


def get_base_url() -> str:
    if os.getenv("CI") == "true":
        return "http://envoy:15001"
    else:
        return "http://localhost:15001"


def request(method: str, path: str, **kwargs):
    base_url = get_base_url()
    url = f"{base_url}{path}"
    return requests.request(method, url, **kwargs)
