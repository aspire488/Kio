"""MCP GitHub Server — GitHub API operations.

Run: python -m mini_kio.core.mcp.servers.mcp_github_server

Requires: pip install PyGithub

Tools:
  github_search_repos   — search repositories
  github_get_repo       — get repository info
  github_list_issues    — list issues
  github_create_issue   — create issue
  github_list_prs       — list pull requests
  github_get_contents   — get file contents
  github_list_branches  — list branches
  github_list_commits   — list recent commits
  github_create_gist    — create a gist
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

logger = logging.getLogger(__name__)

_GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")


def _get_client():
    try:
        from github import Github
    except ImportError:
        return None
    if not _GITHUB_TOKEN:
        return None
    return Github(_GITHUB_TOKEN)


def github_search_repos(query: str, limit: int = 10) -> dict[str, Any]:
    client = _get_client()
    if client is None:
        return {"success": False, "error": "GitHub API not available (install PyGithub and set GITHUB_TOKEN)"}
    try:
        repos = client.search_repositories(query, sort="stars", order="desc")
        results = []
        for r in repos[:limit]:
            results.append({"name": r.full_name, "description": r.description, "stars": r.stargazers_count,
                            "url": r.html_url, "language": r.language, "forks": r.forks_count})
        return {"success": True, "repos": results, "count": len(results)}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def github_get_repo(repo_name: str) -> dict[str, Any]:
    client = _get_client()
    if client is None:
        return {"success": False, "error": "GitHub API not available"}
    try:
        r = client.get_repo(repo_name)
        return {"success": True, "name": r.full_name, "description": r.description,
                "stars": r.stargazers_count, "forks": r.forks_count, "language": r.language,
                "url": r.html_url, "open_issues": r.open_issues_count, "default_branch": r.default_branch,
                "created_at": str(r.created_at), "updated_at": str(r.updated_at)}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def github_list_issues(repo_name: str, state: str = "open", limit: int = 20) -> dict[str, Any]:
    client = _get_client()
    if client is None:
        return {"success": False, "error": "GitHub API not available"}
    try:
        repo = client.get_repo(repo_name)
        issues = repo.get_issues(state=state)[:limit]
        results = []
        for i in issues:
            results.append({"number": i.number, "title": i.title, "state": i.state,
                            "created_at": str(i.created_at), "url": i.html_url,
                            "labels": [l.name for l in i.labels]})
        return {"success": True, "issues": results, "count": len(results)}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def github_create_issue(repo_name: str, title: str, body: str = "") -> dict[str, Any]:
    client = _get_client()
    if client is None:
        return {"success": False, "error": "GitHub API not available"}
    try:
        repo = client.get_repo(repo_name)
        issue = repo.create_issue(title=title, body=body)
        return {"success": True, "number": issue.number, "url": issue.html_url, "title": issue.title}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def github_list_prs(repo_name: str, state: str = "open", limit: int = 20) -> dict[str, Any]:
    client = _get_client()
    if client is None:
        return {"success": False, "error": "GitHub API not available"}
    try:
        repo = client.get_repo(repo_name)
        prs = repo.get_pulls(state=state)[:limit]
        results = []
        for pr in prs:
            results.append({"number": pr.number, "title": pr.title, "state": pr.state,
                            "created_at": str(pr.created_at), "url": pr.html_url,
                            "user": pr.user.login if pr.user else None})
        return {"success": True, "pull_requests": results, "count": len(results)}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def github_get_contents(repo_name: str, path: str, ref: str = "") -> dict[str, Any]:
    client = _get_client()
    if client is None:
        return {"success": False, "error": "GitHub API not available"}
    try:
        repo = client.get_repo(repo_name)
        content = repo.get_contents(path, ref=ref if ref else None)
        if isinstance(content, list):
            return {"success": True, "type": "directory", "entries": [c.path for c in content]}
        return {"success": True, "type": "file", "path": content.path, "size": content.size,
                "content": content.decoded_content.decode("utf-8", errors="replace") if content.encoding == "base64" else str(content)}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def github_list_branches(repo_name: str) -> dict[str, Any]:
    client = _get_client()
    if client is None:
        return {"success": False, "error": "GitHub API not available"}
    try:
        repo = client.get_repo(repo_name)
        branches = repo.get_branches()
        return {"success": True, "branches": [{"name": b.name, "sha": b.commit.sha} for b in branches]}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def github_list_commits(repo_name: str, branch: str = "main", limit: int = 20) -> dict[str, Any]:
    client = _get_client()
    if client is None:
        return {"success": False, "error": "GitHub API not available"}
    try:
        repo = client.get_repo(repo_name)
        commits = repo.get_commits(sha=branch)[:limit]
        results = []
        for c in commits:
            results.append({"sha": c.sha, "message": c.commit.message.split("\n")[0],
                            "author": c.commit.author.name if c.commit.author else None,
                            "date": str(c.commit.author.date) if c.commit.author else None})
        return {"success": True, "commits": results, "count": len(results)}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def github_create_gist(description: str, files: dict[str, str], public: bool = False) -> dict[str, Any]:
    client = _get_client()
    if client is None:
        return {"success": False, "error": "GitHub API not available"}
    try:
        gist = client.get_user().create_gist(public=public, description=description, files=files)
        return {"success": True, "id": gist.id, "url": gist.html_url}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    from mini_kio.core.mcp.servers.base import BaseMCPServer
    server = BaseMCPServer("github", "GitHub MCP Server", version="1.0.0")
    server.register_tool("github_search_repos", github_search_repos, {"query": {"type": "string"}, "limit": {"type": "integer", "default": 10}})
    server.register_tool("github_get_repo", github_get_repo, {"repo_name": {"type": "string"}})
    server.register_tool("github_list_issues", github_list_issues, {"repo_name": {"type": "string"}, "state": {"type": "string", "default": "open"}, "limit": {"type": "integer", "default": 20}})
    server.register_tool("github_create_issue", github_create_issue, {"repo_name": {"type": "string"}, "title": {"type": "string"}, "body": {"type": "string", "default": ""}})
    server.register_tool("github_list_prs", github_list_prs, {"repo_name": {"type": "string"}, "state": {"type": "string", "default": "open"}, "limit": {"type": "integer", "default": 20}})
    server.register_tool("github_get_contents", github_get_contents, {"repo_name": {"type": "string"}, "path": {"type": "string"}, "ref": {"type": "string", "default": ""}})
    server.register_tool("github_list_branches", github_list_branches, {"repo_name": {"type": "string"}})
    server.register_tool("github_list_commits", github_list_commits, {"repo_name": {"type": "string"}, "branch": {"type": "string", "default": "main"}, "limit": {"type": "integer", "default": 20}})
    server.register_tool("github_create_gist", github_create_gist, {"description": {"type": "string"}, "files": {"type": "object"}, "public": {"type": "boolean", "default": False}})
    server.run()
