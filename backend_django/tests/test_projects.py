import pytest
from django.contrib.auth.hashers import make_password
from rest_framework import status

from apps.core.models import Project, Task, UserAccount


@pytest.mark.django_db
class TestProjects:
    def test_list_projects_requires_auth(self, api_client):
        resp = api_client.get("/api/projects/")
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_list_projects_empty(self, api_client, regular_user, auth_headers):
        resp = api_client.get("/api/projects/", **auth_headers)
        assert resp.status_code == status.HTTP_200_OK
        results = resp.data.get("results", resp.data)
        assert len(results) == 0

    def test_create_project(self, api_client, regular_user, auth_headers):
        resp = api_client.post(
            "/api/projects/",
            {"name": "My Project", "description": "Test"},
            format="json",
            **auth_headers,
        )
        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.data["name"] == "My Project"
        assert resp.data["created_by"] == regular_user.id_user

    def test_create_project_missing_name(self, api_client, auth_headers):
        resp = api_client.post(
            "/api/projects/",
            {"description": "No name"},
            format="json",
            **auth_headers,
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_retrieve_own_project(self, api_client, regular_user, auth_headers):
        create = api_client.post(
            "/api/projects/",
            {"name": "Project A"},
            format="json",
            **auth_headers,
        )
        pid = create.data["id_project"]

        resp = api_client.get(f"/api/projects/{pid}/", **auth_headers)
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["name"] == "Project A"

    def test_other_user_cannot_see_project(self, api_client, regular_user, auth_headers):
        create = api_client.post(
            "/api/projects/",
            {"name": "Private Project"},
            format="json",
            **auth_headers,
        )
        pid = create.data["id_project"]

        other = UserAccount.objects.create(
            email="other@test.com",
            username="other",
            password_hash=make_password("pass123456"),
        )
        login = api_client.post(
            "/api/auth/login/",
            {"email": "other@test.com", "password": "pass123456"},
            format="json",
        )
        other_token = login.data["access_token"]

        resp = api_client.get(
            f"/api/projects/{pid}/",
            HTTP_AUTHORIZATION=f"Bearer {other_token}",
        )
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_update_project(self, api_client, regular_user, auth_headers):
        create = api_client.post(
            "/api/projects/",
            {"name": "Old Name"},
            format="json",
            **auth_headers,
        )
        pid = create.data["id_project"]

        resp = api_client.patch(
            f"/api/projects/{pid}/",
            {"name": "New Name"},
            format="json",
            **auth_headers,
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["name"] == "New Name"

    def test_delete_project(self, api_client, regular_user, auth_headers):
        create = api_client.post(
            "/api/projects/",
            {"name": "To Delete"},
            format="json",
            **auth_headers,
        )
        pid = create.data["id_project"]

        resp = api_client.delete(f"/api/projects/{pid}/", **auth_headers)
        assert resp.status_code == status.HTTP_204_NO_CONTENT
        assert not Project.objects.filter(pk=pid).exists()


@pytest.mark.django_db
class TestTasks:
    def test_list_tasks_requires_auth(self, api_client):
        resp = api_client.get("/api/tasks/")
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_create_task(self, api_client, regular_user, auth_headers):
        project = api_client.post(
            "/api/projects/",
            {"name": "Task Project"},
            format="json",
            **auth_headers,
        )
        pid = project.data["id_project"]

        resp = api_client.post(
            "/api/tasks/",
            {"title": "Test Task", "project": pid},
            format="json",
            **auth_headers,
        )
        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.data["title"] == "Test Task"
        assert resp.data["project"] == pid

    def test_list_tasks_only_own_projects(self, api_client, regular_user, auth_headers):
        project = api_client.post(
            "/api/projects/",
            {"name": "My Project"},
            format="json",
            **auth_headers,
        )
        pid = project.data["id_project"]
        api_client.post(
            "/api/tasks/",
            {"title": "My Task", "project": pid},
            format="json",
            **auth_headers,
        )

        other = UserAccount.objects.create(
            email="other2@test.com",
            username="other2",
            password_hash=make_password("pass123456"),
        )
        login = api_client.post(
            "/api/auth/login/",
            {"email": "other2@test.com", "password": "pass123456"},
            format="json",
        )
        other_token = login.data["access_token"]

        resp = api_client.get(
            "/api/tasks/",
            HTTP_AUTHORIZATION=f"Bearer {other_token}",
        )
        assert resp.status_code == status.HTTP_200_OK
        results = resp.data.get("results", resp.data)
        assert len(results) == 0

    def test_delete_task(self, api_client, regular_user, auth_headers):
        project = api_client.post(
            "/api/projects/",
            {"name": "Task Project"},
            format="json",
            **auth_headers,
        )
        pid = project.data["id_project"]
        task = api_client.post(
            "/api/tasks/",
            {"title": "To Delete", "project": pid},
            format="json",
            **auth_headers,
        )
        tid = task.data["id_task"]

        resp = api_client.delete(f"/api/tasks/{tid}/", **auth_headers)
        assert resp.status_code == status.HTTP_204_NO_CONTENT
        assert not Task.objects.filter(pk=tid).exists()
