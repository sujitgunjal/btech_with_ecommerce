from tests.conftest import auth_header


def test_register_login_and_reject_bad_password(client):
    created = client.post(
        "/auth/register",
        json={"email": "ada@northline.shop", "password": "correct-horse", "full_name": "Ada Lopes"},
    )
    assert created.status_code == 201
    token = created.json()["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "ada@northline.shop"

    duplicate = client.post(
        "/auth/register",
        json={"email": "ada@northline.shop", "password": "correct-horse", "full_name": "Ada Lopes"},
    )
    assert duplicate.status_code == 409

    bad = client.post("/auth/login", json={"email": "ada@northline.shop", "password": "wrong-password"})
    assert bad.status_code == 401
    assert client.get("/auth/me").status_code == 401


def test_profile_update_and_password_change(client):
    headers = auth_header(client)
    updated = client.patch(
        "/profile",
        headers=headers,
        json={
            "full_name": "Demo Buyer",
            "phone": "555",
            "address_line": "9 River Road",
            "city": "Porto",
            "postal_code": "4000-001",
            "country": "Portugal",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["city"] == "Porto"
    changed = client.post(
        "/profile/password",
        headers=headers,
        json={"current_password": "DemoPass123!", "new_password": "DemoPass123!"},
    )
    assert changed.status_code == 400
    changed = client.post(
        "/profile/password",
        headers=headers,
        json={"current_password": "DemoPass123!", "new_password": "AnotherPass1"},
    )
    assert changed.status_code == 204
    assert client.post(
        "/auth/login", json={"email": "demo@northline.shop", "password": "AnotherPass1"}
    ).status_code == 200
