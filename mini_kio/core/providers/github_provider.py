"""GitHubProvider — GitHub API operations via PyGithub."""
from __future__ import annotations
import logging, os
from typing import Any
from mini_kio.core.provider_contract import ExecutionProvider, ProviderHealth, ProviderCapability

logger = logging.getLogger(__name__)

_GITHUB_ACTIONS = [
    "get_issue", "gather_issue_context", "get_pr_diff", "prs_since_last_tag",
    "repo_metrics", "create_issue", "list_issues", "list_prs", "get_contents",
    "search_repos", "dependency_scan",
]


def _get_client():
    try:
        from mini_kio.core.config import _ensure_env_loaded
        _ensure_env_loaded()
    except Exception:
        pass
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        return None
    try:
        from github import Github
        return Github(token)
    except ImportError:
        return None


class GitHubProvider(ExecutionProvider):
    def id(self) -> str:
        return "github"

    def capabilities(self) -> list[ProviderCapability]:
        return [
            ProviderCapability(name=a, category="external_api", timeout_s=15, ram_budget_mb=10)
            for a in _GITHUB_ACTIONS
        ]

    def health(self) -> ProviderHealth:
        return ProviderHealth.HEALTHY if _get_client() else ProviderHealth.OFFLINE

    def execute(self, action: str, target: str = "", **kwargs: Any) -> dict[str, Any]:
        client = _get_client()
        if client is None:
            return {"success": False, "message": "GitHub API not available"}
        try:
            if action == "repo_metrics":
                repo_name = kwargs.get("repo", target)
                repo = client.get_repo(repo_name)
                return {"success": True, "name": repo.full_name, "stars": repo.stargazers_count,
                        "forks": repo.forks_count, "open_issues": repo.open_issues_count,
                        "language": repo.language, "description": repo.description,
                        "message": f"Metrics for {repo.full_name}"}
            if action == "get_issue":
                repo_name = kwargs.get("repo", target)
                issue_num = int(kwargs.get("number", 1))
                repo = client.get_repo(repo_name)
                issue = repo.get_issue(issue_num)
                return {"success": True, "number": issue.number, "title": issue.title,
                        "body": issue.body[:500] if issue.body else "",
                        "state": issue.state, "labels": [l.name for l in issue.labels],
                        "message": f"Issue #{issue.number}: {issue.title}"}
            if action == "gather_issue_context":
                repo_name = kwargs.get("repo", target)
                issue_num = int(kwargs.get("number", 1))
                repo = client.get_repo(repo_name)
                issue = repo.get_issue(issue_num)
                comments = [c.body[:200] for c in issue.get_comments()[:5]]
                return {"success": True, "issue": {"title": issue.title, "body": issue.body[:500] if issue.body else ""},
                        "comments": comments, "labels": [l.name for l in issue.labels],
                        "message": f"Context gathered for #{issue.number}"}
            if action == "get_pr_diff":
                repo_name = kwargs.get("repo", target)
                pr_num = int(kwargs.get("number", 1))
                repo = client.get_repo(repo_name)
                pr = repo.get_pull(pr_num)
                files = [{"filename": f.filename, "status": f.status, "additions": f.additions, "deletions": f.deletions}
                         for f in pr.get_files()]
                return {"success": True, "pr_number": pr.number, "title": pr.title,
                        "files": files, "message": f"PR #{pr.number} diff: {len(files)} files"}
            if action == "prs_since_last_tag":
                repo_name = kwargs.get("repo", target)
                repo = client.get_repo(repo_name)
                prs = list(repo.get_pulls(state="closed", sort="updated", direction="desc")[:10])
                return {"success": True, "prs": [{"number": p.number, "title": p.title} for p in prs],
                        "count": len(prs), "message": f"{len(prs)} recent PRs"}
            if action == "create_issue":
                repo_name = kwargs.get("repo", target)
                title = kwargs.get("title", "Issue")
                body = kwargs.get("body", "")
                repo = client.get_repo(repo_name)
                issue = repo.create_issue(title=title, body=body)
                return {"success": True, "number": issue.number, "url": issue.html_url,
                        "message": f"Created issue #{issue.number}"}
            if action == "list_issues":
                repo_name = kwargs.get("repo", target)
                repo = client.get_repo(repo_name)
                issues = list(repo.get_issues(state="open", sort="updated")[:10])
                return {"success": True, "issues": [{"number": i.number, "title": i.title} for i in issues],
                        "count": len(issues), "message": f"{len(issues)} open issues"}
            if action == "list_prs":
                repo_name = kwargs.get("repo", target)
                repo = client.get_repo(repo_name)
                prs = list(repo.get_pulls(state="open")[:10])
                return {"success": True, "prs": [{"number": p.number, "title": p.title} for p in prs],
                        "count": len(prs), "message": f"{len(prs)} open PRs"}
            if action == "get_contents":
                repo_name = kwargs.get("repo", target)
                path = kwargs.get("path", "README.md")
                repo = client.get_repo(repo_name)
                content = repo.get_contents(path)
                import base64
                decoded = base64.b64decode(content.content).decode("utf-8", errors="replace")
                return {"success": True, "path": path, "content": decoded[:5000],
                        "message": f"Contents of {path}"}
            if action == "search_repos":
                query = kwargs.get("query", target)
                repos = client.search_repositories(query, sort="stars", order="desc")
                results = [{"name": r.full_name, "stars": r.stargazers_count, "description": r.description}
                           for r in repos[:5]]
                return {"success": True, "repos": results, "count": len(results),
                        "message": f"{len(results)} repos found"}
            if action == "dependency_scan":
                repo_name = kwargs.get("repo", target)
                return {"success": True, "dependencies": [], "vulnerabilities": [],
                        "message": f"Dependency scan for {repo_name} (placeholder)"}
            return {"success": False, "message": f"GitHubProvider: unknown action {action}"}
        except Exception as exc:
            return {"success": False, "message": f"GitHubProvider.{action} failed: {exc}"}
