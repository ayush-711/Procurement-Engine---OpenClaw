# Vegetable catalog MCP server

A minimal MCP server for OpenClaw. Holds a dummy vegetable catalog (name + price
per kg) and generates purchase-order PDFs. All pricing arithmetic happens in
Python, so the model never does the maths.

## Tools

| Tool | Purpose |
| --- | --- |
| `list_vegetables()` | Whole catalog with prices |
| `get_price(name)` | One price; tolerates plurals and small typos |
| `create_purchase_order(items, buyer, notes?, tax_percent?)` | Writes a PO PDF, returns its path |

`items` is a list of `{"name": "tomato", "quantity_kg": 5}`. Unknown names are
rejected, never guessed at.

## Install (inside your Ubuntu WSL distro)

```bash
mkdir -p ~/veg-mcp && cd ~/veg-mcp
# copy veg_mcp.py, catalog.json, requirements.txt, run.sh, .env.example here
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

cp .env.example .env
sed -i "s/replace-me/$(openssl rand -hex 24)/" .env
grep VEG_MCP_TOKEN .env        # note this token down
```

## Run

```bash
./run.sh
```

Listens on `http://127.0.0.1:8765/mcp`, bound to localhost only.

## Auth

Every request needs the token, either as a header or a query parameter:

```
Authorization: Bearer <token>
http://127.0.0.1:8765/mcp?token=<token>
```

Quick check — the first should be 401, the second 200:

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://127.0.0.1:8765/mcp -d '{}'
curl -s -o /dev/null -w "%{http_code}\n" -X POST "http://127.0.0.1:8765/mcp?token=<token>" \
  -H 'content-type: application/json' -H 'accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"ping"}'
```

## Register with OpenClaw

```bash
openclaw mcp add veggies --url "http://127.0.0.1:8765/mcp?token=<token>" \
  --transport streamable-http
openclaw mcp doctor veggies --probe
```

Prefer a real header? Add it in Control UI → Settings → MCP → veggies, or in the
config under `mcp.servers.veggies.headers`, and drop `?token=` from the URL.

## Editing the catalog

`catalog.json` is re-read on every tool call. Edit prices and they apply
immediately, no restart needed.

## Generated POs

Written to `~/veg-mcp/orders/PO-YYYYMMDD-HHMMSS.pdf`. The gateway runs in the
same WSL distro, so it can read that path directly when sending the file to
Telegram.

## Config (.env)

| Variable | Default |
| --- | --- |
| `VEG_MCP_TOKEN` | *(required)* |
| `VEG_MCP_PORT` | 8765 |
| `VEG_MCP_HOST` | 127.0.0.1 |
| `VEG_MCP_SUPPLIER` | Green Valley Vegetables |
| `VEG_MCP_CURRENCY` | INR |
