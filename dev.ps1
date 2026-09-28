# Starts the API (uvicorn on :8000) and the Vite dev server together.
# Ctrl+C stops both.

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot

function Stop-Tree([System.Diagnostics.Process] $Process) {
    if ($null -eq $Process) { return }
    if ($Process.HasExited) { return }
    & taskkill.exe /PID $Process.Id /T /F | Out-Null
}

$backend = Start-Process -FilePath "python" `
    -ArgumentList "-m", "uvicorn", "app.main:app", "--reload", "--host", "127.0.0.1", "--port", "8000" `
    -WorkingDirectory (Join-Path $Root "backend") `
    -PassThru -NoNewWindow

$frontend = Start-Process -FilePath "npm.cmd" `
    -ArgumentList "run", "dev" `
    -WorkingDirectory (Join-Path $Root "frontend") `
    -PassThru -NoNewWindow

Write-Host "Backend  http://127.0.0.1:8000"
Write-Host "Frontend http://127.0.0.1:5173"
Write-Host "Press Ctrl+C to stop both."

try {
    while (-not $backend.HasExited -and -not $frontend.HasExited) {
        Start-Sleep -Milliseconds 400
    }
    if ($backend.HasExited) {
        Write-Host "Backend exited ($($backend.ExitCode)). Stopping frontend."
    }
    if ($frontend.HasExited) {
        Write-Host "Frontend exited ($($frontend.ExitCode)). Stopping backend."
    }
}
finally {
    Stop-Tree $backend
    Stop-Tree $frontend
}
