import email
import email.policy
import gzip
import json
from typing import Any

import httpx
import pytest
import respx

from paprika_mcp.client import BASE_URL, PaprikaClient

API = BASE_URL


@pytest.fixture
def client() -> PaprikaClient:
    c = PaprikaClient(email="e", password="p", token_cache_path=None)
    c._token = "TOKEN"
    return c


@pytest.fixture
def mock_api():
    with respx.mock(assert_all_called=False) as router:
        yield router


def decode_upload(request: httpx.Request) -> Any:
    """Parse a multipart request, gunzip its `data` field, return the JSON."""
    content_type = request.headers["content-type"]
    raw = b"Content-Type: " + content_type.encode() + b"\r\n\r\n" + request.content
    msg = email.message_from_bytes(raw, policy=email.policy.HTTP)
    for part in msg.iter_parts():
        if part.get_param("name", header="content-disposition") == "data":
            return json.loads(gzip.decompress(part.get_payload(decode=True)))
    raise AssertionError("no 'data' field in multipart body")
