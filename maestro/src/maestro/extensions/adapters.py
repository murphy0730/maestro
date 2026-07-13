from __future__ import annotations

import hashlib
import io
import json
import re
import tomllib
import zipfile

from .github import GitHubClient
from .schemas import CatalogConnector, CatalogSource, ConnectorEnvSpec, utcnow
from .localization import CONNECTOR_DESCRIPTIONS_ZH


def stable_hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _skill_roots(tree: list[dict], source: CatalogSource) -> tuple[dict[str, str], set[str]]:
    blobs = {str(item["path"]): str(item["sha"]) for item in tree if item.get("type") == "blob"}
    roots: set[str] = set()
    for path in blobs:
        if not path.endswith("/SKILL.md"):
            continue
        root = path.rsplit("/", 1)[0]
        if any(root == allowed or root.startswith(allowed.rstrip("/") + "/") for allowed in source.paths):
            roots.add(root)
    return blobs, roots


async def _zip_root(client: GitHubClient, source: CatalogSource, commit: str, blobs: dict[str, str], root: str) -> tuple[str, str, bytes, str] | None:
    members = [path for path in blobs if path.startswith(root + "/")]
    if not members or len(members) > 200:  # 200 与 parser._ZIP_MAX_MEMBERS 对齐；真实技能（含 references/scripts）可达 60+ 文件
        return None
    bio = io.BytesIO()
    total = 0
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in members:
            content = await client.raw(source, commit, path)
            total += len(content)
            if total > 10 * 1024 * 1024:
                raise ValueError(f"技能目录 {root} 超过 10MB")
            archive.writestr(path[len(root) + 1 :], content)
    return (root.rsplit("/", 1)[-1], root, bio.getvalue(), stable_hash({p: blobs[p] for p in members}))


async def skill_packages(client: GitHubClient, source: CatalogSource, commit: str, tree: list[dict]) -> list[tuple[str, str, bytes, str]]:
    blobs, roots = _skill_roots(tree, source)
    results = []
    for root in sorted(roots):
        package = await _zip_root(client, source, commit, blobs, root)
        if package:
            results.append(package)
    return results


async def skill_package(client: GitHubClient, source: CatalogSource, commit: str, tree: list[dict], root: str) -> tuple[str, str, bytes, str] | None:
    """只下载并打包单个技能目录（安装/更新用），避免为装一个技能拉取整源全部技能。"""
    blobs, roots = _skill_roots(tree, source)
    if root not in roots:
        return None
    return await _zip_root(client, source, commit, blobs, root)


_MCP_TEMPLATES = {
    "mcp-reference-servers": {
        "filesystem": ("npx", ["-y", "@modelcontextprotocol/server-filesystem@2026.1.14", "."], [], ["Node.js", "配置允许访问的目录"]),
        "memory": ("npx", ["-y", "@modelcontextprotocol/server-memory@2025.11.25"], [], ["Node.js"]),
        "sequentialthinking": ("npx", ["-y", "@modelcontextprotocol/server-sequential-thinking@2025.12.18"], [], ["Node.js"]),
        "fetch": ("uvx", ["mcp-server-fetch==2025.4.7"], [], ["Python", "uv"]),
        "git": ("uvx", ["mcp-server-git==2025.12.19", "--repository", "."], [], ["Python", "uv"]),
        "time": ("uvx", ["mcp-server-time==2025.9.25"], [], ["Python", "uv"]),
    },
    "github-mcp-server": {
        "github": ("docker", ["run", "-i", "--rm", "-e", "GITHUB_PERSONAL_ACCESS_TOKEN", "ghcr.io/github/github-mcp-server:0.27.0"], [ConnectorEnvSpec(name="GITHUB_PERSONAL_ACCESS_TOKEN", description="GitHub access token", required=True, secret=True)], ["Docker", "GitHub Token"]),
    },
    "playwright-mcp": {
        "playwright": ("npx", ["-y", "@playwright/mcp@0.0.68"], [], ["Node.js", "Playwright 浏览器"]),
    },
}


async def connector_items(client: GitHubClient, source: CatalogSource, commit: str, tree: list[dict]) -> list[CatalogConnector]:
    templates = _MCP_TEMPLATES[source.id]
    tree_paths = {str(item.get("path", "")) for item in tree}
    now = utcnow()
    results = []
    for name, (command, args, env_schema, requirements) in templates.items():
        if command not in {"npx", "uvx", "docker"} or any(re.search(r"[;&|`$<>]", arg) for arg in args):
            continue
        configured_path = next((p for p in source.paths if p == "." or p.endswith("/" + name)), ".")
        if configured_path != "." and not any(p.startswith(configured_path + "/") for p in tree_paths):
            continue
        # 从上游 manifest 提取版本与英文简介：npx server 用 package.json，uvx server 用 pyproject.toml。
        pkg_json = "package.json" if configured_path == "." else f"{configured_path}/package.json"
        pyproject = "pyproject.toml" if configured_path == "." else f"{configured_path}/pyproject.toml"
        version, english = None, None
        if pkg_json in tree_paths:
            try:
                data = json.loads((await client.raw(source, commit, pkg_json)).decode("utf-8"))
                version, english = (str(data["version"]) if "version" in data else None), (data.get("description") or None)
            except (ValueError, UnicodeDecodeError):
                pass
        elif pyproject in tree_paths:
            try:
                project = tomllib.loads((await client.raw(source, commit, pyproject)).decode("utf-8")).get("project", {})
                version, english = (str(project["version"]) if "version" in project else None), (project.get("description") or None)
            except (ValueError, UnicodeDecodeError):
                pass
        if version:
            args = [re.sub(r"(@|==)[^/]+$", lambda match: match.group(1) + version, arg) if ("@" in arg or "==" in arg) else arg for arg in args]
        template_hash = stable_hash({"command": command, "args": args, "env_schema": [x.model_dump() for x in env_schema]})
        version = version or next((arg.rsplit("@", 1)[-1] for arg in args if "@" in arg), None)
        description = CONNECTOR_DESCRIPTIONS_ZH.get(name) or english or f"来自 {source.display_name} 的官方 MCP 连接器"
        results.append(CatalogConnector(catalog_id=f"{source.id}:{name}", name=name, display_name=name.replace("-", " ").title(), description=description, summary_zh=CONNECTOR_DESCRIPTIONS_ZH.get(name), author=source.owner, license="MIT", version=version, source_id=source.id, source_name=source.display_name, source_url=f"{source.source_url}/tree/{commit}/{configured_path}", source_ref=source.ref, source_commit=commit, command=command, args=args, env_schema=env_schema, requirements=requirements, catalog_template_sha256=template_hash, synced_at=now, last_checked_at=now))
    return results
