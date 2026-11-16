import httpx

from tests.conftest import API, decode_upload


def test_post_gzip_sends_gzipped_json_in_data_field(client, mock_api):
    route = mock_api.post(f"{API}/v2/sync/groceries/").mock(
        return_value=httpx.Response(200, json={"result": True})
    )

    result = client._post_gzip("/v2/sync/groceries/", [{"a": 1}])

    assert result == {"result": True}
    request = route.calls[0].request
    assert request.headers["Authorization"] == "Bearer TOKEN"
    assert decode_upload(request) == [{"a": 1}]


def test_notify_ignores_errors(client, mock_api):
    route = mock_api.post(f"{API}/v2/sync/notify/").mock(return_value=httpx.Response(500))

    client.notify()  # must not raise

    assert route.called
