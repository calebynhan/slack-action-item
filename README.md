# meeting-dm-bot

Slack bot that reads meeting summaries / action items posted in a channel and
DMs each person their items — or @-mentions them in a thread when a name can't
be matched to a Slack user.

## How it works

1. **Trigger** — either:
   - a message that looks like an action-item summary is posted (including by
     other bots, e.g. a meeting-notes integration), or
   - someone @mentions this bot on a summary message (or in a thread under one).
2. **Parse** — `parser.py` extracts `(assignee, task)` pairs. Supported line
   shapes (numbered, lettered, or bulleted lists all work):
   - `Upload final slides — Kelly Anne Miller` (task — Name)
   - `Ori — Send logos to Jon` (Name — task)
   - `Devanshu: Schedule meeting` (Name: task)
   - `<@U012ABCDEF> — follow up on X` (Slack mention)
   - `Team:` / `All:` items are surfaced to the whole thread.
3. **Deliver** — names are matched against the workspace user list (real name,
   display name, or unique first name), then `conversations_open()` +
   `chat_postMessage()` DMs each person their items with a permalink back to
   the summary. A thread reply confirms delivery and @-mentions anyone whose
   items couldn't be DM'd.

## Setup

1. Create a Slack app (https://api.slack.com/apps) and enable **Socket Mode**.
2. Bot token scopes: `app_mentions:read`, `channels:history`, `chat:write`,
   `im:write`, `users:read`.
3. Event subscriptions (bot events): `app_mention`, `message.channels`.
4. Install to the workspace, invite the bot to the summary channel.
5. Configure and run:

```bash
cp .env.example .env   # fill in SLACK_BOT_TOKEN and SLACK_APP_TOKEN
pip install -r requirements.txt
python app.py
```

## Tests

```bash
pytest test_parser.py -v
```

## Deploying to the cloud (always-on)

The bot uses Socket Mode, so it runs as a background worker — no public URL,
port, or webhook configuration needed. Any host that runs a long-lived process
works. Set `SLACK_BOT_TOKEN` and `SLACK_APP_TOKEN` as environment variables in
the host's dashboard (do NOT commit `.env`).

**Railway** (simplest):
1. https://railway.app → New Project → Deploy from GitHub repo → pick this repo.
2. Railway auto-detects the `Dockerfile` and builds it.
3. In the service's *Variables* tab, add `SLACK_BOT_TOKEN` and `SLACK_APP_TOKEN`.
4. Deploy. Logs should show `Bolt app is running!`.

**Render**: New → Background Worker → connect this repo (uses the `Dockerfile`
or `Procfile`), add the two env vars, deploy.

**Fly.io / any Docker host**: `docker build -t meeting-dm-bot .` then run with
`-e SLACK_BOT_TOKEN=... -e SLACK_APP_TOKEN=...`.
