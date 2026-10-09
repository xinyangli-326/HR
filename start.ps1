$ErrorActionPreference = 'Stop'
$here = $PSScriptRoot
$parent = Split-Path $here -Parent
# 支持两种目录结构：本机工程 <project>\outputs\hr-review\start.ps1，或仓库根目录直接放 server.py
if ((Split-Path $parent -Leaf) -eq 'outputs') {
    $root = Split-Path $parent -Parent
} else {
    $root = $here
}
$server = Join-Path $here 'server.py'
$work = Join-Path $root 'work'
New-Item -ItemType Directory -Path $work -Force | Out-Null
$env:HR_DATA_DIR = Join-Path $work 'hr-private'
Set-Location -LiteralPath $root
$python = (Get-Command python -ErrorAction Stop).Source

# 端口探测用 TCP 连接，避免依赖 Get-NetTCPConnection（无权限时会静默失败，导致重复启动）
function Test-PortOpen([int]$port) {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $async = $client.BeginConnect('127.0.0.1', $port, $null, $null)
        if (-not $async.AsyncWaitHandle.WaitOne(1000)) { return $false }
        $client.EndConnect($async)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}
if (Test-PortOpen 8765) {
    Write-Output 'Port 8765 is already in use. Existing app: http://127.0.0.1:8765'
    exit
}
Start-Process -FilePath $python -ArgumentList $server,'--port','8765' -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput (Join-Path $work 'server.log') -RedirectStandardError (Join-Path $work 'server-error.log')
Write-Output 'Local app: http://127.0.0.1:8765'
