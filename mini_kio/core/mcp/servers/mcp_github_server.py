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

_GITHUB_TOKEN = None


def _get_client():
    global _GITHUB_TOKEN
    if _GITHUB_TOKEN is None:
        try:
            from mini_kio.core.config import _ensure_env_loaded
            _ensure_env_loaded()
        except Exception:
            pass
        _GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
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


def github_dependency_scan(repo_name: str) -> dict[str, Any]:
    """Scan Dependabot alerts for a repository. Requires GITHUB_TOKEN with repo scope."""
    client = _get_client()
    if client is None:
        return {"success": False, "error": "GitHub API not available"}
    try:
        repo = client.get_repo(repo_name)
        # Dependabot alerts via REST API (PyGithub doesn't wrap this directly)
        from github import GithubException
        headers, data = repo._requester.requestJsonAndCheck(
            "GET", f"/repos/{repo_name}/dependabot/alerts",
            parameters={"state": "open", "per_page": 100}
        )
        alerts = data if isinstance(data, list) else data.get("alerts", []) if isinstance(data, dict) else []
        results = []
        for a in alerts:
            results.append({
                "number": a.get("number"),
                "severity": a.get("security_advisory", {}).get("severity", "unknown"),
                "package": a.get("security_vulnerability", {}).get("package", {}).get("name", "unknown"),
                "summary": a.get("security_advisory", {}).get("summary", ""),
                "state": a.get("state"),
                "created_at": a.get("created_at"),
            })
        return {"success": True, "alerts": results, "count": len(results),
                "message": f"Found {len(results)} Dependabot alerts"}
    except Exception as exc:
        return {"success": False, "error": str(exc), "message": f"dependency_scan failed: {exc}"}


def github_gather_issue_context(repo_name: str, issue_number: int) -> dict[str, Any]:
    """Gather full context for an issue: body, comments, labels, linked PRs."""
    client = _get_client()
    if client is None:
        return {"success": False, "error": "GitHub API not available"}
    try:
        repo = client.get_repo(repo_name)
        issue = repo.get_issue(issue_number)
        # Comments
        comments = []
        for c in issue.get_comments():
            comments.append({
                "author": c.user.login if c.user else None,
                "body": c.body or "",
                "created_at": str(c.created_at),
            })
        # Linked PRs (issues that reference this)
        linked_prs = []
        for pr in repo.get_pulls(state="all"):
            if pr.number == issue_number:
                linked_prs.append({"number": pr.number, "title": pr.title, "state": pr.state})
            # Check if PR body references this issue
            body = pr.body or ""
            if f"#{issue_number}" in body or f"fixes #{issue_number}" in body.lower():
                linked_prs.append({"number": pr.number, "title": pr.title, "state": pr.state})
        return {
            "success": True,
            "number": issue.number,
            "title": issue.title,
            "body": issue.body or "",
            "state": issue.state,
            "labels": [l.name for l in issue.labels],
            "author": issue.user.login if issue.user else None,
            "created_at": str(issue.created_at),
            "comments": comments,
            "comment_count": len(comments),
            "linked_prs": linked_prs,
            "url": issue.html_url,
        }
    except Exception as exc:
        return {"success": False, "error": str(exc), "message": f"gather_issue_context failed: {exc}"}


def github_get_run_logs(repo_name: str, workflow_run_id: int = 0, limit: int = 5) -> dict[str, Any]:
    """Get recent GitHub Actions workflow runs and their status/logs summary."""
    client = _get_client()
    if client is None:
        return {"success": False, "error": "GitHub API not available"}
    try:
        repo = client.get_repo(repo_name)
        if workflow_run_id:
            # Get specific run
            headers, data = repo._requester.requestJsonAndCheck(
                "GET", f"/repos/{repo_name}/actions/runs/{workflow_run_id}"
            )
            run = data
            jobs_headers, jobs_data = repo._requester.requestJsonAndCheck(
                "GET", f"/repos/{repo_name}/actions/runs/{workflow_run_id}/jobs"
            )
            jobs = jobs_data.get("jobs", []) if isinstance(jobs_data, dict) else []
            return {
                "success": True,
                "run_id": run.get("id"),
                "name": run.get("name"),
                "status": run.get("status"),
                "conclusion": run.get("conclusion"),
                "head_branch": run.get("head_branch"),
                "created_at": run.get("created_at"),
                "jobs": [{"name": j.get("name"), "status": j.get("status"),
                          "conclusion": j.get("conclusion")} for j in jobs],
            }
        else:
            # Get recent runs
            headers, data = repo._requester.requestJsonAndCheck(
                "GET", f"/repos/{repo_name}/actions/runs",
                parameters={"per_page": limit}
            )
            runs = data.get("workflow_runs", []) if isinstance(data, dict) else []
            return {
                "success": True,
                "runs": [{
                    "id": r.get("id"),
                    "name": r.get("name"),
                    "status": r.get("status"),
                    "conclusion": r.get("conclusion"),
                    "head_branch": r.get("head_branch"),
                    "created_at": r.get("created_at"),
                    "html_url": r.get("html_url"),
                } for r in runs],
                "count": len(runs),
                "message": f"Found {len(runs)} workflow runs",
            }
    except Exception as exc:
        return {"success": False, "error": str(exc), "message": f"get_run_logs failed: {exc}"}


def github_prs_since_last_tag(repo_name: str) -> dict[str, Any]:
    """List PRs merged since the most recent release tag."""
    client = _get_client()
    if client is None:
        return {"success": False, "error": "GitHub API not available"}
    try:
        repo = client.get_repo(repo_name)
        # Get tags (latest first)
        tags = list(repo.get_tags())
        if not tags:
            return {"success": True, "prs": [], "count": 0,
                    "message": "No tags found — cannot determine 'since last tag'"}
        last_tag = tags[0]
        last_tag_date = last_tag.commit.commit.author.date
        # Get PRs merged after that date
        merged_prs = []
        for pr in repo.get_pulls(state="closed"):
            if pr.merged and pr.merged_at and pr.merged_at > last_tag_date:
                merged_prs.append({
                    "number": pr.number,
                    "title": pr.title,
                    "user": pr.user.login if pr.user else None,
                    "merged_at": str(pr.merged_at),
                    "url": pr.html_url,
                })
        return {
            "success": True,
            "last_tag": last_tag.name,
            "last_tag_date": str(last_tag_date),
            "prs": merged_prs,
            "count": len(merged_prs),
            "message": f"Found {len(merged_prs)} PRs since {last_tag.name}",
        }
    except Exception as exc:
        return {"success": False, "error": str(exc), "message": f"prs_since_last_tag failed: {exc}"}


def github_repo_metrics(repo_name: str) -> dict[str, Any]:
    """Get repo health metrics: stars, forks, open issues, recent activity, CI status."""
    client = _get_client()
    if client is None:
        return {"success": False, "error": "GitHub API not available"}
    try:
        repo = client.get_repo(repo_name)
        # Recent commits (last 30 days)
        from datetime import datetime, timedelta
        cutoff = datetime.utcnow() - timedelta(days=30)
        recent_commits = 0
        for c in repo.get_commits(since=cutoff):
            recent_commits += 1
        # Open issues vs PRs
        open_issues = repo.open_issues_count
        open_prs = len(list(repo.get_pulls(state="open")))
        # Contributors (top 5)
        contribs = []
        try:
            for c in repo.get_contributors()[:5]:
                contribs.append({"login": c.login, "contributions": c.contributions})
        except Exception:
            pass
        return {
            "success": True,
            "name": repo.full_name,
            "stars": repo.stargazers_count,
            "forks": repo.forks_count,
            "open_issues": open_issues - open_prs,
            "open_prs": open_prs,
            "language": repo.language,
            "size_kb": repo.size,
            "recent_commits_30d": recent_commits,
            "top_contributors": contribs,
            "default_branch": repo.default_branch,
            "updated_at": str(repo.updated_at),
            "message": f"Metrics for {repo.full_name}",
        }
    except Exception as exc:
        return {"success": False, "error": str(exc), "message": f"repo_metrics failed: {exc}"}


def github_get_issue(repo_name: str, issue_number: int) -> dict[str, Any]:
    client = _get_client()
    if client is None:
        return {"success": False, "error": "GitHub API not available"}
    try:
        repo = client.get_repo(repo_name)
        issue = repo.get_issue(issue_number)
        labels = [l.name for l in issue.labels]
        return {"success": True, "number": issue.number, "title": issue.title,
                "body": issue.body or "", "state": issue.state, "labels": labels,
                "author": issue.user.login if issue.user else None,
                "created_at": str(issue.created_at), "url": issue.html_url}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def github_apply_labels(repo_name: str, issue_number: int, labels: list[str]) -> dict[str, Any]:
    client = _get_client()
    if client is None:
        return {"success": False, "error": "GitHub API not available"}
    try:
        repo = client.get_repo(repo_name)
        issue = repo.get_issue(issue_number)
        issue.add_to_labels(*labels)
        return {"success": True, "applied": labels, "issue": issue_number}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def github_create_draft_pr(repo_name: str, title: str, head: str, base: str = "main", body: str = "") -> dict[str, Any]:
    client = _get_client()
    if client is None:
        return {"success": False, "error": "GitHub API not available"}
    try:
        repo = client.get_repo(repo_name)
        pr = repo.create_pull(title=title, body=body, head=head, base=base, draft=True)
        return {"success": True, "pr_url": pr.html_url, "pr_number": pr.number}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def github_get_pr_diff(repo_name: str, pr_number: int) -> dict[str, Any]:
    client = _get_client()
    if client is None:
        return {"success": False, "error": "GitHub API not available"}
    try:
        repo = client.get_repo(repo_name)
        pr = repo.get_pull(pr_number)
        files = [{"filename": f.filename, "status": f.status, "additions": f.additions,
                  "deletions": f.deletions, "changes": f.changes} for f in pr.get_files()]
        return {"success": True, "diff": pr.body or "", "files_changed": files,
                "file_count": len(files), "pr_url": pr.html_url}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def github_create_release(repo_name: str, tag: str, name: str = "", body: str = "", draft: bool = False) -> dict[str, Any]:
    client = _get_client()
    if client is None:
        return {"success": False, "error": "GitHub API not available"}
    try:
        repo = client.get_repo(repo_name)
        release = repo.create_git_release(tag=tag, name=name or tag, body=body, draft=draft)
        return {"success": True, "release_url": release.html_url, "tag": tag}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def github_export_archive(repo_name: str, ref: str = "main") -> dict[str, Any]:
    client = _get_client()
    if client is None:
        return {"success": False, "error": "GitHub API not available"}
    try:
        repo = client.get_repo(repo_name)
        archive_url = repo.archive_url.format(ref=ref, archive_format="tarball")
        return {"success": True, "archive_url": archive_url, "message": f"Download archive from {archive_url}"}
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
    server.register_tool("github_dependency_scan", github_dependency_scan, {"repo_name": {"type": "string"}})
    server.register_tool("github_gather_issue_context", github_gather_issue_context, {"repo_name": {"type": "string"}, "issue_number": {"type": "integer"}})
    server.register_tool("github_get_run_logs", github_get_run_logs, {"repo_name": {"type": "string"}, "workflow_run_id": {"type": "integer", "default": 0}, "limit": {"type": "integer", "default": 5}})
    server.register_tool("github_prs_since_last_tag", github_prs_since_last_tag, {"repo_name": {"type": "string"}})
    server.register_tool("github_repo_metrics", github_repo_metrics, {"repo_name": {"type": "string"}})
    server.run()
