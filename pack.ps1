<#
.SYNOPSIS
    将 EaseAgent 项目打包为 zip，排除运行时数据和敏感文件。
.DESCRIPTION
    生成 easeagent-YYYYMMDD.zip，可直接发给同事。
    同事解压后按 docs/EaseAgent-使用说明.md 操作即可。
.EXAMPLE
    .\pack.ps1
    .\pack.ps1 -OutputName "easeagent-v4.zip"
#>
param(
    [string]$OutputName = "easeagent-$(Get-Date -Format 'yyyyMMdd').zip"
)

$ProjectRoot = $PSScriptRoot
$OutputPath  = Join-Path $ProjectRoot $OutputName

$ExcludeDirs = @(
    "venv", ".venv", "env",
    "__pycache__",
    "data",
    "logs",
    ".git",
    ".cursor",
    "node_modules"
)

$ExcludeFiles = @(
    ".env",
    "*.pyc",
    "*.pyo",
    "*.pt",
    "*.onnx",
    "*.log",
    "*.egg-info",
    "docker-compose.override.yml",
    "Thumbs.db",
    ".DS_Store"
)

Write-Host "[pack] Project root: $ProjectRoot" -ForegroundColor Cyan

$allFiles = Get-ChildItem -Path $ProjectRoot -Recurse -File

$filtered = $allFiles | Where-Object {
    $relativePath = $_.FullName.Substring($ProjectRoot.Length + 1)
    $parts = $relativePath -split '[/\\]'

    $inExcludedDir = $false
    foreach ($dir in $ExcludeDirs) {
        if ($parts -contains $dir) {
            $inExcludedDir = $true
            break
        }
    }
    if ($inExcludedDir) { return $false }

    foreach ($pattern in $ExcludeFiles) {
        if ($_.Name -like $pattern) { return $false }
    }

    return $true
}

$count = ($filtered | Measure-Object).Count
Write-Host "[pack] Packing $count files ..." -ForegroundColor Cyan

if (Test-Path $OutputPath) {
    Remove-Item $OutputPath -Force
}

$filtered | Compress-Archive -DestinationPath $OutputPath -CompressionLevel Optimal

$sizeMB = [math]::Round((Get-Item $OutputPath).Length / 1MB, 2)
Write-Host "[pack] Done: $OutputPath ($sizeMB MB, $count files)" -ForegroundColor Green
Write-Host ""
Write-Host "Checklist for recipient:" -ForegroundColor Yellow
Write-Host "  1. Unzip and cd into easeagent/"
Write-Host "  2. Copy .env.example to .env, fill in DASHSCOPE_API_KEY"
Write-Host "  3. python -m venv .venv && .venv\Scripts\activate"
Write-Host "  4. pip install -r requirements.txt"
Write-Host "  5. docker-compose up -d mosquitto redis chromadb"
Write-Host "  6. ollama serve  (new terminal)"
Write-Host "  7. ollama pull qwen3.5:9b"
Write-Host "  8. python run.py"
Write-Host "  9. Open http://localhost:8000/health?detail=true"
Write-Host ""
Write-Host "Full guide: docs/EaseAgent-使用说明.md" -ForegroundColor Yellow
Write-Host "Troubleshooting: docs/EaseAgent-排错指南.md" -ForegroundColor Yellow
