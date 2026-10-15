<#
.SYNOPSIS
    Fetch a credit card's current + last statement balance and copy it to the
    clipboard as a journal entry, ready to paste into the bookkeeping software.

.DESCRIPTION
    Calls POST /exports/balance/<account> on export_api.py (dell1, port 8090).
    The response carries the numbers directly (no separate file-fetch step
    needed), which get formatted into a 4-line journal entry (JSON array) and
    copied to the clipboard, ready to paste into the bookkeeping software.

    Only 301, 302, and 304 support this -- checking has no statement-balance
    reconciliation step.

    The API call and the clipboard copy are handled as separate failure modes:
    a busy/locked clipboard (a transient Windows-local issue, not a network
    one) is retried a few times, and if it still fails the fetched value is
    printed so it isn't lost -- it should never be reported as if dell1 or
    export_api.py were unreachable.

.EXAMPLE
    .\Get-Balance.ps1 -Account 301
#>
param(
    [Parameter(Mandatory)]
    [ValidateSet("301", "302", "304")]
    [string]$Account,

    [string]$ApiBase = "http://192.168.100.121:8090"
)

$url = "$ApiBase/exports/balance/$Account"

try {
    $resp = Invoke-RestMethod -Method Post -Uri $url -TimeoutSec 60
}
catch {
    $status = $null
    if ($_.Exception.Response) { $status = [int]$_.Exception.Response.StatusCode }

    $body = $null
    if ($_.ErrorDetails.Message) {
        try { $body = $_.ErrorDetails.Message | ConvertFrom-Json } catch {}
    }

    Write-Host "FAILED (HTTP $status) fetching balance for account '$Account'" -ForegroundColor Red
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

# The API call succeeded -- everything past this point (journal-entry
# formatting, clipboard) is local and shouldn't be mislabeled as a
# dell1/network failure if it goes wrong.
$mmdd    = (Get-Date).ToString("MMdd")
$acct    = "140"
$curBal  = if ([string]::IsNullOrWhiteSpace($resp.currentBalance))      { "0.00" } else { $resp.currentBalance }
$stmtBal = if ([string]::IsNullOrWhiteSpace($resp.lastStatementBalance)) { "0.00" } else { $resp.lastStatementBalance }

# Negate a numeric string (toggle leading minus)
function Neg($n) { if ($n -match "^-") { $n.Substring(1) } else { "-$n" } }

$negCur  = Neg $curBal
$negStmt = Neg $stmtBal

$entries = @(
    [ordered]@{ line = "$mmdd,-$acct,$negCur;$Account-,AcctBal * -1";  mmdd = $mmdd; acctamt = @([ordered]@{ acct = $acct; amt = $negCur  }); cract = $Account; desc = "AcctBal * -1"  },
    [ordered]@{ line = "$mmdd,-$acct,$stmtBal;$Account-,StmtBal";       mmdd = $mmdd; acctamt = @([ordered]@{ acct = $acct; amt = $stmtBal }); cract = $Account; desc = "StmtBal"        },
    [ordered]@{ line = "$mmdd,-$acct,$negStmt;$Account-,StmtBal * -1";  mmdd = $mmdd; acctamt = @([ordered]@{ acct = $acct; amt = $negStmt  }); cract = $Account; desc = "StmtBal * -1"  },
    [ordered]@{ line = "$mmdd,-$acct,$curBal;$Account-,AcctBal";        mmdd = $mmdd; acctamt = @([ordered]@{ acct = $acct; amt = $curBal   }); cract = $Account; desc = "AcctBal"        }
)

$clip = $entries | ConvertTo-Json -Depth 3

$copied = $false
for ($i = 1; $i -le 3 -and -not $copied; $i++) {
    try {
        Set-Clipboard -Value $clip
        $copied = $true
    }
    catch {
        if ($i -lt 3) { Start-Sleep -Milliseconds 300 }
    }
}

Write-Host $clip -ForegroundColor Cyan
if ($copied) {
    Write-Host "OK: copied to clipboard  (AcctBal: $curBal  StmtBal: $stmtBal)" -ForegroundColor Green
}
else {
    Write-Host "Fetched balance OK, but clipboard copy failed after 3 tries (clipboard busy/locked by another app):" -ForegroundColor Yellow
    Write-Host "  Copy the JSON above manually. If this keeps happening, check for a clipboard manager, Clipboard History (Win+V) / Cloud Clipboard sync, or an RDP session grabbing the clipboard." -ForegroundColor Yellow
}
