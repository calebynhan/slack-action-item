"""Extract action items and assignees from meeting-summary text.

Supported line shapes (list markers like "1.", "a.", "-", "•" are stripped first):

    Upload final analysis slides — Kelly Anne Miller      (task — Name)
    Ori — Send English versions of logos to Jon           (Name — task)
    Devanshu: Schedule dedicated meeting                  (Name: task)
    <@U012ABCDEF> — follow up on X                        (Slack mention)
    Team: Complete Google Search Console connection       (group item)
    Jon & Caleb: Coordinate email approvals               (multi-assignee)
    Jon, Caleb, and William — review the deck             (multi-assignee)

Dashes may be em/en dashes or a spaced hyphen.
Multiple assignees separated by "&", "and", or "," each get their own item.
"""

import re
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ActionItem:
    assignee: str            # name exactly as written ("" only for group items)
    task: str
    user_id: Optional[str] = None   # Slack user ID when written as <@U...>
    is_group: bool = False          # Team / All / Everyone


GROUP_WORDS = {"team", "all", "everyone", "everybody"}

# Leading list markers: bullets, "1." / "1)", "a." / "a)"
_BULLET_RE = re.compile(r"^\s*(?:[-*•◦▪‣]+|\d{1,3}[.)]|[A-Za-z][.)])\s+")

# Separators between name and task
_DASH = r"(?:—|–|\s-\s|-\s)"

_MENTION_RE = re.compile(r"<@([A-Z0-9]+)(?:\|[^>]*)?>")

# A human name: optional leading "*", then 1-4 capitalized words,
# or an @handle, or a Slack <@U...> mention.
_NAME = r"\*?\s*(?:<@[A-Z0-9]+(?:\|[^>]*)?>|@[\w.\-]+|[A-Z][\w'’.\-]*(?:\s+[A-Z][\w'’.\-]*){0,3})"

# Multi-assignee leading prefix: "Jon & Caleb:" or "Jon, Caleb, and William —"
# Captured group 1 = raw names string, group 2 = task.
_NAME_PART = r"(?:<@[A-Z0-9]+(?:\|[^>]*)?>|@[\w.\-]+|[A-Z][\w''.\-]*(?:\s+[A-Z][\w''.\-]*)?)"
_NAME_SEP = r"(?:\s*(?:,\s*(?:and\s+)?|&\s*|\band\b\s*))"
_MULTI_NAME = rf"(\*?\s*{_NAME_PART}(?:{_NAME_SEP}{_NAME_PART})+)"
_MULTI_LEADING_RE = re.compile(rf"^{_MULTI_NAME}\s*(?:{_DASH}|:)\s*(.+)$")

_LEADING_RE = re.compile(rf"^({_NAME})\s*(?:{_DASH}|:)\s*(.+)$")
_TRAILING_RE = re.compile(rf"^(.+?)\s*{_DASH}\s*({_NAME})\s*$")

# Splits "Jon & Caleb", "Jon, Caleb, and William", etc. into individual names.
_NAME_SPLIT_RE = re.compile(r"\s*(?:,\s*(?:and\s+)?|&\s*|\band\b\s*)")

_HEADER_RE = re.compile(r"^(action items?|next steps?|to[- ]?dos?|follow[- ]?ups?)\s*:?\s*$", re.I)


def _clean_name(raw: str) -> str:
    return raw.lstrip("*").strip()


def _mention_id(name: str) -> Optional[str]:
    m = _MENTION_RE.fullmatch(name)
    return m.group(1) if m else None


def _is_plausible_name(name: str) -> bool:
    """Trailing-position guard so '... — May 29' or long clauses don't match."""
    if _mention_id(name) or name.startswith("@"):
        return True
    words = name.split()
    if not 1 <= len(words) <= 4:
        return False
    months = {"january", "february", "march", "april", "may", "june", "july",
              "august", "september", "october", "november", "december"}
    if words[0].lower() in months:
        return False
    return all(w[0].isupper() for w in words)


def _make_item(name: str, task: str) -> Optional[ActionItem]:
    name, task = _clean_name(name), task.strip().rstrip(".")
    if not name or not task:
        return None
    if name.lower() in GROUP_WORDS:
        return ActionItem(assignee=name, task=task, is_group=True)
    return ActionItem(assignee=name, task=task, user_id=_mention_id(name))


def _split_names(raw: str) -> List[str]:
    """Split "Jon & Caleb" or "Jon, Caleb, and William" into individual names."""
    return [n.strip() for n in _NAME_SPLIT_RE.split(raw.strip()) if n.strip()]


def parse_action_items(text: str) -> List[ActionItem]:
    """Parse a message and return one ActionItem per assigned line."""
    items: List[ActionItem] = []
    for line in (text or "").splitlines():
        line = _BULLET_RE.sub("", line.strip()).strip()
        if not line or _HEADER_RE.match(line):
            continue

        # Multi-assignee leading: "Jon & Caleb: task" or "Jon, Caleb, and William — task"
        m = _MULTI_LEADING_RE.match(line)
        if m:
            names_raw, task = m.group(1), m.group(2)
            names = _split_names(names_raw)
            if len(names) >= 2 and all(_is_plausible_name(_clean_name(n)) for n in names):
                for name in names:
                    item = _make_item(name, task)
                    if item:
                        items.append(item)
                continue

        # Single leading: "Jon: task" or "Jon — task"
        m = _LEADING_RE.match(line)
        if m and _is_plausible_name(_clean_name(m.group(1))):
            item = _make_item(m.group(1), m.group(2))
            if item:
                items.append(item)
                continue

        # Single trailing: "task — Kelly Anne Miller"
        m = _TRAILING_RE.match(line)
        if m and _is_plausible_name(_clean_name(m.group(2))):
            item = _make_item(m.group(2), m.group(1))
            if item:
                items.append(item)
    return items


def looks_like_summary(text: str) -> bool:
    """Heuristic gate for unsolicited messages: an action-item header keyword
    plus at least two parseable items, or three parseable items on their own."""
    if not text:
        return False
    items = parse_action_items(text)
    has_header = re.search(r"action items?|next steps?", text, re.I) is not None
    return (has_header and len(items) >= 2) or len(items) >= 3
