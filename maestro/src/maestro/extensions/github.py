from __future__ import annotations

import httpx

from .schemas import CatalogSource


class GitHubError(RuntimeError):
    pass


class GitHubClient:
    def __init__(self, token: str = "", timeout: float = 20.0):
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "maestro-extension-catalog"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.client = httpx.AsyncClient(headers=headers, timeout=timeout, follow_redirects=False)

    async def close(self) -> None:
        await self.client.aclose()

    async def _json(self, url: str) -> dict:
        response = await self.client.get(url)
        if response.status_code >= 400:
            reset = response.headers.get("x-ratelimit-reset")
            raise GitHubError(f"GitHub {response.status_code}" + (f"，reset={reset}" if reset else ""))
        if len(response.content) > 8 * 1024 * 1024:
            raise GitHubError("GitHub 响应超过 8MB")
        return response.json()

    async def head_commit(self, source: CatalogSource) -> str:
        data = await self._json(f"https://api.github.com/repos/{source.owner}/{source.repo}/commits/{source.ref}")
        return str(data["sha"])

    async def tree(self, source: CatalogSource, commit: str) -> list[dict]:
        data = await self._json(f"https://api.github.com/repos/{source.owner}/{source.repo}/git/trees/{commit}?recursive=1")
        if data.get("truncated"):
            raise GitHubError("Git Trees API 返回截断结果")
        return list(data.get("tree", []))

    async def raw(self, source: CatalogSource, commit: str, path: str) -> bytes:
        url = f"https://raw.githubusercontent.com/{source.owner}/{source.repo}/{commit}/{path}"
        response = await self.client.get(url)
        if response.status_code >= 400:
            raise GitHubError(f"读取 {path} 失败: {response.status_code}")
        if len(response.content) > 10 * 1024 * 1024:
            raise GitHubError(f"文件 {path} 超过 10MB")
        return response.content
