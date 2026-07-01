param(
    [string]$CondaEnv = "agno-assist",
    [string]$HostAddress = "127.0.0.1",
    [int]$ApiPort = 8080,
    [int]$McpPort = 8090,
    [int]$FrontendPort = 5173,
    [switch]$SkipInstall,
    [switch]$SkipViewerBuild
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

function Assert-Command {
    param([string]$Name)

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Command '$Name' was not found. Please install it or add it to PATH."
    }
}

function Invoke-Step {
    param(
        [string]$Title,
        [string]$WorkingDirectory,
        [scriptblock]$Script
    )

    Write-Host ""
    Write-Host "==> $Title" -ForegroundColor Cyan
    Push-Location $WorkingDirectory
    try {
        & $Script
    }
    finally {
        Pop-Location
    }
}

function ConvertTo-SingleQuotedPowerShell {
    param([string]$Value)

    return "'" + $Value.Replace("'", "''") + "'"
}

function Start-ServiceWindow {
    param(
        [string]$Title,
        [string]$WorkingDirectory,
        [string]$Command
    )

    $quotedTitle = ConvertTo-SingleQuotedPowerShell $Title
    $quotedDirectory = ConvertTo-SingleQuotedPowerShell $WorkingDirectory
    $quotedCommand = ConvertTo-SingleQuotedPowerShell $Command

    $windowScript = @"
`$Host.UI.RawUI.WindowTitle = $quotedTitle
Set-Location -LiteralPath $quotedDirectory
Write-Host ""
Write-Host $quotedTitle -ForegroundColor Cyan
Write-Host $quotedCommand
Write-Host ""
$Command
"@

    Start-Process `
        -FilePath "powershell.exe" `
        -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $windowScript) `
        -WorkingDirectory $WorkingDirectory
}

function New-CondaActivatedCommand {
    param(
        [string]$EnvironmentName,
        [string]$Command
    )

    $quotedEnvironmentName = ConvertTo-SingleQuotedPowerShell $EnvironmentName

    return @"
(& conda 'shell.powershell' 'hook') | Out-String | Invoke-Expression
conda activate $quotedEnvironmentName
$Command
"@
}

$FrontendDir = Join-Path $Root "frontend"
$ViewerDir = Join-Path $Root "services\three_dgs_mcp\viewer"

Assert-Command "conda"
Assert-Command "npm"

Invoke-Step "Checking Conda environment '$CondaEnv'" $Root {
    conda run -n $CondaEnv python --version
}

if (-not $SkipInstall) {
    if (-not (Test-Path (Join-Path $FrontendDir "node_modules"))) {
        Invoke-Step "Installing frontend dependencies" $FrontendDir {
            npm install
        }
    }

    if (-not (Test-Path (Join-Path $ViewerDir "node_modules"))) {
        Invoke-Step "Installing 3DGS viewer dependencies" $ViewerDir {
            npm install
        }
    }
}

if (-not $SkipViewerBuild) {
    Invoke-Step "Building 3DGS MCP viewer" $ViewerDir {
        npm run build
    }
}

$McpCommand = New-CondaActivatedCommand $CondaEnv "python -m uvicorn services.three_dgs_mcp.server:app --host $HostAddress --port $McpPort"
$ApiCommand = New-CondaActivatedCommand $CondaEnv "python -m uvicorn api.main:app --host $HostAddress --port $ApiPort"
$FrontendCommand = ".\node_modules\.bin\vite.cmd --host=$HostAddress --port=$FrontendPort"

Start-ServiceWindow "Agent Material - 3DGS MCP :$McpPort" $Root $McpCommand
Start-Sleep -Seconds 2
Start-ServiceWindow "Agent Material - API :$ApiPort" $Root $ApiCommand
Start-Sleep -Seconds 2
Start-ServiceWindow "Agent Material - Frontend :$FrontendPort" $FrontendDir $FrontendCommand

Write-Host ""
Write-Host "Started development services:" -ForegroundColor Green
Write-Host "  Frontend: http://$HostAddress`:$FrontendPort"
Write-Host "  API:      http://$HostAddress`:$ApiPort/health"
Write-Host "  3DGS MCP: http://$HostAddress`:$McpPort/health"
Write-Host ""
Write-Host "Close the opened PowerShell windows, or press Ctrl+C inside them, to stop the services."
