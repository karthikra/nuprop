from __future__ import annotations

import httpx

from app.core.config import get_settings


class GDriveClient:
    """Google Drive API v3 via httpx. Searches for documents about clients."""

    DRIVE_API = "https://www.googleapis.com/drive/v3"
    SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

    def __init__(self):
        self._settings = get_settings()

    async def search_files(
        self, access_token: str, query: str, max_results: int = 20,
    ) -> list[dict]:
        """Search Drive for files matching a query. Returns file metadata list."""
        params = {
            "q": f"fullText contains '{query}' and trashed = false",
            "pageSize": max_results,
            "fields": "files(id,name,mimeType,modifiedTime,owners,webViewLink,description)",
            "orderBy": "modifiedTime desc",
        }
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{self.DRIVE_API}/files",
                headers={"Authorization": f"Bearer {access_token}"},
                params=params,
                timeout=15,
            )
            r.raise_for_status()
            return r.json().get("files", [])

    async def get_file_content_text(self, access_token: str, file_id: str) -> str:
        """Export a Google Doc/Sheet as plain text. For PDFs/DOCX, gets metadata only."""
        async with httpx.AsyncClient() as client:
            try:
                r = await client.get(
                    f"{self.DRIVE_API}/files/{file_id}/export",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params={"mimeType": "text/plain"},
                    timeout=15,
                )
                r.raise_for_status()
                return r.text[:5000]  # Cap at 5K chars
            except Exception:
                return ""

    async def search_client_documents(
        self, access_token: str, client_name: str, max_results: int = 10,
    ) -> list[dict]:
        """Search for documents mentioning a client. Returns [{name, type, modified, link, snippet}]."""
        files = await self.search_files(access_token, client_name, max_results)
        results = []
        for f in files:
            doc_type = "unknown"
            mime = f.get("mimeType", "")
            if "document" in mime:
                doc_type = "doc"
            elif "spreadsheet" in mime:
                doc_type = "spreadsheet"
            elif "presentation" in mime:
                doc_type = "presentation"
            elif "pdf" in mime:
                doc_type = "pdf"

            results.append({
                "id": f["id"],
                "name": f.get("name", ""),
                "type": doc_type,
                "modified": f.get("modifiedTime", ""),
                "link": f.get("webViewLink", ""),
                "description": f.get("description", ""),
            })
        return results
