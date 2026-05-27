$TOKEN  = "8766500366:AAG4OnAyqdPCusI1ENzjduXKQGyerQeeA7E"
$NGROK  = "https://lifting-sinister-pectin.ngrok-free.dev"   # your current ngrok URL
$SECRET = "2d54b4be5794a28cf43a7e0aaa4a422c075086dcccb76aaf1a91935368387af4"

Invoke-WebRequest -Uri "https://api.telegram.org/bot$TOKEN/setWebhook" `
    -Method POST `
    -ContentType "application/json" `
    -Body (@{
        url             = "$NGROK/webhook/$SECRET"
        allowed_updates = @("message")
    } | ConvertTo-Json)