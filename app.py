import os
import sys
from datetime import datetime, timezone

from flask import Flask, jsonify, render_template
from slack_sdk.errors import SlackApiError

# Import core logic from the CLI tool
sys.path.insert(0, os.path.dirname(__file__))
from analyze_billing_issues import (
    WebClient,
    analyze,
    build_message_block,
    fetch_messages,
    get_channel_id,
)

app = Flask(__name__)

CHANNEL_NAME = "billing_support_tickets"


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/analyze")
def api_analyze():
    slack_token = os.environ.get("SLACK_BOT_TOKEN")
    if not slack_token:
        return jsonify({"error": "SLACK_BOT_TOKEN is not configured on the server."}), 500

    if not os.environ.get("ANTHROPIC_API_KEY"):
        return jsonify({"error": "ANTHROPIC_API_KEY is not configured on the server."}), 500

    try:
        slack = WebClient(token=slack_token)
        channel_id = get_channel_id(slack, CHANNEL_NAME)
        messages = fetch_messages(slack, channel_id)
    except SlackApiError as e:
        return jsonify({"error": f"Slack error: {e.response['error']}"}), 502
    except ValueError as e:
        return jsonify({"error": str(e)}), 404

    messages_text = build_message_block(messages)
    issues = analyze(messages_text)

    return jsonify(
        {
            "issues": issues,
            "message_count": len(messages),
            "channel": f"#{CHANNEL_NAME}",
            "analyzed_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        }
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
