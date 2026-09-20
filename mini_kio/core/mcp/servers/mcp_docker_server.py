"""MCP Docker Server — container management via docker CLI.

Run: python -m mini_kio.core.mcp.servers.mcp_docker_server

Tools:
  docker_ps        — list running containers
  docker_inspect   — inspect a container
  docker_logs      — fetch container logs
  docker_exec      — run command in container
  docker_start     — start a container
  docker_stop      — stop a container
  docker_restart   — restart a container
  docker_images    — list images
  docker_pull      — pull an image
  docker_compose_up   — docker compose up
  docker_compose_down — docker compose down
"""

from __future__ import annotations

import json
import logging
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

from mini_kio.core.win_spawn import no_window

logger = logging.getLogger(__name__)


def _run_docker(args: list[str], timeout_s: int = 60) -> dict[str, Any]:
    try:
        result = subprocess.run(
            ["docker"] + args, capture_output=True, text=True, timeout=timeout_s,
            **no_window(),
        )
        if result.returncode == 0:
            return {"success": True, "stdout": result.stdout.strip(), "stderr": result.stderr.strip()}
        return {"success": False, "error": result.stderr.strip() or result.stdout.strip()}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Command timed out"}
    except FileNotFoundError:
        return {"success": False, "error": "docker command not found"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def docker_ps(all_containers: bool = False) -> dict[str, Any]:
    args = ["ps"]
    if all_containers:
        args.append("-a")
    args.extend(["--format", "{{json .}}"])
    result = _run_docker(args)
    if not result["success"]:
        return result
    containers = []
    for line in result["stdout"].splitlines():
        line = line.strip()
        if line:
            try:
                containers.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return {"success": True, "containers": containers, "count": len(containers)}


def docker_inspect(container_id: str) -> dict[str, Any]:
    return _run_docker(["inspect", container_id])


def docker_logs(container_id: str, tail: int = 50) -> dict[str, Any]:
    return _run_docker(["logs", "--tail", str(tail), container_id])


def docker_exec(container_id: str, command: str) -> dict[str, Any]:
    return _run_docker(["exec", container_id] + shlex.split(command))


def docker_start(container_id: str) -> dict[str, Any]:
    return _run_docker(["start", container_id])


def docker_stop(container_id: str, timeout_s: int = 10) -> dict[str, Any]:
    return _run_docker(["stop", "-t", str(timeout_s), container_id])


def docker_restart(container_id: str, timeout_s: int = 10) -> dict[str, Any]:
    return _run_docker(["restart", "-t", str(timeout_s), container_id])


def docker_images() -> dict[str, Any]:
    args = ["images", "--format", "{{json .}}"]
    result = _run_docker(args)
    if not result["success"]:
        return result
    images = []
    for line in result["stdout"].splitlines():
        line = line.strip()
        if line:
            try:
                images.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return {"success": True, "images": images, "count": len(images)}


def docker_pull(image: str) -> dict[str, Any]:
    return _run_docker(["pull", image], timeout_s=300)


def docker_compose_up(path: str = ".", detach: bool = True) -> dict[str, Any]:
    args = ["compose", "-f", path, "up"] if path != "." and Path(path).is_file() else ["compose", "up"]
    if detach:
        args.append("-d")
    return _run_docker(args, timeout_s=120)


def docker_compose_down(path: str = ".") -> dict[str, Any]:
    args = ["compose", "-f", path, "down"] if path != "." and Path(path).is_file() else ["compose", "down"]
    return _run_docker(args, timeout_s=60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    from mini_kio.core.mcp.servers.base import BaseMCPServer
    server = BaseMCPServer("docker", "Docker MCP Server", version="1.0.0")
    server.register_tool("docker_ps", docker_ps, {"all_containers": {"type": "boolean", "default": False}})
    server.register_tool("docker_inspect", docker_inspect, {"container_id": {"type": "string"}})
    server.register_tool("docker_logs", docker_logs, {"container_id": {"type": "string"}, "tail": {"type": "integer", "default": 50}})
    server.register_tool("docker_exec", docker_exec, {"container_id": {"type": "string"}, "command": {"type": "string"}})
    server.register_tool("docker_start", docker_start, {"container_id": {"type": "string"}})
    server.register_tool("docker_stop", docker_stop, {"container_id": {"type": "string"}, "timeout_s": {"type": "integer", "default": 10}})
    server.register_tool("docker_restart", docker_restart, {"container_id": {"type": "string"}, "timeout_s": {"type": "integer", "default": 10}})
    server.register_tool("docker_images", docker_images)
    server.register_tool("docker_pull", docker_pull, {"image": {"type": "string"}})
    server.register_tool("docker_compose_up", docker_compose_up, {"path": {"type": "string", "default": "."}, "detach": {"type": "boolean", "default": True}})
    server.register_tool("docker_compose_down", docker_compose_down, {"path": {"type": "string", "default": "."}})
    server.run()
