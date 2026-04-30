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


def test_json_session_routes_are_removed(client) -> None:
    assert client.get("/api/session", follow_redirects=False).status_code == 404
    assert client.post("/api/session/login", json={"username": "operator", "password": "secret-pass"}).status_code == 404
    assert client.post("/api/session/logout").status_code == 404
