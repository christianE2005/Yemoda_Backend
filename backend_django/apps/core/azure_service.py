"""Synchronous Azure DevOps helper for Django.

Minimal client using `requests` to list projects, run WIQL and fetch workitems.
This is a prototype used by the Django endpoints that manage external connections.
"""
from __future__ import annotations

import base64
from typing import Any, Dict, List

import requests

API_VERSION = "7.2"


def _auth_header_from_pat(pat: str) -> Dict[str, str]:
    token = base64.b64encode(f":{pat}".encode()).decode()
    return {"Authorization": f"Basic {token}", "Accept": "application/json"}


def list_projects(organization: str, pat: str) -> List[Dict[str, Any]]:
    url = f"https://dev.azure.com/{organization}/_apis/projects?api-version={API_VERSION}"
    resp = requests.get(url, headers=_auth_header_from_pat(pat), timeout=20)
    resp.raise_for_status()
    data = resp.json()
    return data.get("value", [])


def run_wiql(organization: str, project: str, pat: str, query: str) -> Dict[str, Any]:
    url = f"https://dev.azure.com/{organization}/{project}/_apis/wit/wiql?api-version={API_VERSION}"
    resp = requests.post(url, headers=_auth_header_from_pat(pat), json={"query": query}, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_workitems_by_ids(organization: str, ids: List[int], pat: str) -> List[Dict[str, Any]]:
    if not ids:
        return []
    ids_str = ",".join(str(i) for i in ids)
    url = f"https://dev.azure.com/{organization}/_apis/wit/workitems?ids={ids_str}&$expand=all&api-version={API_VERSION}"
    resp = requests.get(url, headers=_auth_header_from_pat(pat), timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data.get("value", [])


def fetch_workitems_for_project(
    organization: str,
    project: str,
    pat: str,
    work_item_types: List[str] | None = None,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    if work_item_types:
        types_clause = "AND [System.WorkItemType] IN (" + ",".join(f"'{t}'" for t in work_item_types) + ")"
    else:
        types_clause = "AND [System.WorkItemType] IN ('User Story','Product Backlog Item','Bug')"

    wiql = (
        "SELECT [System.Id] FROM WorkItems "
        "WHERE [System.TeamProject] = @project "
        f"{types_clause} "
        "ORDER BY [System.ChangedDate] DESC"
    )

    wiql_result = run_wiql(organization, project, pat, wiql)
    items = wiql_result.get("workItems", []) or []
    ids = [w.get("id") for w in items if w.get("id")]
    if not ids:
        return []

    if limit:
        ids = ids[:limit]

    raw_items = get_workitems_by_ids(organization, ids, pat)

    simplified: List[Dict[str, Any]] = []
    for wi in raw_items:
        fields = wi.get("fields", {})
        title = fields.get("System.Title")
        description = fields.get("System.Description") or ""
        acceptance = fields.get("Microsoft.VSTS.Common.AcceptanceCriteria") or ""
        assigned_to = fields.get("System.AssignedTo")
        if isinstance(assigned_to, dict):
            assignee = assigned_to.get("displayName") or assigned_to.get("uniqueName")
        else:
            assignee = assigned_to

        simplified.append(
            {
                "id": wi.get("id"),
                "url": wi.get("url"),
                "title": title,
                "description": description,
                "acceptance_criteria": acceptance,
                "assignee": assignee,
                "raw_fields": fields,
            }
        )

    return simplified
