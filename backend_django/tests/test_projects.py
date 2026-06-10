import pytest
from django.contrib.auth.hashers import make_password
from rest_framework import status

from apps.core.models import Project, Task, TaskWarning, UserAccount


@pytest.mark.django_db
class TestProjects:
    def test_list_projects_requires_auth(self, api_client):
        resp = api_client.get("/api/projects/")
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_list_projects_empty(self, api_client, regular_user, auth_headers):
        resp = api_client.get("/api/projects/", **auth_headers)
        assert resp.status_code == status.HTTP_200_OK
        # The endpoint returns a plain list (no pagination); tolerate both shapes.
        results = resp.data if isinstance(resp.data, list) else resp.data["results"]
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
        # The endpoint returns a plain list (no pagination); tolerate both shapes.
        results = resp.data if isinstance(resp.data, list) else resp.data["results"]
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

    def test_ai_fix_prompt_returns_active_warnings_and_prompt(self, api_client, auth_headers):
        project_resp = api_client.post(
            "/api/projects/",
            {"name": "AI Prompt Project"},
            format="json",
            **auth_headers,
        )
        pid = project_resp.data["id_project"]

        task_resp = api_client.post(
            "/api/tasks/",
            {"title": "Fix login flow", "description": "Corregir fallos de autenticación", "project": pid},
            format="json",
            **auth_headers,
        )
        tid = task_resp.data["id_task"]
        task = Task.objects.get(pk=tid)

        TaskWarning.objects.create(task=task, message="Falta validar JWT expirado", severity="critical", status="active")
        TaskWarning.objects.create(task=task, message="No hay test para refresh token", severity="warning", status="active")
        TaskWarning.objects.create(task=task, message="Issue ya resuelto", severity="info", status="resolved")

        resp = api_client.get(f"/api/tasks/{tid}/ai-fix-prompt/", **auth_headers)

        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["task_id"] == tid
        assert resp.data["warnings_count"] == 2
        assert len(resp.data["warnings"]) == 2
        assert "Falta validar JWT expirado" in resp.data["copy_prompt"]
        assert "No hay test para refresh token" in resp.data["copy_prompt"]

    def test_ai_fix_prompt_hidden_for_non_member(self, api_client, auth_headers):
        project_resp = api_client.post(
            "/api/projects/",
            {"name": "Private Prompt Project"},
            format="json",
            **auth_headers,
        )
        pid = project_resp.data["id_project"]

        task_resp = api_client.post(
            "/api/tasks/",
            {"title": "Private Task", "project": pid},
            format="json",
            **auth_headers,
        )
        tid = task_resp.data["id_task"]

        other = UserAccount.objects.create(
            email="other3@test.com",
            username="other3",
            password_hash=make_password("pass123456"),
        )
        login = api_client.post(
            "/api/auth/login/",
            {"email": other.email, "password": "pass123456"},
            format="json",
        )
        other_token = login.data["access_token"]

        resp = api_client.get(
            f"/api/tasks/{tid}/ai-fix-prompt/",
            HTTP_AUTHORIZATION=f"Bearer {other_token}",
        )
        assert resp.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestProjectRisk:
    """GET /api/projects/{id}/risk/ — proxy autenticado al servicio ML de FastAPI."""

    def _create_project(self, api_client, auth_headers, name="Riskful"):
        resp = api_client.post(
            "/api/projects/", {"name": name}, format="json", **auth_headers
        )
        return resp.data["id_project"]

    def test_risk_requires_auth(self, api_client, regular_user, auth_headers):
        pid = self._create_project(api_client, auth_headers)
        resp = api_client.get(f"/api/projects/{pid}/risk/")
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_risk_hidden_for_non_member(self, api_client, regular_user, auth_headers):
        pid = self._create_project(api_client, auth_headers)

        other = UserAccount.objects.create(
            email="outsider@test.com",
            username="outsider",
            password_hash=make_password("pass123456"),
        )
        login = api_client.post(
            "/api/auth/login/",
            {"email": "outsider@test.com", "password": "pass123456"},
            format="json",
        )
        resp = api_client.get(
            f"/api/projects/{pid}/risk/",
            HTTP_AUTHORIZATION=f"Bearer {login.data['access_token']}",
        )
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_risk_proxies_prediction(self, api_client, regular_user, auth_headers, monkeypatch, settings):
        settings.FASTAPI_CHAT_BASE_URL = "http://fastapi.test"
        settings.FASTAPI_INTERNAL_TOKEN = "secret-token"
        pid = self._create_project(api_client, auth_headers)

        prediction = {
            "project_id": pid,
            "at_risk": True,
            "confidence": 0.4,
            "predicted_end_date": "2026-07-01",
            "days_delay_estimate": 9,
            "model_used": "elasticnet",
            "features": {},
        }
        captured = {}

        class FakeResponse:
            status_code = 200

            @staticmethod
            def json():
                return prediction

        def fake_post(url, json=None, headers=None, timeout=None):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return FakeResponse()

        monkeypatch.setattr("apps.core.views.requests.post", fake_post)

        resp = api_client.get(f"/api/projects/{pid}/risk/", **auth_headers)
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["at_risk"] is True
        assert resp.data["model_used"] == "elasticnet"
        assert captured["url"] == "http://fastapi.test/predictions/project-risk/"
        assert captured["json"] == {"project_id": pid}
        assert captured["headers"]["X-Internal-Token"] == "secret-token"

    def test_risk_maps_unpredictable_to_400(self, api_client, regular_user, auth_headers, monkeypatch, settings):
        settings.FASTAPI_CHAT_BASE_URL = "http://fastapi.test"
        pid = self._create_project(api_client, auth_headers)

        class FakeResponse:
            status_code = 404

            @staticmethod
            def json():
                return {"detail": "Project not found or has no tasks / end_date configured."}

        monkeypatch.setattr(
            "apps.core.views.requests.post", lambda *a, **k: FakeResponse()
        )

        resp = api_client.get(f"/api/projects/{pid}/risk/", **auth_headers)
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert resp.data["code"] == "not_predictable"
