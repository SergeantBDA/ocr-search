chcp 65001 > $null
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)

$body = @{
  q      = "1166-2-2020"
  limit  = 20
  offset = 0
} | ConvertTo-Json -Depth 5 -Compress

$resp = Invoke-RestMethod -Method Post `
  -Uri "http://localhost:8000/api/search" `
  -Headers @{ "X-API-Key" = "key1"; "Content-Type" = "application/json; charset=utf-8" } `
  -Body ($body | ConvertTo-Json -Compress)
$resp