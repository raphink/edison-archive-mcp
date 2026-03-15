# Edison Papers MCP Server

Serveur MCP pour interroger les [Thomas A. Edison Papers](https://edisondigital.rutgers.edu) (Rutgers University) — API publique Omeka S, ~150 000 documents, CC0.

Fonctionne en deux modes :
- **stdio** — pour Claude Desktop (local, pas de réseau)
- **HTTP** — pour Claude.ai (hébergé sur Railway, Render, Fly.io…)

---

## Déploiement Railway (Claude.ai)

### Étape 1 — Créer un dépôt GitHub

```bash
git init
git add .
git commit -m "Edison Papers MCP"
git remote add origin https://github.com/TON_NOM/edison-papers-mcp.git
git push -u origin main
```

### Étape 2 — Déployer sur Railway

1. Aller sur [railway.app](https://railway.app) → **New Project → Deploy from GitHub repo**
2. Sélectionner ton dépôt `edison-papers-mcp`
3. Dans **Variables**, ajouter : `MCP_TRANSPORT = http`
   (la variable `PORT` est injectée automatiquement par Railway)
4. Cliquer **Deploy** — déploiement en ~2 minutes

### Étape 3 — Récupérer l'URL publique

Railway → ton service → **Settings → Networking → Generate Domain**

URL de la forme : `https://edison-papers-mcp-production.up.railway.app`

### Étape 4 — Connecter à Claude.ai

Claude.ai → **Settings → Integrations → Add custom integration** :
```
https://edison-papers-mcp-production.up.railway.app/mcp
```

---

## Installation locale (Claude Desktop)

```bash
pip install "mcp[cli]" httpx
```

`~/Library/Application Support/Claude/claude_desktop_config.json` :

```json
{
  "mcpServers": {
    "edison-papers": {
      "command": "python",
      "args": ["/chemin/absolu/vers/server.py"]
    }
  }
}
```

---

## Outils

| Outil | Description |
|-------|-------------|
| `edison_search` | Recherche fulltext (nom, cote, sujet…) paginée |
| `edison_get_document` | Cote → métadonnées + transcription intégrale |
| `edison_browse_series` | Lister tous les documents d'une série d'archives |

---

## Cotes connues — Louis Rau & CCE

| Cote | Date | Description |
|------|------|-------------|
| `HX88018B1` | 1888-02-15 | Contrat éclairage Exposition universelle 1889 |
| `D8839ACK2` | 1888-10-16 | Brevets autrichiens et français |
| `CE89073`   | 1889-05-13 | Augmentation de capital (7 → 10 M F) |
| `CE91089`   | 1891-01-13 | Plainte Milan Edison Co. |
| `D9128AAA`  | 1891-02-19 | Guerre des brevets — Siemens, Rathenau/AEG |
