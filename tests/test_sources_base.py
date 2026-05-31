from stock_dashboard.engine.sources import base


def test_http_get_json_success(mocker):
    resp = mocker.Mock(status_code=200)
    resp.json.return_value = {"ok": True}
    mocker.patch("requests.get", return_value=resp)
    assert base.http_get_json("http://x") == {"ok": True}


def test_http_get_json_non_200_returns_none(mocker):
    resp = mocker.Mock(status_code=429)
    mocker.patch("requests.get", return_value=resp)
    assert base.http_get_json("http://x") is None


def test_http_get_json_exception_returns_none(mocker):
    mocker.patch("requests.get", side_effect=Exception("boom"))
    assert base.http_get_json("http://x") is None
