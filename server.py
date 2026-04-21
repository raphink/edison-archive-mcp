"""
Edison Papers MCP Server
Queries the public Omeka S API of the Thomas A. Edison Papers (Rutgers University).
https://edisondigital.rutgers.edu/api/
"""

import base64
import os
from typing import Literal, Optional
import httpx
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field, ConfigDict

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://edisondigital.rutgers.edu/api"
DOCUMENT_BASE = "https://edisondigital.rutgers.edu/document"
TIMEOUT = 15.0

# Known fields to extract from Omeka S responses (confirmed on D8839ACK2)
# Note: dcterms:abstract contains the full transcription of the document
#       bibo:recipient contains the recipient (BIBO extension, not Dublin Core)

# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

mcp = FastMCP("edison_papers_mcp", host="0.0.0.0", stateless_http=True)

# ---------------------------------------------------------------------------
# Shared HTTP client
# ---------------------------------------------------------------------------

async def _get(endpoint: str, params: dict) -> dict:
    """Async GET call to the Edison Papers API."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.get(f"{BASE_URL}/{endpoint}", params=params)
        r.raise_for_status()
        total = r.headers.get("Omeka-S-Total-Results")
        return {"items": r.json(), "total": total}


def _extract(item: dict) -> dict:
    """Extracts key fields from an Omeka S Edison Papers item."""
    def get(field: str) -> list[str]:
        return [v.get("@value", v.get("@id", "")) for v in item.get(field, [])]

    cote = get("dcterms:identifier")
    return {
        "omeka_id":       item.get("o:id"),
        "callnumber":     cote[0] if cote else None,
        "title":          get("dcterms:title")[0] if get("dcterms:title") else None,
        "date":           get("dcterms:date")[0] if get("dcterms:date") else None,
        "type":           get("dcterms:type")[0] if get("dcterms:type") else None,
        "creators":       get("dcterms:creator"),
        "recipients":     get("bibo:recipient"),
        "transcription":  get("dcterms:abstract")[0] if get("dcterms:abstract") else None,
        "subjects":       get("dcterms:subject"),
        "relations":      get("dcterms:relation"),
        "series":         get("dcterms:isPartOf")[0] if get("dcterms:isPartOf") else None,
        "source_microfilm": get("dcterms:source")[0] if get("dcterms:source") else None,
        "archive_org":    get("dcterms:hasVersion")[0] if get("dcterms:hasVersion") else None,
        "license":        get("dcterms:license")[0] if get("dcterms:license") else None,
        "web_url":        f"{DOCUMENT_BASE}/{cote[0]}" if cote else None,
        "thumbnail":      item.get("thumbnail_display_urls", {}).get("large"),
        "nb_scans":       len(item.get("o:media", [])),
        "item_set_id":    item["o:item_set"][0]["o:id"] if item.get("o:item_set") else None,
    }


def _fmt_item(m: dict, include_transcription: bool = False) -> str:
    """Formats an extracted item as readable Markdown."""
    lines = [
        f"### {m['callnumber']} — {m['date'] or 'unknown date'}",
        f"**Title** : {m['title']}",
        f"**Type** : {m['type']}",
        f"**From** : {', '.join(m['creators']) or '—'}",
        f"**To** : {', '.join(m['recipients']) or '—'}",
        f"**Subjects** : {', '.join(m['subjects']) or '—'}",
        f"**Series** : {m['series'] or '—'}",
        f"**Scans** : {m['nb_scans']} page(s)",
        f"**URL** : {m['web_url']}",
    ]
    if m.get("archive_org"):
        lines.append(f"**Archive.org** : {m['archive_org']}")
    if include_transcription and m.get("transcription"):
        lines += ["", "**Transcription** :", m["transcription"]]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

class SearchInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    query: Optional[str] = Field(default=None, description="Free-text search query. E.g.: 'D8839ACK2', 'incandescent lamp'. Leave empty to filter by creator/recipient only.", max_length=200)
    creator: Optional[str] = Field(default=None, description="Filter by exact sender/author. E.g.: 'Rau, Louis', 'Compagnie Continentale Edison'", max_length=200)
    recipient: Optional[str] = Field(default=None, description="Filter by exact recipient. E.g.: 'Edison, Thomas Alva', 'Edison Electric Light Co of Europe Ltd'", max_length=200)
    per_page: Optional[int] = Field(default=20, description="Number of results per page (1-100)", ge=1, le=100)
    page: Optional[int] = Field(default=1, description="Page number for pagination", ge=1)
    sort_by: Optional[Literal["dcterms:date", "dcterms:title", "o:id"]] = Field(default="dcterms:date", description="Sort field.")
    sort_order: Optional[Literal["asc", "desc"]] = Field(default="asc", description="Sort order.")


@mcp.tool(
    name="edison_search",
    annotations={
        "title": "Search the Edison Papers",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def edison_search(params: SearchInput) -> str:
    """Search the Edison Papers (Rutgers University).

    Supports two complementary search modes:
    - fulltext (query): searches all metadata, broad but less precise
    - exact filters (creator, recipient): filters on the exact Dublin Core field, much more precise

    For Louis Rau, use creator='Rau, Louis' rather than query='Louis Rau'.
    Both filters can be combined.

    Args:
        params: SearchInput with optional query, creator, recipient, per_page, page, sort_by, sort_order.

    Returns:
        str: Markdown list of found documents with total, pagination, and metadata.
    """
    if not params.query and not params.creator and not params.recipient:
        return "Error: provide at least one search criterion (query, creator, or recipient)."

    api_params: dict = {
        "per_page": params.per_page,
        "page": params.page,
        "sort_by": params.sort_by,
        "sort_order": params.sort_order,
    }

    if params.query:
        api_params["fulltext_search"] = params.query

    # Dublin Core property filters (Omeka S syntax)
    prop_index = 0
    if params.creator:
        api_params[f"property[{prop_index}][property]"] = "dcterms:creator"
        api_params[f"property[{prop_index}][type]"] = "in"
        api_params[f"property[{prop_index}][text]"] = params.creator
        prop_index += 1

    if params.recipient:
        api_params[f"property[{prop_index}][property]"] = "bibo:recipient"
        api_params[f"property[{prop_index}][type]"] = "in"
        api_params[f"property[{prop_index}][text]"] = params.recipient
        prop_index += 1

    try:
        result = await _get("items", api_params)
    except httpx.HTTPStatusError as e:
        return f"Edison Papers API error: {e.response.status_code}"
    except httpx.TimeoutException:
        return "Error: request timed out. Please try again."

    items = result["items"]
    total = result["total"] or "?"

    label = params.query or params.creator or params.recipient
    if not items:
        return f"No results for « {label} »."

    lines = [
        f"## Edison Papers results: « {label} »",
        f"**{total} documents** found — page {params.page} ({len(items)} shown)\n",
    ]
    for item in items:
        m = _extract(item)
        lines.append(_fmt_item(m))
        lines.append("")

    has_more = len(items) == params.per_page
    if has_more:
        lines.append(f"*→ Next page: use page={params.page + 1}*")

    return "\n".join(lines)


# ---------------------------------------------------------------------------

class GetDocumentInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    callnumber: str = Field(..., description="Edison Papers call number (e.g.: 'D8839ACK2', 'CE89073', 'HX88018B1')", min_length=3, max_length=50)


@mcp.tool(
    name="edison_get_document",
    annotations={
        "title": "Retrieve an Edison Papers document by call number",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def edison_get_document(params: GetDocumentInput) -> str:
    """Retrieves the full metadata and transcription of a document by its call number.

    The full transcription of the document (text of the letter, contract, etc.)
    is available in the dcterms:abstract field of the Edison Papers API.

    Args:
        params: GetDocumentInput with the document call number (e.g.: 'D8839ACK2').

    Returns:
        str: Full metadata + complete transcription of the document in Markdown.
    """
    try:
        result = await _get("items", {
            "fulltext_search": params.callnumber,
            "per_page": 10,
        })
    except httpx.HTTPStatusError as e:
        return f"Edison Papers API error: {e.response.status_code}"
    except httpx.TimeoutException:
        return "Error: request timed out."

    # Find the exact item by call number
    target = None
    for item in result["items"]:
        cotes = [v.get("@value", "") for v in item.get("dcterms:identifier", [])]
        if params.callnumber.upper() in [c.upper() for c in cotes]:
            target = item
            break

    if not target:
        return (
            f"Document '{params.callnumber}' not found.\n"
            f"Check the call number or try edison_search('{params.callnumber}')."
        )

    m = _extract(target)
    return _fmt_item(m, include_transcription=True)


# ---------------------------------------------------------------------------

class BrowseSeriesInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    item_set_id: int = Field(..., description="Omeka ID of the series (item set). Obtain via edison_search then the item_set_id field.", ge=1)
    per_page: Optional[int] = Field(default=50, description="Number of documents to list (1-100)", ge=1, le=100)
    page: Optional[int] = Field(default=1, description="Page number", ge=1)


@mcp.tool(
    name="edison_browse_series",
    annotations={
        "title": "Browse an Edison Papers archive series",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def edison_browse_series(params: BrowseSeriesInput) -> str:
    """Lists all documents in an Edison Papers series (item set).

    Useful for exploring all documents in an archive folder (e.g.: all
    documents in the D8839-F series). The item_set_id is obtained via the
    'item_set_id' field returned by edison_search or edison_get_document.

    Args:
        params: BrowseSeriesInput with item_set_id, per_page, page.

    Returns:
        str: Markdown list of documents in the series with metadata.
    """
    try:
        result = await _get("items", {
            "item_set_id": params.item_set_id,
            "per_page": params.per_page,
            "page": params.page,
            "sort_by": "dcterms:date",
            "sort_order": "asc",
        })
    except httpx.HTTPStatusError as e:
        return f"Edison Papers API error: {e.response.status_code}"
    except httpx.TimeoutException:
        return "Error: request timed out."

    items = result["items"]
    total = result["total"] or "?"

    if not items:
        return f"No documents in series {params.item_set_id}."

    # Retrieve the series name from the first item
    series_name = None
    if items:
        first = _extract(items[0])
        series_name = first.get("series")

    lines = [
        f"## Edison Papers series — item set {params.item_set_id}",
        f"**{series_name or 'Unknown series'}**",
        f"**{total} documents** — page {params.page} ({len(items)} shown)\n",
    ]
    for item in items:
        m = _extract(item)
        creators = ", ".join(m["creators"]) if m["creators"] else "—"
        recipients = ", ".join(m["recipients"]) if m["recipients"] else "—"
        lines.append(
            f"- **{m['callnumber']}** ({m['date'] or '?'}) — {m['type'] or '?'} "
            f"| From: {creators} → {recipients}"
        )

    has_more = len(items) == params.per_page
    if has_more:
        lines.append(f"\n*→ Next page: use page={params.page + 1}*")

    return "\n".join(lines)



# ---------------------------------------------------------------------------
# Tool: scan retrieval (images)
# ---------------------------------------------------------------------------

class GetImagesInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    callnumber: str = Field(..., description="Edison Papers call number (e.g.: 'MU095', 'D8839ACK2')", min_length=3, max_length=50)
    pages: Optional[list[int]] = Field(default=None, description="Specific pages to retrieve (1-indexed). E.g.: [1, 2]. If absent, returns all pages (max 8).")


@mcp.tool(
    name="edison_get_images",
    annotations={
        "title": "Retrieve scans of an Edison Papers document for visual analysis",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def edison_get_images(params: GetImagesInput) -> list:
    """Retrieves high-resolution scans of an Edison Papers document and returns them
    as base64 for direct visual analysis by Claude.

    Use this to read the original text of a document (handwritten letters, contracts,
    telegrams), analyze signatures, letterheads, marginal annotations,
    or any visual content not captured by the text transcription.

    Args:
        params: GetImagesInput with the call number and optionally page numbers.

    Returns:
        list: Mixed content — metadata text + base64 images for each page.
    """
    # 1. Retrieve media via the API
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            # First search for the item by call number
            r = await client.get(f"{BASE_URL}/items", params={
                "fulltext_search": params.callnumber,
                "per_page": 10,
            })
            r.raise_for_status()
            items = r.json()
    except httpx.HTTPStatusError as e:
        return [{"type": "text", "text": f"API error: {e.response.status_code}"}]
    except httpx.TimeoutException:
        return [{"type": "text", "text": "Error: request timed out."}]

    # Find the exact item
    target = None
    for item in items:
        cotes = [v.get("@value", "") for v in item.get("dcterms:identifier", [])]
        if params.callnumber.upper() in [c.upper() for c in cotes]:
            target = item
            break

    if not target:
        return [{"type": "text", "text": f"Document '{params.callnumber}' not found."}]

    omeka_id = target["o:id"]
    media_refs = target.get("o:media", [])
    nb_total = len(media_refs)

    if nb_total == 0:
        return [{"type": "text", "text": f"No scans available for {params.callnumber}."}]

    # 2. Retrieve media metadata
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.get(f"{BASE_URL}/media", params={"item_id": omeka_id})
            r.raise_for_status()
            media_list = r.json()
    except Exception as e:
        return [{"type": "text", "text": f"Error retrieving media: {e}"}]

    # 3. Select pages
    if params.pages:
        selected = [media_list[i - 1] for i in params.pages if 0 < i <= len(media_list)]
    else:
        selected = media_list[:8]  # max 8 pages by default

    # 4. Download and encode
    result = []
    m = _extract(target)
    title = m['title'] or ''
    date = m['date'] or 'unknown date'
    result.append({
        "type": "text",
        "text": (
            f"## {params.callnumber} — {date}\n"
            f"**{title}**\n"
            f"Available pages: {nb_total} | Loaded pages: {len(selected)}\n"
        )
    })

    async with httpx.AsyncClient(timeout=30.0) as client:
        for i, media in enumerate(selected, 1):
            # Try original_url first, then large thumbnail
            img_url = media.get("o:original_url") or media.get("o:thumbnail_urls", {}).get("large")
            if not img_url:
                continue

            try:
                resp = await client.get(img_url, follow_redirects=True)
                resp.raise_for_status()
                content_type = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
                # Normalize MIME type
                if content_type not in ("image/jpeg", "image/png", "image/gif", "image/webp"):
                    content_type = "image/jpeg"
                b64 = base64.standard_b64encode(resp.content).decode("utf-8")
                result.append({
                    "type": "text",
                    "text": f"**Page {i}/{len(selected)}** ({img_url.split('/')[-1]})"
                })
                result.append({
                    "type": "image",
                    "data": b64,
                    "mimeType": content_type,
                })
            except Exception as e:
                result.append({
                    "type": "text",
                    "text": f"Page {i} — download error: {e}"
                })

    return result

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "http":
        port = int(os.environ.get("PORT", 8000))
        print(f"Edison Papers MCP — HTTP on port {port}", flush=True)
        mcp.run(transport="streamable-http", host="0.0.0.0", port=port)
    else:
        mcp.run()
