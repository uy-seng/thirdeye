from __future__ import annotations


def test_browser_dashboard_route_is_removed(client) -> None:
    response = client.get("/", follow_redirects=False)

    assert response.status_code == 404


def test_browser_login_route_is_removed(client) -> None:
    response = client.post(
        "/login",
        data={"username": "operator", "password": "secret-pass"},
        follow_redirects=False,
    )

    assert response.status_code == 404


def test_json_login_sets_session(client) -> None:
    response = client.post(
        "/api/session/login",
        json={"username": "operator", "password": "secret-pass"},
    )

    assert response.status_code == 200
    assert response.json() == {"authenticated": True, "username": "operator"}
