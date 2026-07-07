# G1 (Windows): frozen MaestroBackend.exe boots to /health and serves a /chat.
# Run from repo root: pwsh ./scripts/smoke_backend.ps1 [path-to-MaestroBackend.exe]
$ErrorActionPreference = "Stop"
$ROOT = (Resolve-Path "$PSScriptRoot/..").Path
$BACKEND = if ($args[0]) { $args[0] } else { Join-Path $ROOT "maestro\dist\backend\MaestroBackend.exe" }
$PORT = if ($env:MAESTRO_BACKEND_PORT) { $env:MAESTRO_BACKEND_PORT } else { "9200" }
$DATA = Join-Path $env:TEMP ("maestro-smoke-" + [guid]::NewGuid().ToString("N").Substring(0,8))
New-Item -ItemType Directory -Path $DATA -Force | Out-Null

if (-not (Test-Path $BACKEND)) { Write-Error "frozen backend not found: $BACKEND"; exit 2 }
Write-Host "smoke: $BACKEND on :$PORT (data: $DATA)"

$env:MAESTRO_DATA_DIR = $DATA
$env:MAESTRO_BACKEND_PORT = $PORT
$p = Start-Process -FilePath $BACKEND -PassThru -WindowStyle Hidden `
  -RedirectStandardOutput "$env:TEMP\maestro_smoke.log" `
  -RedirectStandardError "$env:TEMP\maestro_smoke_err.log"
try {
  $ok = $false
  for ($i = 0; $i -lt 60; $i++) {
    try { Invoke-RestMethod "http://127.0.0.1:$PORT/health" -ErrorAction Stop | Out-Null; $ok = $true; break } catch { Start-Sleep -Seconds 1 }
  }
  if (-not $ok) {
    Write-Error "FAIL: /health no response (60s)"
    Get-Content "$env:TEMP\maestro_smoke.log" -Tail 20 -ErrorAction SilentlyContinue
    exit 1
  }
  $h = Invoke-RestMethod "http://127.0.0.1:$PORT/health"
  Write-Host "/health: $($h | ConvertTo-Json -Compress)"
  $chat = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$PORT/chat" -ContentType "application/json" -Body '{"session_id":"smoke","message":"你好"}'
  $c = ($chat | ConvertTo-Json -Compress -Depth 5)
  Write-Host ("/chat: " + $c.Substring(0, [Math]::Min(200, $c.Length)))
  Write-Host "SMOKE OK"
} finally {
  Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
  Remove-Item -Recurse -Force $DATA -ErrorAction SilentlyContinue
}
