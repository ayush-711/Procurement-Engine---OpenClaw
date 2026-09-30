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



# Setup guide

From a clean Windows PC to a working Telegram bot: you text it a vegetable order, and it replies with a purchase-order PDF.

**How it fits together**

```
Telegram  →  OpenClaw gateway (WSL)  →  Claude (via Claude Code CLI)
                     │
                     └──→  veg-mcp server (WSL, 127.0.0.1:8765)  →  orders/PO-*.pdf
```

Everything runs inside one Ubuntu WSL distro. Nothing is exposed to the internet: Telegram uses long polling, and the MCP server listens on localhost only.

**You need**
- Windows 10 (21H2+) or Windows 11, with virtualization enabled in BIOS
- A Telegram account
- A Claude Pro/Max subscription (for Claude Code login) **or** an Anthropic API key

---

## 1. Install WSL + Ubuntu

In **PowerShell as Administrator**:

```powershell
wsl --install -d Ubuntu-24.04
```

Reboot if asked. Then open **Ubuntu-24.04** from the Start menu and create your Linux username and password.

Check that systemd is running (OpenClaw's background service needs it):

```bash
ps -p 1 -o comm=
```

If it doesn't print `systemd`, enable it:

```bash
printf '[boot]\nsystemd=true\n' | sudo tee /etc/wsl.conf
```

Then run `wsl --shutdown` in PowerShell and reopen Ubuntu.

> Every command from here on runs **inside Ubuntu**, not PowerShell.

## 2. Install base packages

```bash
sudo apt update
sudo apt install -y git curl openssl python3 python3-venv python3-pip
```

## 3. Log in to Claude Code

OpenClaw reuses your Claude Code login, so there's no API key to manage.

```bash
curl -fsSL https://claude.ai/install.sh | bash
exec bash            # reload PATH
claude auth login    # opens a browser link; sign in
claude auth status --text
```

*Using an API key instead?* Skip this step and choose **Anthropic API key** in step 4.

## 4. Install OpenClaw

```bash
curl -fsSL https://openclaw.ai/install.sh | bash
exec bash
openclaw --version
```

The installer handles Node.js (OpenClaw needs Node 24.16+). Then run the onboarding wizard, which also installs the gateway as a background service:

```bash
openclaw onboard --install-daemon
```

In the wizard, pick **Anthropic → Claude CLI** as the model provider. Accept the defaults for everything else. You can skip channels for now; Telegram is added in step 8.

Confirm the gateway is up:

```bash
openclaw gateway status
openclaw models list --provider anthropic
```

If no Anthropic models are listed, run:

```bash
openclaw models auth login --provider anthropic --method cli --set-default
```

The Control UI is at http://127.0.0.1:18789 (open it in your Windows browser).

## 5. Set up the MCP server

```bash
git clone https://github.com/ayush-711/Procurement-Engine---OpenClaw.git ~/veg-mcp
cd ~/veg-mcp
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Generate the auth token:

```bash
echo "VEG_MCP_TOKEN=$(openssl rand -hex 24)" > .env
chmod 600 .env
```

Optional settings you can add to `.env`:

| Variable | Default |
|---|---|
| `VEG_MCP_PORT` | `8765` |
| `VEG_MCP_HOST` | `127.0.0.1` |
| `VEG_MCP_SUPPLIER` | `Green Valley Vegetables` |
| `VEG_MCP_CURRENCY` | `INR` |

Test-run it:

```bash
./run.sh
```

Leave it running and open a **second** Ubuntu tab to check auth. The first command should print `401`, the second `200`:

```bash
TOKEN=$(grep ^VEG_MCP_TOKEN= ~/veg-mcp/.env | cut -d= -f2)

curl -s -o /dev/null -w "%{http_code}\n" -X POST http://127.0.0.1:8765/mcp -d '{}'

curl -s -o /dev/null -w "%{http_code}\n" -X POST "http://127.0.0.1:8765/mcp?token=$TOKEN" \
  -H 'content-type: application/json' -H 'accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"ping"}'
```

Stop the test server with `Ctrl+C`.

## 6. Keep the MCP server running

Run it as a systemd user service so it starts with WSL and restarts if it crashes:

```bash
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/veg-mcp.service <<'EOF'
[Unit]
Description=Vegetable catalog MCP server

[Service]
ExecStart=%h/veg-mcp/run.sh
Restart=on-failure

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now veg-mcp
sudo loginctl enable-linger "$USER"     # keep user services running without an open terminal
systemctl --user status veg-mcp --no-pager
```

## 7. Register the MCP server with OpenClaw

```bash
TOKEN=$(grep ^VEG_MCP_TOKEN= ~/veg-mcp/.env | cut -d= -f2)

openclaw mcp add veggies --url "http://127.0.0.1:8765/mcp?token=$TOKEN" \
  --transport streamable-http

openclaw mcp doctor veggies --probe
```

The probe should list three tools: `list_vegetables`, `get_price`, `create_purchase_order`.

## 8. Connect Telegram

1. In Telegram, open a chat with **@BotFather** (check the handle is exact). Send `/newbot`, pick a name and a username ending in `bot`, and copy the token it gives you.
2. Give the token to OpenClaw:
   ```bash
   openclaw channels add --channel telegram --token <BOT_TOKEN>
   openclaw channels status --probe
   ```
3. Send your bot any message in Telegram. It replies with a pairing code. Approve it:
   ```bash
   openclaw pairing list telegram
   openclaw pairing approve telegram <CODE>
   ```
   Codes expire after 1 hour. Only approved users can talk to the bot.

## 9. Test it

Send the bot:

```
What vegetables do you have?
```

Then:

```
Order 5 kg tomatoes and 2 kg onions for Ayush Kumar
```

You should get a purchase-order PDF back. A copy is saved in `~/veg-mcp/orders/`.

---

## Day to day

| Task | How |
|---|---|
| Change prices / add items | Edit `~/veg-mcp/catalog.json`. It's re-read on every call, so no restart is needed. |
| Restart MCP server | `systemctl --user restart veg-mcp` |
| MCP server logs | `journalctl --user -u veg-mcp -f` |
| Gateway logs | `openclaw logs --follow` |
| Health check | `openclaw status` / `openclaw doctor` |
| Open files from Windows | Explorer → `\\wsl$\Ubuntu-24.04\home\<user>\veg-mcp` |

## Troubleshooting

| Symptom | Fix |
|---|---|
| `openclaw: command not found` | Run `exec bash`. If still missing: `export PATH="$(npm prefix -g)/bin:$PATH"` and add that line to `~/.bashrc`. |
| Gateway service won't install | systemd isn't running. Redo the check in step 1. |
| `VEG_MCP_TOKEN is not set` | `.env` is missing or empty in `~/veg-mcp`. Redo step 5. |
| MCP probe fails | Check `systemctl --user status veg-mcp`. The URL must include `?token=` and the token must match `.env`. |
| Bot doesn't reply | Run `openclaw channels status --probe`, then check `openclaw pairing list telegram` for an unapproved request. |
| Bot replies but never sends a PDF | Run `openclaw mcp doctor veggies --probe`. Ask it "list your tools" in Telegram to confirm it sees `veggies`. |
| Everything stops after closing Ubuntu | Run `sudo loginctl enable-linger "$USER"`. WSL also shuts down when idle; opening Ubuntu restarts both services. |
| Model/auth errors | `claude auth status --text`, then rerun the `openclaw models auth login ...` command from step 4. |

## Security notes

- Never commit `.env`. It's already in `.gitignore`.
- The MCP server and gateway bind to `127.0.0.1` only. Don't change `VEG_MCP_HOST` to `0.0.0.0` unless you know why.
- Keep Telegram DM policy on `pairing` (the default) so strangers can't place orders.
- Your Telegram bot token lives in `~/.openclaw/openclaw.json`. Don't share that file.
