# 一键生成《CodeMind-FZU 系统设计说明书》的 docx 与 PDF
# 依赖：pandoc、python-docx、Microsoft Word（通过 export_pdf.ps1 调用）

$ErrorActionPreference = 'Continue'
$env:PYTHONWARNINGS = 'ignore'

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$sourceDir = Split-Path -Parent $here
$designDir = Split-Path -Parent $sourceDir
$outDir = Join-Path $here 'out'
New-Item -ItemType Directory -Force $outDir | Out-Null

$ref = Join-Path $here 'reference.docx'
if (-not (Test-Path $ref)) {
    cmd /c "pandoc --print-default-data-file reference.docx > `"$ref`""
}

python (Join-Path $here 'make_reference.py') $ref
if ($LASTEXITCODE -ne 0) { throw 'make_reference.py 执行失败' }

$raw = Join-Path $outDir 'raw.docx'
$final = Join-Path $outDir 'final.docx'
$pdfTmp = Join-Path $outDir 'final.pdf'

Push-Location $sourceDir
try {
    pandoc '系统设计说明书.md' -f markdown+smart -t docx `
        --reference-doc $ref `
        --resource-path '.' --resource-path '..' `
        -o $raw
    if ($LASTEXITCODE -ne 0) { throw 'pandoc 转换失败' }
}
finally {
    Pop-Location
}

python (Join-Path $here 'postprocess.py') $raw $final
if ($LASTEXITCODE -ne 0) { throw 'postprocess.py 执行失败' }

# 在独立进程中调用 Word，并设置超时保护，避免 Word 弹窗导致构建卡死
$exportScript = Join-Path $here 'export_pdf.ps1'
$before = @(Get-Process WINWORD -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })
$argList = @(
    '-NoProfile', '-STA', '-ExecutionPolicy', 'Bypass',
    '-File', "`"$exportScript`"",
    '-Docx', "`"$final`"",
    '-Pdf', "`"$pdfTmp`""
)
$proc = Start-Process -FilePath 'powershell.exe' -ArgumentList $argList -PassThru -WindowStyle Hidden
if (-not $proc.WaitForExit(180000)) {
    $proc.Kill()
    Get-Process WINWORD -ErrorAction SilentlyContinue |
        Where-Object { $before -notcontains $_.Id } |
        Stop-Process -Force
    throw 'Word 导出超时（180 秒），已终止本次 Word 进程'
}
if ($proc.ExitCode -ne 0) { throw "Word 导出失败，退出码 $($proc.ExitCode)" }

$pdfOut = Join-Path $designDir 'CodeMind-FZU_系统设计说明书.pdf'
$docxOut = Join-Path $sourceDir 'CodeMind-FZU_系统设计说明书.docx'
Copy-Item $pdfTmp $pdfOut -Force
Copy-Item $final $docxOut -Force

Write-Host "PDF : $pdfOut"
Write-Host "DOCX: $docxOut"
