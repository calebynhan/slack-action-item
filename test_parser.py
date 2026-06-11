import pytest

from parser import looks_like_summary, parse_action_items

# --- Format 1: numbered list, "task — Name" (trailing assignee) -------------

NUMBERED_TRAILING = """Action items:

1. Upload final analysis slides + create white paper from AP50 results — Kelly Anne Miller
2. Create NotebookLM presentation (Collage branding) — Jon M Millar
3. Schedule meeting with Alex re: TOS + privacy policy — Guy Aronson
4. Introduce Karen Nurenberg to team (Guy+Ori / Jon+Caleb+William) — Dan Braga
10. Participate in Partnership Success hiring process — *Ori Nurieli
"""


def test_trailing_assignee_numbered_list():
    items = parse_action_items(NUMBERED_TRAILING)
    assert len(items) == 5
    assert items[0].assignee == "Kelly Anne Miller"
    assert items[0].task.startswith("Upload final analysis slides")
    assert items[3].assignee == "Dan Braga"
    # leading "*" on the name is stripped
    assert items[4].assignee == "Ori Nurieli"


def test_trailing_date_is_not_an_assignee():
    items = parse_action_items(
        "7. Polish LinkedIn pages + websites; prep case study for May 29 — Jon M Millar")
    assert len(items) == 1
    assert items[0].assignee == "Jon M Millar"


# --- Format 2: lettered list, "Name — task" (leading assignee) --------------

LETTERED_LEADING = """a. Ori — Send English versions of Israeli institution logos to Jon.
b. Jon — Follow up with Jeff and Emmanuel on meeting requests.
e. Kelly — Share Stanford talk case study feedback with the team.
i. William — Draft webinar invitation email for ASU GSV/BAT attendees.
"""


def test_leading_assignee_lettered_list():
    items = parse_action_items(LETTERED_LEADING)
    assert [i.assignee for i in items] == ["Ori", "Jon", "Kelly", "William"]
    assert items[0].task == "Send English versions of Israeli institution logos to Jon"


# --- Format 3: bullets, "Name: task", with group items -----------------------

BULLETED_COLON = """Here's what is in Granola. Not super comprehensive but better than nothing:
• Devanshu: Schedule dedicated meeting for experience design ideas
• Devanshu: Create centralized feedback repository/platform for all user input
• John: Send action items summary to meeting summary Slack channel
• Team: Complete Google Search Console connection today
• Kelly: Create demo lessons for STEM and humanities subjects
• All: Coordinate email approvals through Dan before symposium (14-day window)
"""


def test_colon_assignee_bullets_and_groups():
    items = parse_action_items(BULLETED_COLON)
    assert len(items) == 6
    assert items[0].assignee == "Devanshu"
    groups = [i for i in items if i.is_group]
    assert [g.assignee for g in groups] == ["Team", "All"]
    assert groups[0].task == "Complete Google Search Console connection today"


def test_intro_sentence_is_not_an_item():
    items = parse_action_items("Here's what is in Granola. Not comprehensive:")
    assert items == []


# --- Slack @mentions ----------------------------------------------------------

def test_slack_mention_assignee():
    items = parse_action_items("- <@U012ABCDEF> — follow up on X\n"
                               "- finish the deck — <@U99ZYXWVUT>")
    assert len(items) == 2
    assert items[0].user_id == "U012ABCDEF"
    assert items[0].task == "follow up on X"
    assert items[1].user_id == "U99ZYXWVUT"


def test_at_handle_assignee():
    items = parse_action_items("@caleb — follow up on X")
    assert len(items) == 1
    assert items[0].assignee == "@caleb"
    assert items[0].user_id is None


# --- misc ---------------------------------------------------------------------

def test_headers_and_blank_lines_skipped():
    assert parse_action_items("Action items:\n\nNext steps:\n") == []


def test_hyphen_separator():
    items = parse_action_items("1. Ship the release - Dan Braga")
    assert len(items) == 1
    assert items[0].assignee == "Dan Braga"


def test_looks_like_summary():
    assert looks_like_summary(NUMBERED_TRAILING)
    assert looks_like_summary(BULLETED_COLON)        # 3+ items, no header needed
    assert not looks_like_summary("hey Jon — lunch at noon?")
    assert not looks_like_summary("")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
