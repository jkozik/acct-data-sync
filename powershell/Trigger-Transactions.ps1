<#
.SYNOPSIS
    Trigger the Plaid transactions export for one account, one at a time.

.DESCRIPTION
    Calls POST /exports/transactions/<account> on export_api.py (dell1, port
    8090). The bookkeeping software finds the resulting CSV itself via its
    "most recent file in this folder" convention, so this script's only job
    is to report success or a clear reason for failure.

.EXAMPLE
    .\Trigger-Transactions.ps1 -Account 301

.EXAMPLE
    # Pin per-account shortcuts to the Start menu with something like:
    powershell.exe -NoLogo -File "C:\path\to\Trigger-Transactions.ps1" -Account 301
#>
param(
    [Parameter(Mandatory)]
    [ValidateSet("101", "301", "302", "304")]
    [string]$Account,

    [string]$ApiBase = "http://192.168.100.121:8090"
)

$url = "$ApiBase/exports/transactions/$Account"

try {
    $resp = Invoke-RestMethod -Method Post -Uri $url -TimeoutSec 60
    Write-Host "OK: wrote $($resp.rows_written) rows to $($resp.output_path)" -ForegroundColor Green
    if ($resp.pending_excluded_count -gt 0) {
        Write-Host "NOTE: $($resp.pending_excluded_count) transaction(s) excluded -- still pending in Plaid (Plaid: +out/-in):" -ForegroundColor Yellow
        foreach ($t in $resp.pending_excluded) {
            Write-Host "  $($t.date)  $($t.amount)  $($t.description)" -ForegroundColor Yellow
        }
        Write-Host "  These will appear automatically in a future export once Plaid marks them posted." -ForegroundColor Yellow
    }
}
catch {
    $status = $null
    if ($_.Exception.Response) { $status = [int]$_.Exception.Response.StatusCode }

    $body = $null
    if ($_.ErrorDetails.Message) {
        try { $body = $_.ErrorDetails.Message | ConvertFrom-Json } catch {}
    }

    Write-Host "FAILED (HTTP $status) exporting transactions for account '$Account'" -ForegroundColor Red
    if ($body) {
        Write-Host "  source:  $($body.source)"
        Write-Host "  message: $($body.error_message)"
        if ($body.error_type)       { Write-Host "  Plaid error_type:  $($body.error_type)" }
        if ($body.error_code)       { Write-Host "  Plaid error_code:  $($body.error_code)" }
        if ($body.plaid_request_id) { Write-Host "  Plaid request_id:  $($body.plaid_request_id)" }
        if ($body.hint)             { Write-Host "  hint:    $($body.hint)" }
    }
    else {
        # No parseable JSON body -- likely the API/host is unreachable entirely
        # (dell1 down, wrong IP, port not open), not an error the API itself sent.
        Write-Host "  $($_.Exception.Message)"
        Write-Host "  (no JSON error body -- this usually means dell1/export_api.py couldn't be reached at all)"
    }
    exit 1
}
