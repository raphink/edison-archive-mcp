"""
Edison Papers MCP Server
Interroge l'API publique Omeka S des Thomas A. Edison Papers (Rutgers University).
https://edisondigital.rutgers.edu/api/
"""

import json
import os
from typing import Optional
import httpx
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field, ConfigDict

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

BASE_URL = "https://edisondigital.rutgers.edu/api"
DOCUMENT_BASE = "https://edisondigital.rutgers.edu/document"
TIMEOUT = 15.0

# Champs connus à extraire des réponses Omeka S (confirmés sur D8839ACK2)
# Note : dcterms:abstract contient la transcription intégrale du document
#        bibo:recipient contient le destinataire (extension BIBO, pas Dublin Core)

# ---------------------------------------------------------------------------
# Serveur
# ---------------------------------------------------------------------------

mcp = FastMCP("edison_papers_mcp")

# ---------------------------------------------------------------------------
# Client HTTP partagé
# ---------------------------------------------------------------------------

def _get(endpoint: str, params: dict) -> dict:
    """Appel GET synchrone vers l'API Edison Papers."""
    with httpx.Client(timeout=TIMEOUT) as client:
        r = client.get(f"{BASE_URL}/{endpoint}", params=params)
        r.raise_for_status()
        total = r.headers.get("Omeka-S-Total-Results")
        return {"items": r.json(), "total": total}


def _extract(item: dict) -> dict:
    """Extrait les champs clés d'un item Omeka S Edison Papers."""
    def get(field: str) -> list[str]:
        return [v.get("@value", v.get("@id", "")) for v in item.get(field, [])]

    cote = get("dcterms:identifier")
    return {
        "omeka_id":       item.get("o:id"),
        "cote":           cote[0] if cote else None,
        "titre":          get("dcterms:title")[0] if get("dcterms:title") else None,
        "date":           get("dcterms:date")[0] if get("dcterms:date") else None,
        "type":           get("dcterms:type")[0] if get("dcterms:type") else None,
        "createurs":      get("dcterms:creator"),
        "destinataires":  get("bibo:recipient"),
        "transcription":  get("dcterms:abstract")[0] if get("dcterms:abstract") else None,
        "sujets":         get("dcterms:subject"),
        "relations":      get("dcterms:relation"),
        "serie":          get("dcterms:isPartOf")[0] if get("dcterms:isPartOf") else None,
        "source_microfilm": get("dcterms:source")[0] if get("dcterms:source") else None,
        "archive_org":    get("dcterms:hasVersion")[0] if get("dcterms:hasVersion") else None,
        "licence":        get("dcterms:license")[0] if get("dcterms:license") else None,
        "url_web":        f"{DOCUMENT_BASE}/{cote[0]}" if cote else None,
        "thumbnail":      item.get("thumbnail_display_urls", {}).get("large"),
        "nb_scans":       len(item.get("o:media", [])),
        "item_set_id":    item["o:item_set"][0]["o:id"] if item.get("o:item_set") else None,
    }


def _fmt_item(m: dict, include_transcription: bool = False) -> str:
    """Formate un item extrait en Markdown lisible."""
    lines = [
        f"### {m['cote']} — {m['date'] or 'date inconnue'}",
        f"**Titre** : {m['titre']}",
        f"**Type** : {m['type']}",
        f"**De** : {', '.join(m['createurs']) or '—'}",
        f"**À** : {', '.join(m['destinataires']) or '—'}",
        f"**Sujets** : {', '.join(m['sujets']) or '—'}",
        f"**Série** : {m['serie'] or '—'}",
        f"**Scans** : {m['nb_scans']} page(s)",
        f"**URL** : {m['url_web']}",
    ]
    if m.get("archive_org"):
        lines.append(f"**Archive.org** : {m['archive_org']}")
    if include_transcription and m.get("transcription"):
        lines += ["", "**Transcription** :", m["transcription"]]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Outils
# ---------------------------------------------------------------------------

class SearchInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    query: Optional[str] = Field(default=None, description="Texte libre à rechercher. Ex : 'D8839ACK2', 'incandescent lamp'. Laisser vide si on filtre uniquement par creator/recipient.", max_length=200)
    creator: Optional[str] = Field(default=None, description="Filtrer par expéditeur/auteur exact. Ex : 'Rau, Louis', 'Compagnie Continentale Edison'", max_length=200)
    recipient: Optional[str] = Field(default=None, description="Filtrer par destinataire exact. Ex : 'Edison, Thomas Alva', 'Edison Electric Light Co of Europe Ltd'", max_length=200)
    per_page: Optional[int] = Field(default=20, description="Nombre de résultats par page (1-100)", ge=1, le=100)
    page: Optional[int] = Field(default=1, description="Numéro de page pour la pagination", ge=1)
    sort_by: Optional[str] = Field(default="dcterms:date", description="Champ de tri. Options : 'dcterms:date', 'dcterms:title', 'o:id'")
    sort_order: Optional[str] = Field(default="asc", description="Ordre de tri : 'asc' ou 'desc'")


@mcp.tool(
    name="edison_search",
    annotations={
        "title": "Recherche dans les Edison Papers",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def edison_search(params: SearchInput) -> str:
    """Recherche dans les Edison Papers (Rutgers University).

    Supporte deux modes de recherche complémentaires :
    - fulltext (query) : recherche dans toutes les métadonnées, large mais imprécis
    - filtres exacts (creator, recipient) : filtre sur le champ Dublin Core exact, bien plus précis

    Pour Louis Rau, utiliser creator='Rau, Louis' plutôt que query='Louis Rau'.
    Les deux filtres peuvent être combinés.

    Args:
        params: SearchInput avec query optionnel, creator, recipient, per_page, page, sort_by, sort_order.

    Returns:
        str: Liste Markdown des documents trouvés avec total, pagination, et métadonnées.
    """
    if not params.query and not params.creator and not params.recipient:
        return "Erreur : fournir au moins un critère de recherche (query, creator, ou recipient)."

    api_params: dict = {
        "per_page": params.per_page,
        "page": params.page,
        "sort_by": params.sort_by,
        "sort_order": params.sort_order,
    }

    if params.query:
        api_params["fulltext_search"] = params.query

    # Filtres par propriété Dublin Core (syntaxe Omeka S)
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
        result = _get("items", api_params)
    except httpx.HTTPStatusError as e:
        return f"Erreur API Edison Papers : {e.response.status_code}"
    except httpx.TimeoutException:
        return "Erreur : délai d'attente dépassé. Réessayer."

    items = result["items"]
    total = result["total"] or "?"

    label = params.query or params.creator or params.recipient
    if not items:
        return f"Aucun résultat pour « {label} »."

    lines = [
        f"## Résultats Edison Papers : « {label} »",
        f"**{total} documents** trouvés — page {params.page} ({len(items)} affichés)\n",
    ]
    for item in items:
        m = _extract(item)
        lines.append(_fmt_item(m))
        lines.append("")

    has_more = len(items) == params.per_page
    if has_more:
        lines.append(f"*→ Page suivante : utiliser page={params.page + 1}*")

    return "\n".join(lines)


# ---------------------------------------------------------------------------

class GetDocumentInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    callnumber: str = Field(..., description="Cote Edison Papers (ex : 'D8839ACK2', 'CE89073', 'HX88018B1')", min_length=3, max_length=50)


@mcp.tool(
    name="edison_get_document",
    annotations={
        "title": "Récupérer un document Edison Papers par sa cote",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def edison_get_document(params: GetDocumentInput) -> str:
    """Récupère les métadonnées complètes et la transcription d'un document par sa cote.

    La transcription intégrale du document (texte de la lettre, du contrat, etc.)
    est disponible dans le champ dcterms:abstract de l'API Edison Papers.

    Args:
        params: GetDocumentInput avec la cote du document (ex : 'D8839ACK2').

    Returns:
        str: Métadonnées complètes + transcription intégrale du document en Markdown.
    """
    try:
        result = _get("items", {
            "fulltext_search": params.callnumber,
            "per_page": 10,
        })
    except httpx.HTTPStatusError as e:
        return f"Erreur API Edison Papers : {e.response.status_code}"
    except httpx.TimeoutException:
        return "Erreur : délai d'attente dépassé."

    # Trouver l'item exact par cote
    target = None
    for item in result["items"]:
        cotes = [v.get("@value", "") for v in item.get("dcterms:identifier", [])]
        if params.callnumber.upper() in [c.upper() for c in cotes]:
            target = item
            break

    if not target:
        return (
            f"Document « {params.callnumber} » introuvable.\n"
            f"Vérifier la cote ou essayer edison_search('{params.callnumber}')."
        )

    m = _extract(target)
    return _fmt_item(m, include_transcription=True)


# ---------------------------------------------------------------------------

class BrowseSeriesInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    item_set_id: int = Field(..., description="ID Omeka de la série (item set). Obtenir via edison_search puis champ item_set_id.", ge=1)
    per_page: Optional[int] = Field(default=50, description="Nombre de documents à lister (1-100)", ge=1, le=100)
    page: Optional[int] = Field(default=1, description="Numéro de page", ge=1)


@mcp.tool(
    name="edison_browse_series",
    annotations={
        "title": "Parcourir une série d'archives Edison Papers",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def edison_browse_series(params: BrowseSeriesInput) -> str:
    """Liste tous les documents d'une série (item set) Edison Papers.

    Utile pour explorer tous les documents d'un dossier d'archives (ex : tous
    les documents de la série D8839-F). L'item_set_id s'obtient via le champ
    'item_set_id' retourné par edison_search ou edison_get_document.

    Args:
        params: BrowseSeriesInput avec item_set_id, per_page, page.

    Returns:
        str: Liste Markdown des documents de la série avec métadonnées.
    """
    try:
        result = _get("items", {
            "item_set_id": params.item_set_id,
            "per_page": params.per_page,
            "page": params.page,
            "sort_by": "dcterms:date",
            "sort_order": "asc",
        })
    except httpx.HTTPStatusError as e:
        return f"Erreur API Edison Papers : {e.response.status_code}"
    except httpx.TimeoutException:
        return "Erreur : délai d'attente dépassé."

    items = result["items"]
    total = result["total"] or "?"

    if not items:
        return f"Aucun document dans la série {params.item_set_id}."

    # Récupérer le nom de la série depuis le premier item
    serie_name = None
    if items:
        first = _extract(items[0])
        serie_name = first.get("serie")

    lines = [
        f"## Série Edison Papers — item set {params.item_set_id}",
        f"**{serie_name or 'Série inconnue'}**",
        f"**{total} documents** — page {params.page} ({len(items)} affichés)\n",
    ]
    for item in items:
        m = _extract(item)
        createurs = ", ".join(m["createurs"]) if m["createurs"] else "—"
        destinataires = ", ".join(m["destinataires"]) if m["destinataires"] else "—"
        lines.append(
            f"- **{m['cote']}** ({m['date'] or '?'}) — {m['type'] or '?'} "
            f"| De : {createurs} → {destinataires}"
        )

    has_more = len(items) == params.per_page
    if has_more:
        lines.append(f"\n*→ Page suivante : utiliser page={params.page + 1}*")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "http":
        port = int(os.environ.get("PORT", 8000))
        print(f"Edison Papers MCP — HTTP sur port {port}", flush=True)
        mcp.run(transport="streamable-http", host="0.0.0.0", port=port)
    else:
        mcp.run()
