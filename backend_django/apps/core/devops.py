import os
import requests
import hmac
import hashlib
from urllib.parse import urlencode
from django.conf import settings

CLIENT_ID = os.getenv("AZURE_CLIENT_ID") or getattr(settings, "AZURE_CLIENT_ID", None)
CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET") or getattr(settings, "AZURE_CLIENT_SECRET", None)
REDIRECT_URI = os.getenv("AZURE_REDIRECT_URI") or getattr(settings, "AZURE_REDIRECT_URI", None)

SCOPES = "vso.work vso.work_write vso.serviceendpoint_manage offline_access"

AUTHORIZE_URL = "https://app.vssps.visualstudio.com/oauth2/authorize"
TOKEN_URL = "https://app.vssps.visualstudio.com/oauth2/token"
BASE_URL = "https://dev.azure.com"

DEVOPS_WEBHOOK_SECRET = os.getenv("DEVOPS_WEBHOOK_SECRET") or getattr(settings, "DEVOPS_WEBHOOK_SECRET", "")
DEVOPS_WEBHOOK_TARGET_URL = os.getenv("DEVOPS_WEBHOOK_TARGET_URL") or getattr(
    settings, "DEVOPS_WEBHOOK_TARGET_URL", ""
)


def get_auth_url(state: str) -> str:
    params = {
        "client_id": CLIENT_ID,
        "response_type": "Assertion",
        "state": state,
        "scope": SCOPES,
        "redirect_uri": REDIRECT_URI,
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


def exchange_code_for_token(code: str) -> dict:
    """Intercambia el código de autorización por access + refresh token (síncrono)."""
    resp = requests.post(
        TOKEN_URL,
        data={
            "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
            "client_assertion": CLIENT_SECRET,
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": code,
            "redirect_uri": REDIRECT_URI,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def refresh_access_token(refresh_token: str) -> dict:
    resp = requests.post(
        TOKEN_URL,
        data={
            "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
            "client_assertion": CLIENT_SECRET,
            "grant_type": "refresh_token",
            "assertion": refresh_token,
            "redirect_uri": REDIRECT_URI,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


class DevOpsClient:
    def __init__(self, access_token: str, organization: str):
        self.token = access_token
        self.org = organization
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

    def get_projects(self) -> list:
        url = f"{BASE_URL}/{self.org}/_apis/projects?api-version=7.1"
        resp = requests.get(url, headers=self.headers, timeout=30)
        resp.raise_for_status()
        return resp.json().get("value", [])

    def get_user_stories(self, project: str, assigned_to_me: bool = True) -> list:
        wiql_url = f"{BASE_URL}/{self.org}/{project}/_apis/wit/wiql?api-version=7.1"

        where_clause = (
            "WHERE [System.WorkItemType] = 'User Story' AND [System.AssignedTo] = @Me"
            if assigned_to_me
            else "WHERE [System.WorkItemType] = 'User Story'"
        )

        wiql_resp = requests.post(
            wiql_url,
            json={"query": f"SELECT [Id] FROM WorkItems {where_clause} ORDER BY [System.CreatedDate] DESC"},
            headers=self.headers,
            timeout=30,
        )
        wiql_resp.raise_for_status()
        work_items = wiql_resp.json().get("workItems", [])

        if not work_items:
            return []

        ids = ",".join(str(item["id"]) for item in work_items[:200])
        fields = (
            "System.Id,System.Title,System.State,System.AssignedTo,System.Description,"
            "Microsoft.VSTS.Scheduling.StoryPoints,System.IterationPath"
        )
        detail_url = f"{BASE_URL}/{self.org}/{project}/_apis/wit/workitems?ids={ids}&fields={fields}&api-version=7.1"
        detail_resp = requests.get(detail_url, headers=self.headers, timeout=30)
        detail_resp.raise_for_status()
        return detail_resp.json().get("value", [])

    def get_all_user_stories(self) -> dict:
        projects = self.get_projects()
        result = {}
        for project in projects:
            project_name = project.get("name")
            if not project_name:
                continue
            try:
                stories = self.get_user_stories(project_name, assigned_to_me=False)
            except Exception:
                stories = []
            result[project_name] = stories
        return result


EVENTS = [
    "workitem.created",
    "workitem.updated",
    "workitem.deleted",
    "workitem.commented",
]


def register_webhooks(access_token: str, organization: str, project_id: str, user_id: str, target_url: str | None = None) -> list:
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    url = f"{BASE_URL}/{organization}/_apis/hooks/subscriptions?api-version=7.1"
    subscriptions = []
    target = target_url or DEVOPS_WEBHOOK_TARGET_URL

    for event in EVENTS:
        payload = {
            "publisherId": "tfs",
            "eventType": event,
            "resourceVersion": "1.0",
            "consumerId": "webHooks",
            "consumerActionId": "httpRequest",
            "publisherInputs": {
                "projectId": project_id,
                **({"workItemType": "User Story"} if "workitem" in event else {}),
            },
            "consumerInputs": {
                "url": f"{target.rstrip('/')}/{user_id}",
                "httpHeaders": f"X-Secret: {DEVOPS_WEBHOOK_SECRET}",
            },
        }

        res = requests.post(url, json=payload, headers=headers, timeout=30)
        if res.status_code in (200, 201):
            subscriptions.append(res.json().get("id"))

    return subscriptions


def delete_webhooks(access_token: str, organization: str, subscription_ids: list):
    headers = {"Authorization": f"Bearer {access_token}"}
    with requests.Session() as s:
        for sid in subscription_ids:
            url = f"{BASE_URL}/{organization}/_apis/hooks/subscriptions/{sid}?api-version=7.1"
            s.delete(url, headers=headers, timeout=30)


def validate_webhook_secret(request_secret: str) -> bool:
    return hmac.compare_digest((request_secret or "").strip(), DEVOPS_WEBHOOK_SECRET)
