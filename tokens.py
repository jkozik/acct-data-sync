"""Read/write tokens.json — a git-ignored file mapping a label to Plaid item info."""
import json
import os

TOKENS_PATH = os.path.join(os.path.dirname(__file__), "tokens.json")


def load_tokens():
    if not os.path.exists(TOKENS_PATH):
        return {}
    with open(TOKENS_PATH) as f:
        return json.load(f)


def save_token(label, access_token, item_id):
    tokens = load_tokens()
    tokens[label] = {"access_token": access_token, "item_id": item_id}
    with open(TOKENS_PATH, "w") as f:
        json.dump(tokens, f, indent=2)


def get_access_token(label):
    tokens = load_tokens()
    if label not in tokens:
        raise KeyError(f"No stored token for label {label!r}. Run link_app.py and connect this account first.")
    return tokens[label]["access_token"]
