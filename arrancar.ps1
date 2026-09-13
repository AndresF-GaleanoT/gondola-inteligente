# ============================================================================
# ARRANCAR TODO - G-ndola Inteligente
# Levanta el backend FastAPI (http://localhost:8000) y el frontend Vite
# (http://localhost:5173) desde la raiz del repo. Mata primero los procesos
# viejos de uvicorn/vite que apunten a este proyecto para evitar puertos
# ocupados por instancias anteriores (reloader/worker).
# Uso:  powershell -ExecutionPolicy Bypass -File .\arrancar.ps1
# ============================================================================

$ErrorActionPreference = "Stop"

$Root = $PSScriptRoot
$Frontend = Join-Path $Root "frontend"
$Logs = Join-Path $Root "outputs"
New-Item -ItemType Directory -Force -Path $Logs | Out-Null

function Stop-ProcesosDelProyecto {
  # Uvicorn del backend (el CLI se lanza como: python -m uvicorn backend.main:app ...).
  Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*uvicorn backend.main:app*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

  # Vite del frontend (npm run dev -> node ...frontend\node_modules\vite\bin\vite.js).
  Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*vite*" -and $_.CommandLine -like "*$Frontend*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

  Start-Sleep -Seconds 1
}

function Esperar-Puerto($puerto, $etiqueta, $segundos = 60) {
  for ($i = 0; $i -lt $segundos; $i++) {
    if (Get-NetTCPConnection -LocalPort $puerto -State Listen -ErrorAction SilentlyContinue) {
      Write-Host "  [OK] $etiqueta escuchando en :$puerto"
      return $true
    }
    Start-Sleep -Seconds 1
  }
  Write-Host "  [ERROR] $etiqueta no escucho en :$puerto tras $segundos segundos."
  return $false
}

Write-Host "== Arrancando G-ndola Inteligente =="
Write-Host "[1/3] Deteniendo instancias anteriores..." -NoNewline
Stop-ProcesosDelProyecto
Write-Host " listo."

Write-Host "[2/3] Backend (uvicorn :8000)..."
$backendLog = Join-Path $Logs "uvicorn.log"
$backendErr = Join-Path $Logs "uvicorn_err.log"
Start-Process -FilePath "python" `
  -ArgumentList "-m", "uvicorn", "backend.main:app", "--reload", `
    "--reload-dir", "app", "--reload-dir", "backend", `
    "--reload-exclude", "app/config.py", `
    "--port", "8000", "--host", "127.0.0.1" `
  -WorkingDirectory $Root `
  -RedirectStandardOutput $backendLog `
  -RedirectStandardError $backendErr `
  -WindowStyle Hidden
$okBackend = Esperar-Puerto 8000 "Backend" 60

# Torch tarda unos segundos en importar; el puerto puede escuchar antes de que
# la app este lista. Se espera tambien a que /api/estado responda.
if ($okBackend) {
  for ($i = 0; $i -lt 30; $i++) {
    try {
      $r = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/estado" -UseBasicParsing -TimeoutSec 5
      if ($r.StatusCode -eq 200) { Write-Host "  [OK] Backend respondio en /api/estado"; break }
    } catch { }
    Start-Sleep -Seconds 2
    if ($i -eq 29) { Write-Host "  [ERROR] Backend escucha pero /api/estado no responde."; $okBackend = $false }
  }
}

Write-Host "[3/3] Frontend (Vite :5173)..."
$viteLog = Join-Path $Logs "vite.log"
# npm es un .cmd; Start-Process lo lanza de forma fiable via cmd.exe /c, con la
# redireccion a log dentro del propio cmd (asi no se cuelga el script esperando
# el cierre de los handles de salida del hijo).
$cmdVite = "npm run dev > `"$viteLog`" 2>&1"
Start-Process -FilePath "cmd.exe" `
  -ArgumentList "/c", $cmdVite `
  -WorkingDirectory $Frontend `
  -WindowStyle Hidden
$okFrontend = Esperar-Puerto 5173 "Frontend"

Write-Host ""
if ($okBackend -and $okFrontend) {
  Write-Host "Todo arriba:"
  Write-Host "   Dashboard  ->  http://localhost:5173"
  Write-Host "   Backend API -> http://localhost:8000/api/estado"
  Write-Host "   Logs: $backendLog y $viteLog"
} else {
  Write-Host "Hubo errores. Revisa:"
  Write-Host "   Backend : $(Get-Content $backendErr -ErrorAction SilentlyContinue | Select-Object -Last 8) $($backendErr)"
  Write-Host "   Frontend: $viteLog"
  exit 1
}