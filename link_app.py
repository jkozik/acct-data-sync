"""
Minimal Plaid Link scaffold.

Run with:  .venv/bin/python link_app.py
Then open the URL it prints (see console output) in a browser.
"""
import plaid
from flask import Flask, request, jsonify, render_template_string
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.products import Products
from plaid.model.country_code import CountryCode

from plaid_client import client, PLAID_PRODUCTS, PLAID_COUNTRY_CODES, PLAID_ENV
from tokens import save_token, get_access_token

app = Flask(__name__)

PAGE = """
<!doctype html>
<html>
<head><title>Plaid Link ({{ env }})</title></head>
<body style="font-family: sans-serif; max-width: 480px; margin: 40px auto;">
  <h2>Plaid Link &mdash; {{ env }}</h2>
  <p>Label for this account (used as the key in tokens.json), e.g. <code>chase_checking</code>:</p>
  <input id="label" style="width:100%; padding:8px;" value="chase_checking">
  <p><button id="link-btn" style="padding:10px 20px; font-size:16px;">Connect account</button></p>
  <pre id="status"></pre>

  <hr style="margin-top:40px;">
  <h3>Update an existing item (update mode)</h3>
  <p>Label of the already-linked account, e.g. <code>chase_household_login</code>:</p>
  <input id="update-label" style="width:100%; padding:8px;" value="chase_household_login">
  <p>Product to add (e.g. <code>liabilities</code>), or leave blank to just re-open
     Link for re-authentication / selecting additional accounts:</p>
  <input id="update-product" style="width:100%; padding:8px;" value="">
  <p><button id="update-btn" style="padding:10px 20px; font-size:16px;">Update</button></p>
  <pre id="update-status"></pre>

  <script src="https://cdn.plaid.com/link/v2/stable/link-initialize.js"></script>
  <script>
    const statusEl = document.getElementById('status');

    document.getElementById('link-btn').onclick = async () => {
      statusEl.textContent = 'Creating link token...';
      const ltRes = await fetch('/create_link_token', { method: 'POST' });
      const ltData = await ltRes.json();
      if (ltData.error) {
        statusEl.textContent = 'Error creating link token: ' + JSON.stringify(ltData.error);
        return;
      }

      const handler = Plaid.create({
        token: ltData.link_token,
        onSuccess: async (public_token, metadata) => {
          statusEl.textContent = 'Exchanging public token...';
          const label = document.getElementById('label').value.trim() || 'default';
          const exRes = await fetch('/exchange_public_token', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ public_token, label })
          });
          const exData = await exRes.json();
          if (exData.error) {
            statusEl.textContent = 'Error exchanging token: ' + JSON.stringify(exData.error);
          } else {
            statusEl.textContent = 'Success! Saved under label "' + exData.label +
              '"\\nitem_id: ' + exData.item_id +
              '\\n\\naccess_token saved to tokens.json (not shown here).';
          }
        },
        onExit: (err, metadata) => {
          if (err) statusEl.textContent = 'Link exited with error: ' + JSON.stringify(err);
        },
      });
      handler.open();
    };

    document.getElementById('update-btn').onclick = async () => {
      const statusEl2 = document.getElementById('update-status');
      const label = document.getElementById('update-label').value.trim();
      const product = document.getElementById('update-product').value.trim();
      if (!label) {
        statusEl2.textContent = 'Label is required.';
        return;
      }
      statusEl2.textContent = 'Creating update-mode link token...';
      const ltRes = await fetch('/create_update_link_token', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ label, product })
      });
      const ltData = await ltRes.json();
      if (ltData.error) {
        statusEl2.textContent = 'Error creating link token: ' + JSON.stringify(ltData.error);
        return;
      }

      const handler2 = Plaid.create({
        token: ltData.link_token,
        onSuccess: async (public_token, metadata) => {
          statusEl2.textContent = 'Exchanging public token...';
          const exRes = await fetch('/exchange_public_token', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ public_token, label })
          });
          const exData = await exRes.json();
          if (exData.error) {
            statusEl2.textContent = 'Error exchanging token: ' + JSON.stringify(exData.error);
          } else {
            const what = product ? ('"' + product + '" consent added') : 'Update complete';
            statusEl2.textContent = what + ' for label "' + exData.label +
              '"\\nitem_id: ' + exData.item_id;
          }
        },
        onExit: (err, metadata) => {
          if (err) statusEl2.textContent = 'Link exited with error: ' + JSON.stringify(err);
        },
      });
      handler2.open();
    };
  </script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(PAGE, env=PLAID_ENV)


@app.route("/create_link_token", methods=["POST"])
def create_link_token():
    try:
        req = LinkTokenCreateRequest(
            products=[Products(p) for p in PLAID_PRODUCTS],
            client_name="Personal Bookkeeping CSV Tool",
            country_codes=[CountryCode(c) for c in PLAID_COUNTRY_CODES],
            language="en",
            user=LinkTokenCreateRequestUser(client_user_id="local-single-user"),
        )
        resp = client.link_token_create(req)
        return jsonify({"link_token": resp.link_token})
    except plaid.ApiException as e:
        return jsonify({"error": e.body}), 400


@app.route("/create_update_link_token", methods=["POST"])
def create_update_link_token():
    """Update-mode link token for an existing item: either grants consent for an
    additional product (e.g. liabilities), or -- if product is left blank --
    just re-opens Link in update mode, which for institutions with account
    selection (like Chase) offers a 'select more accounts' step."""
    data = request.get_json()
    label = data["label"]
    product = (data.get("product") or "").strip()
    try:
        access_token = get_access_token(label)
    except KeyError as e:
        return jsonify({"error": str(e)}), 400
    try:
        kwargs = dict(
            access_token=access_token,
            client_name="Personal Bookkeeping CSV Tool",
            country_codes=[CountryCode(c) for c in PLAID_COUNTRY_CODES],
            language="en",
            user=LinkTokenCreateRequestUser(client_user_id="local-single-user"),
        )
        if product:
            kwargs["products"] = [Products(product)]
        req = LinkTokenCreateRequest(**kwargs)
        resp = client.link_token_create(req)
        return jsonify({"link_token": resp.link_token})
    except plaid.ApiException as e:
        return jsonify({"error": e.body}), 400


@app.route("/exchange_public_token", methods=["POST"])
def exchange_public_token():
    data = request.get_json()
    public_token = data["public_token"]
    label = data.get("label") or "default"
    try:
        req = ItemPublicTokenExchangeRequest(public_token=public_token)
        resp = client.item_public_token_exchange(req)
        save_token(label, resp.access_token, resp.item_id)
        return jsonify({"label": label, "item_id": resp.item_id})
    except plaid.ApiException as e:
        return jsonify({"error": e.body}), 400


if __name__ == "__main__":
    print(f"\nPlaid env: {PLAID_ENV}")
    print("Starting Link app on http://0.0.0.0:5001")
    print("Open this in a browser on dell1 itself:      http://localhost:5001")
    print("Or from another machine on your LAN:          http://<dell1-LAN-IP>:5001\n")
    app.run(host="0.0.0.0", port=5001)
