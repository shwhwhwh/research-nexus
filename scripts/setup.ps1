param([string]$Python = 'python', [switch]$SkipNpm)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $projectRoot
try {
    $pythonPath = (& $Python -c 'import sys; assert sys.version_info >= (3,10); print(sys.executable)')
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.10+ is required.' }
    & $pythonPath -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
    if (!$SkipNpm) {
        & npm.cmd ci
        if ($LASTEXITCODE -ne 0) { throw 'Electron installation failed.' }
    }
    $runtime = @{python=$pythonPath} | ConvertTo-Json
    [IO.File]::WriteAllText((Join-Path $projectRoot 'runtime.local.json'), $runtime, (New-Object Text.UTF8Encoding($false)))
    & (Join-Path $projectRoot 'desktop\build-native-host.ps1')
    Write-Host 'Research Nexus is ready. Run npm start.'
} finally { Pop-Location }
