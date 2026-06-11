"""Slack bot that reads meeting summaries / action items and DMs each
assignee their items (falling back to @-mentioning them in the thread).

Triggers:
  * someone @mentions the bot on (or in a thread under) a summary message
  * any message that looks like an action-item summary (incl. bot posts)

Run with Socket Mode: python app.py
"""

import logging
import os
import re
from collections import defaultdict
from typing import Dict, List, Optional

from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from parser import ActionItem, looks_like_summary, parse_action_items

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = App(token=os.environ["SLACK_BOT_TOKEN"])

# ---------------------------------------------------------------- user lookup

_user_index: Dict[str, List[str]] = {}   # normalized name -> [user_id, ...]


def _normalize(name: str) -> str:
    return re.sub(r"[^a-z ]", "", name.lower()).strip()


def _build_user_index(client) -> None:
    _user_index.clear()
    cursor = None
    while True:
        resp = client.users_list(cursor=cursor, limit=200)
        for user in resp["members"]:
            if user.get("deleted") or user.get("is_bot") or user["id"] == "USLACKBOT":
                continue
            profile = user.get("profile", {})
            names = {profile.get("real_name", ""), profile.get("display_name", ""),
                     user.get("name", "")}
            first_names = {n.split()[0] for n in names if n}
            for n in names | first_names:
                key = _normalize(n)
                if key and user["id"] not in _user_index.setdefault(key, []):
                    _user_index[key].append(user["id"])
        cursor = resp.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break


def resolve_user(client, name: str) -> Optional[str]:
    """Map a written name to a Slack user ID; None if unknown or ambiguous."""
    if not _user_index:
        _build_user_index(client)
    key = _normalize(name.lstrip("@"))
    candidates = _user_index.get(key, [])
    return candidates[0] if len(candidates) == 1 else None


# ---------------------------------------------------------------- delivery

def _dm_items(client, user_id: str, items: List[ActionItem], permalink: str) -> bool:
    lines = "\n".join(f"• {item.task}" for item in items)
    text = (f":clipboard: You have {len(items)} action item"
            f"{'s' if len(items) != 1 else ''} from a meeting summary:\n{lines}")
    if permalink:
        text += f"\n\n<{permalink}|View the original summary>"
    try:
        channel = client.conversations_open(users=user_id)["channel"]["id"]
        client.chat_postMessage(channel=channel, text=text)
        return True
    except Exception:
        logger.exception("Failed to DM %s", user_id)
        return False


def process_summary(client, channel: str, ts: str, text: str) -> None:
    items = parse_action_items(text)
    if not items:
        return

    try:
        permalink = client.chat_getPermalink(channel=channel, message_ts=ts)["permalink"]
    except Exception:
        permalink = ""

    by_user: Dict[str, List[ActionItem]] = defaultdict(list)
    unresolved: List[ActionItem] = []
    group_items: List[ActionItem] = []
    for item in items:
        if item.is_group:
            group_items.append(item)
            continue
        user_id = item.user_id or resolve_user(client, item.assignee)
        if user_id:
            by_user[user_id].append(item)
        else:
            unresolved.append(item)

    dmed = [uid for uid, user_items in by_user.items()
            if _dm_items(client, uid, user_items, permalink)]

    # Thread reply: confirm delivery and @-mention anyone we couldn't DM.
    reply_lines = []
    if dmed:
        reply_lines.append(
            "DM'd action items to " + ", ".join(f"<@{uid}>" for uid in dmed) + ".")
    for item in unresolved:
        reply_lines.append(
            f"Couldn't match *{item.assignee}* to a Slack user — their item: {item.task}")
    for item in group_items:
        reply_lines.append(f"For the whole team: {item.task}")
    if reply_lines:
        client.chat_postMessage(channel=channel, thread_ts=ts, text="\n".join(reply_lines))


# ---------------------------------------------------------------- handlers

@app.event("app_mention")
def on_mention(event, client, context):
    text = re.sub(rf"<@{context.bot_user_id}(?:\|[^>]*)?>", "", event.get("text", ""))
    channel, ts = event["channel"], event["ts"]

    if parse_action_items(text):
        process_summary(client, channel, ts, text)
        return

    # Mentioned in a thread under a summary: parse the thread's parent message.
    parent_ts = event.get("thread_ts")
    if parent_ts and parent_ts != ts:
        parent = client.conversations_replies(
            channel=channel, ts=parent_ts, limit=1)["messages"][0]
        if parse_action_items(parent.get("text", "")):
            process_summary(client, channel, parent_ts, parent.get("text", ""))
            return

    client.chat_postMessage(
        channel=channel, thread_ts=ts,
        text="I couldn't find any action items here. Mention me on a summary "
             "with lines like `Task — Name`, `Name — task`, or `Name: task`.")


@app.event("message")
def on_message(event, client, context):
    if event.get("subtype") in {"message_changed", "message_deleted", "channel_join"}:
        return
    if event.get("bot_id") and event.get("bot_id") == context.get("bot_id"):
        return  # never react to our own posts
    if event.get("user") == context.bot_user_id:
        return
    text = event.get("text", "")
    if f"<@{context.bot_user_id}>" in text:
        return  # handled by app_mention
    if looks_like_summary(text):
        process_summary(client, event["channel"], event["ts"], text)


if __name__ == "__main__":
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()
