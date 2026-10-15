"""Resolve a specific account_id within a Plaid item (an item can bundle multiple accounts)."""
import plaid
from plaid.model.accounts_get_request import AccountsGetRequest

from plaid_client import client, raise_friendly_if_login_required


def get_account_id_by_mask(access_token, mask):
    """Return the account_id whose last-4-digits mask matches, e.g. '1018' or '1818'."""
    try:
        resp = client.accounts_get(AccountsGetRequest(access_token=access_token))
    except plaid.ApiException as e:
        raise_friendly_if_login_required(e)
    for account in resp.accounts:
        if account.mask == mask:
            return account.account_id
    raise KeyError(f"No account with mask {mask!r} found on this item")
