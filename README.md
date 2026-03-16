# Edison Papers MCP Server

An MCP server for querying the [Thomas A. Edison Papers](https://edisondigital.rutgers.edu) (Rutgers University) — ~150,000 documents, public domain (CC0).

## Tools

| Tool | Description |
|------|-------------|
| `edison_search` | Full-text search by keyword, author, or recipient |
| `edison_get_document` | Fetch full metadata and transcription for a document by call number |
| `edison_browse_series` | List all documents in an archive series |

---

## Use with Claude.ai (hosted)

Deploy the server online so Claude.ai can connect to it via HTTP.

### 1. Deploy to Railway (free)

1. Push this repo to GitHub
2. Go to [railway.app](https://railway.app) → **New Project → Deploy from GitHub repo**
3. Select your repo, then add this environment variable:
   ```
   MCP_TRANSPORT = http
   ```
   (`PORT` is set automatically by Railway)
4. Click **Deploy** (~2 minutes)
5. Go to **Settings → Networking → Generate Domain** to get your public URL

### 2. Connect to Claude.ai

Go to **Claude.ai → Settings → Integrations → Add custom integration** and enter:
```
https://your-app.up.railway.app/mcp
```

---

## Use with Claude Desktop (local)

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Add to Claude Desktop config

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "edison-papers": {
      "command": "python",
      "args": ["/absolute/path/to/server.py"]
    }
  }
}
```

---

## Other free hosting options

| Platform | Notes |
|----------|-------|
| [Railway](https://railway.app) | $5/month free credit, fast cold starts |
| [Render](https://render.com) | Always free tier, sleeps after 15 min of inactivity |
| [Hugging Face Spaces](https://huggingface.co/spaces) | Always-on, requires a `Dockerfile` |
