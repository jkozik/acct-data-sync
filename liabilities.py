"""Fetch credit card liability details (last statement balance, etc.) from Plaid.

Requires the item to have been granted consent for the 'liabilities' product
(via link_app.py's update-mode flow) -- a plain 'transactions'-only item will
raise ADDITIONAL_CONSENT_REQUIRED.
"""
import plaid
from plaid.model.liabilities_get_request import LiabilitiesGetRequest

from plaid_client import client, raise_friendly_if_login_required


def get_last_statement_balance(access_token, account_id):
    """Return the last statement balance (float) for one credit card account."""
    req = LiabilitiesGetRequest(access_token=access_token)
    try:
        resp = client.liabilities_get(req)
    except plaid.ApiException as e:
        raise_friendly_if_login_required(e)
    for credit in resp.liabilities.credit:
        if credit.account_id == account_id:
            return credit.last_statement_balance
    raise KeyError(f"account_id {account_id!r} not found in /liabilities/get response")
