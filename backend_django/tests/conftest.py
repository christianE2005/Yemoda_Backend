import pytest
from django.contrib.auth.hashers import make_password
from rest_framework.test import APIClient

from apps.core.models import UserAccount


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def regular_user(db):
    return UserAccount.objects.create(
        email="user@test.com",
        username="testuser",
        password_hash=make_password("password123"),
    )


@pytest.fixture
def admin_user(db):
    return UserAccount.objects.create(
        email="admin@test.com",
        username="adminuser",
        password_hash=make_password("adminpass123"),
        is_admin=True,
    )


@pytest.fixture
def auth_token(regular_user, api_client):
    resp = api_client.post(
        "/api/auth/login/",
        {"email": "user@test.com", "password": "password123"},
        format="json",
    )
    return resp.data["access_token"]


@pytest.fixture
def auth_headers(auth_token):
    return {"HTTP_AUTHORIZATION": f"Bearer {auth_token}"}


@pytest.fixture
def admin_token(admin_user, api_client):
    resp = api_client.post(
        "/api/auth/login/",
        {"email": "admin@test.com", "password": "adminpass123"},
        format="json",
    )
    return resp.data["access_token"]


@pytest.fixture
def admin_headers(admin_token):
    return {"HTTP_AUTHORIZATION": f"Bearer {admin_token}"}
