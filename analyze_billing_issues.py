#!/usr/bin/env python3
"""
Billing Issues Analyzer
Fetches the last 30 messages from #billing_support_tickets and ranks recurring billing issues.

Required environment variables:
  SLACK_BOT_TOKEN   - Slack bot token with channels:history and channels:read scopes
  ANTHROPIC_API_KEY - Anthropic API key
"""

import json
import os
import sys

import anthropic
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

CHANNEL_NAME = "billing_support_tickets"
MESSAGE_LIMIT = 30

SYSTEM_PROMPT = """\
You are a billing support analyst. You will receive raw Slack messages from a \
billing support channel. Each message is typically a support ticket summary \
posted by a support agent.

Your job:
1. Read every message and identify the core billing issue it describes.
2. Group messages that describe the same type of problem under a single label \
   (e.g. "Refund request", "Double charge", "Payment failed", "Pricing model switch").
3. Count how many messages belong to each group.
4. Discard groups with only 1 message — only recurring issues matter.
5. Rank the remaining groups from most frequent to least frequent.
6. For each group pick a short, representative snippet (≤120 chars) from one of \
   its messages as an example.

Respond with ONLY a JSON array. No prose, no markdown fences. Schema:
[
  {
    "issue_type": "<concise label>",
    "count": <integer>,
    "example": "<short quote from one of the matching messages>"
  }
]
""".strip()


def get_channel_id(client: WebClient, name: str) -> str:
    cursor = None
    while True:
        kwargs = {"types": "public_channel,private_channel", "limit": 200}
        if cursor:
            kwargs["cursor"] = cursor
        resp = client.conversations_list(**kwargs)
        for ch in resp["channels"]:
            if ch["name"] == name:
                return ch["id"]
        meta = resp.get("response_metadata", {})
        cursor = meta.get("next_cursor")
        if not cursor:
            break
    raise ValueError(f"Channel #{name} not found. Check the bot is a member of the channel.")


def fetch_messages(client: WebClient, channel_id: str) -> list[dict]:
    resp = client.conversations_history(channel=channel_id, limit=MESSAGE_LIMIT)
    return resp["messages"]


def build_message_block(messages: list[dict]) -> str:
    parts = []
    for i, msg in enumerate(messages, 1):
        text = msg.get("text", "").strip()
        if text:
            parts.append(f"[{i}] {text}")
    return "\n\n".join(parts)


def analyze(messages_text: str) -> list[dict]:
    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=1024,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[
            {
                "role": "user",
                "content": f"Here are the last {MESSAGE_LIMIT} messages:\n\n{messages_text}",
            }
        ],
    )
    raw = response.content[0].text.strip()
    return json.loads(raw)


def print_report(issues: list[dict]) -> None:
    width = 64
    print()
    print("=" * width)
    print("  RECURRING BILLING ISSUES  —  ranked by frequency")
    print("=" * width)

    if not issues:
        print("\n  No recurring issues found — all problems appeared only once.\n")
        print("=" * width)
        return

    for rank, item in enumerate(issues, 1):
        label = item["issue_type"]
        count = item["count"]
        example = item.get("example", "")
        print(f"\n  #{rank}  {label}  ×{count}")
        if example:
            # Wrap example text at 58 chars
            words = example.split()
            line, lines = [], []
            for w in words:
                if sum(len(x) + 1 for x in line) + len(w) > 58:
                    lines.append(" ".join(line))
                    line = [w]
                else:
                    line.append(w)
            if line:
                lines.append(" ".join(line))
            print(f"      Example: \"{lines[0]}\"")
            for continuation in lines[1:]:
                print(f"               \"{continuation}\"")

    print()
    print("=" * width)
    print()


def main() -> None:
    slack_token = os.environ.get("SLACK_BOT_TOKEN")
    if not slack_token:
        sys.exit("Error: SLACK_BOT_TOKEN environment variable is not set.")

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("Error: ANTHROPIC_API_KEY environment variable is not set.")

    print(f"Connecting to Slack — fetching last {MESSAGE_LIMIT} messages from #{CHANNEL_NAME}...")

    try:
        slack = WebClient(token=slack_token)
        channel_id = get_channel_id(slack, CHANNEL_NAME)
        messages = fetch_messages(slack, channel_id)
    except SlackApiError as e:
        sys.exit(f"Slack API error: {e.response['error']}")
    except ValueError as e:
        sys.exit(str(e))

    print(f"Fetched {len(messages)} messages. Analyzing with Claude...")

    messages_text = build_message_block(messages)
    issues = analyze(messages_text)
    print_report(issues)


if __name__ == "__main__":
    main()
