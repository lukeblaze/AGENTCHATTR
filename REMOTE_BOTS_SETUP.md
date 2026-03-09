# Remote Telegram + WhatsApp bridge (with fallback)

This project now includes webhook endpoints that let external chat platforms feed messages into agentchattr, and relay agent replies back out.

## What it does

- Inbound Telegram messages -> stored in channel `remote-tg-<chat_id>` (or renamed via command)
- Inbound WhatsApp messages -> stored in channel `remote-wa-<wa_user_id>`
- Agent replies in that channel -> sent back to user on preferred platform
- If WhatsApp free period is over, destination auto-switches to Telegram

## New endpoints

- `POST /api/bridge/telegram/webhook`
- `GET /api/bridge/whatsapp/webhook` (Meta verification)
- `POST /api/bridge/whatsapp/webhook`

All require `bridge_key` via query param or `x-bridge-key` header.

Example webhook URL pattern:

`https://YOUR-HOST/api/bridge/telegram/webhook?bridge_key=YOUR_SECRET`

`https://YOUR-HOST/api/bridge/whatsapp/webhook?bridge_key=YOUR_SECRET`

## Config

Set these under `[bridge]` in `config.local.toml` (recommended):

```toml
[bridge]
enabled = true
bridge_key = "replace-with-long-random-secret"
telegram_bot_token = "<bot token from BotFather>"
whatsapp_access_token = "<meta cloud api token>"
whatsapp_phone_number_id = "<phone-number-id>"
whatsapp_verify_token = "<token used in Meta webhook verify>"
default_whatsapp_free_until = "2026-12-31"
```

## Telegram setup

1. Create bot with BotFather.
2. Set webhook URL to:
   `https://YOUR-HOST/api/bridge/telegram/webhook?bridge_key=YOUR_SECRET`
3. Start chat with your bot and send `/help`.

Useful Telegram bot commands:

- `/channel <name>`
- `/linkwa <whatsapp-id-or-number>`
- `/wafreeuntil YYYY-MM-DD`
- `/prefer telegram|whatsapp`

## WhatsApp Cloud API setup

1. Create app in Meta developers console.
2. Enable WhatsApp Cloud API and get:
   - access token
   - phone number id
3. Configure webhook callback URL:
   `https://YOUR-HOST/api/bridge/whatsapp/webhook?bridge_key=YOUR_SECRET`
4. Set verify token in Meta to match `whatsapp_verify_token`.

## Best free-ish hosting options (practical)

Free plans change often, but this order is usually most practical:

1. Railway starter credit (easy deploy, can sleep after credit)
2. Render free web service (may sleep)
3. Fly.io small shared VM (often cheapest for always-on)
4. Oracle Cloud Free VM (best always-on free option, more setup effort)

If you want always-on with minimal surprises, a tiny paid VM is usually more reliable than rotating free tiers.

## Cloud env vars

You can deploy without editing tracked config by setting:

- `AGENTCHATTR_HOST=0.0.0.0`
- `AGENTCHATTR_PORT=8300` (or platform port)
- `AGENTCHATTR_ALLOW_NETWORK=1`
- `AGENTCHATTR_BRIDGE_ENABLED=1`
- `AGENTCHATTR_BRIDGE_KEY=...`
- `TELEGRAM_BOT_TOKEN=...`
- `WHATSAPP_ACCESS_TOKEN=...`
- `WHATSAPP_PHONE_NUMBER_ID=...`
- `WHATSAPP_VERIFY_TOKEN=...`

Optional 24/7 wrapper supervision (keeps agent presence online continuously):

- `AGENTCHATTR_AUTO_START_WRAPPERS=1`
- `AGENTCHATTR_AUTO_START_AGENTS=all` (recommended)
   - or use a list: `agent1,agent2`
   - if unset, the supervisor now attempts all configured agents by default

If wrappers run outside the same host/container as the server, point them at your deployed URL:

- `AGENTCHATTR_SERVER_URL=https://YOUR-HOST`

Cloud-safe API agents (no CLI binaries required):

- This repo includes `config.cloud.toml` with two API agents: `openai`, `openrouter`.
- They auto-load at startup and are safe to commit because they reference env var names only.
- Set these env vars in your host:
   - `OPENAI_API_KEY=...`
   - `OPENROUTER_API_KEY=...`

## Quick deploy with Docker

This repo now includes a `Dockerfile`.

Build and run locally:

```bash
docker build -t agentchattr .
docker run -p 8300:8300 -e AGENTCHATTR_BRIDGE_ENABLED=1 -e AGENTCHATTR_BRIDGE_KEY=... agentchattr
```

## Security notes

- Keep `bridge_key` long and secret.
- Keep API tokens only in `config.local.toml` or environment-injected config.
- If deploying publicly, use HTTPS and avoid exposing open webhook endpoints without secret checks.

## Recommended workflow to VS Code

Best path for reliability:

- Agents implement changes in cloud runner -> push branch/PR on GitHub
- You review and merge in VS Code

Directly writing into your local VS Code from cloud is possible, but requires exposing a secure local bridge and is riskier.
