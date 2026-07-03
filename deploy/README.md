# deploy/

Operational scripts and configs for the Hetzner CX22 host (`root@46.225.218.207`, `/opt/NotZelda/`).

| File | Purpose |
|---|---|
| `setup_llamacpp.sh` | Install/refresh llama-server + GGUF + systemd unit. Idempotent. |
| `notzelda-llama.service` | Systemd unit template for `llama-server`. Rendered into `/etc/systemd/system/` by `setup_llamacpp.sh`. |
| `uninstall_ollama.sh` | One-shot cleanup of the old Ollama install. Run after llama-server is verified. |
| `notzelda.nginx.conf` | Nginx site config (HTTP -> game on :8080). |
| `notzelda_redirect` | Static landing page for the redirect domain. |

## Routine deploy (after first-time setup is done)

```bash
ssh root@46.225.218.207
cd /opt/NotZelda
git pull
bash deploy/setup_llamacpp.sh   # no-op once llama.cpp + model are in place
systemctl restart notzelda
journalctl -u notzelda -n 30 --no-pager
```

`setup_llamacpp.sh` is safe in the deploy hot path: it short-circuits when the
release tag and model file are already on disk. If you want to force a llama.cpp
upgrade, set `LLAMACPP_VERSION=bXXXX bash deploy/setup_llamacpp.sh` (or just
`rm /opt/llama.cpp/INSTALLED_VERSION` to re-pull `latest`).

## First-time setup on a fresh box

1. Clone the repo to `/opt/NotZelda/` and create the venv (one-time):
   ```bash
   git clone <repo> /opt/NotZelda
   cd /opt/NotZelda
   python3 -m venv venv
   venv/bin/pip install -r requirements.txt
   ```
2. Drop a `notzelda.service` file pointing at `venv/bin/python3 mud_server.py`
   (see `systemctl cat notzelda` on the running host for the canonical version).
3. Copy `server.env` -> `.env` and fill in secrets.
4. Run the llama-server bringup:
   ```bash
   bash deploy/setup_llamacpp.sh
   ```
5. Edit `.env` per the script's final hint:
   ```
   AI_BACKEND=llamacpp
   LLAMACPP_BASE_URL=http://localhost:8081/v1
   LLAMACPP_MODEL=gemma-2-2b-it-Q4_K_M
   ```
6. `systemctl enable --now notzelda` and verify NPC chat in-game.
7. Once verified, retire Ollama:
   ```bash
   bash deploy/uninstall_ollama.sh
   ```

## Knobs (env vars for `setup_llamacpp.sh`)

| Var | Default | Purpose |
|---|---|---|
| `LLAMACPP_VERSION` | `latest` | GitHub release tag (e.g. `b9010`). Pin for reproducible deploys. |
| `LLAMACPP_DIR` | `/opt/llama.cpp` | Where the release tarball is extracted. |
| `MODELS_DIR` | `/opt/NotZelda/models` | Where GGUFs live (gitignored). |
| `MODEL_FILE` | `gemma-2-2b-it-Q4_K_M.gguf` | GGUF filename inside `MODELS_DIR`. |
| `MODEL_URL` | bartowski's gemma 2 2B Q4_K_M | Direct download URL. |
| `LLAMA_PORT` | `8081` | Avoids the game server on 8080. |
| `LLAMA_CTX_SIZE` | `1024` | Match to `MAX_HISTORY` * msg length in `server/npc_chat.py`. |

## Why port 8081?

`mud_server.py` listens on 8080 (HTTP/WS) and 8443 (WSS). 8081 is the next
free port and stays bound to `127.0.0.1` so it's not publicly reachable —
nginx + the game server are the only public entry points.
