"""Fetch a real, current account balance from Plaid (for anchoring running-balance reconstruction)."""
import plaid
from plaid.model.accounts_balance_get_request import AccountsBalanceGetRequest

from plaid_client import client, raise_friendly_if_login_required


def get_current_balance(access_token, account_id):
    """Return the 'current' balance (float) for one account on an Item.

    /accounts/balance/get forces a fresh balance check with the institution
    (as opposed to a cached value), so this reflects all posted transactions
    at the moment of the call.
    """
    req = AccountsBalanceGetRequest(access_token=access_token)
    try:
        resp = client.accounts_balance_get(req)
    except plaid.ApiException as e:
        raise_friendly_if_login_required(e)
    for account in resp.accounts:
        if account.account_id == account_id:
            return account.balances.current
    raise KeyError(f"account_id {account_id!r} not found in /accounts/balance/get response")
