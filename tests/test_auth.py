import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db import SessionLocal
from app.models import User

client = TestClient(app)

TEST_EMAIL = "testuser@example.com"
TEST_PASSWORD = "s3cur3passw0rd"


def teardown_module(module):
    # cleanup user if exists
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email == TEST_EMAIL.lower()).one_or_none()
        if u:
            db.delete(u)
            db.commit()
    finally:
        db.close()


def test_register_and_login():
    # register
    resp = client.post("/auth/register", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    assert resp.status_code in (200, 201)
    data = resp.json()
    assert "id" in data and "email" in data
    assert data["email"] == TEST_EMAIL.lower()
    assert "created_at" in data

    # duplicate register -> 409
    resp2 = client.post("/auth/register", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    assert resp2.status_code == 409

    # login
    resp3 = client.post("/auth/login", data={"username": TEST_EMAIL, "password": TEST_PASSWORD})
    assert resp3.status_code == 200
    token_data = resp3.json()
    assert "access_token" in token_data and token_data["token_type"] == "bearer"

    # me without token -> 401
    r = client.get("/auth/me")
    assert r.status_code == 401

    # me with token -> 200
    headers = {"Authorization": f"Bearer {token_data['access_token']}"}
    r2 = client.get("/auth/me", headers=headers)
    assert r2.status_code == 200
    me = r2.json()
    assert me["email"] == TEST_EMAIL.lower()