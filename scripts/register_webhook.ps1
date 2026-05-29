$TOKEN   = $env:TELEGRAM_BOT_TOKEN
$NGROK   = $env:NGROK_PUBLIC_URL
$SECRET  = $env:WEBHOOK_SECRET

## CHECKS
## CMD: Get-ChildItem env:TELEGRAM_BOT_TOKEN, env:NGROK_PUBLIC_URL, env:WEBHOOK_SECRET
## RMB: no trailing '/' in the url


# Verify required environment variables are not empty
if (-not $TOKEN -or -not $NGROK -or -not $SECRET) {
    Throw "Missing required environment variables!"
}

Invoke-WebRequest -Uri "https://api.telegram.org/bot$TOKEN/setWebhook" `
    -Method POST `
    -ContentType "application/json" `
    -Body (@{
        url                  = "$NGROK/webhook/$SECRET"
        allowed_updates      = @("message")
        drop_pending_updates = $true
    } | ConvertTo-Json)
