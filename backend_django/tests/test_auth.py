import pytest
from rest_framework import status


@pytest.mark.django_db
class TestLogin:
    def test_login_success(self, api_client, regular_user):
        resp = api_client.post(
            "/api/auth/login/",
            {"email": "user@test.com", "password": "password123"},
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK
        assert "access_token" in resp.data
        assert "refresh_token" in resp.data
        assert resp.data["user"]["email"] == "user@test.com"

    def test_login_wrong_password(self, api_client, regular_user):
        resp = api_client.post(
            "/api/auth/login/",
            {"email": "user@test.com", "password": "wrongpass"},
            format="json",
        )
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_login_nonexistent_user(self, api_client):
        resp = api_client.post(
            "/api/auth/login/",
            {"email": "ghost@test.com", "password": "password123"},
            format="json",
        )
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_login_missing_fields(self, api_client):
        resp = api_client.post("/api/auth/login/", {}, format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestRefresh:
    def test_refresh_success(self, api_client, regular_user):
        login = api_client.post(
            "/api/auth/login/",
            {"email": "user@test.com", "password": "password123"},
            format="json",
        )
        refresh_token = login.data["refresh_token"]

        resp = api_client.post(
            "/api/auth/refresh/",
            {"refresh_token": refresh_token},
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK
        assert "access_token" in resp.data

    def test_refresh_invalid_token(self, api_client):
        resp = api_client.post(
            "/api/auth/refresh/",
            {"refresh_token": "invalid.token.value"},
            format="json",
        )
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_refresh_using_access_token_fails(self, api_client, regular_user):
        """Un access_token no debe funcionar como refresh_token."""
        login = api_client.post(
            "/api/auth/login/",
            {"email": "user@test.com", "password": "password123"},
            format="json",
        )
        access_token = login.data["access_token"]

        resp = api_client.post(
            "/api/auth/refresh/",
            {"refresh_token": access_token},
            format="json",
        )
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED
