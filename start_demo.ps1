#requires -Version 5.1
# CodeMind-FZU Alpha Demo Launcher (Windows)
# Keep this file and start_demo.bat in the repository root.
# Mode 1: real Qwen API + synthetic example.invalid fixture (technical demo only).
# Mode 2: Mock Agent (no API key and no model usage).

$ErrorActionPreference = 'Stop'
try {
    [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
    $OutputEncoding = [Console]::OutputEncoding
} catch { }

$ProjectRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
$BackendDir = Join-Path $ProjectRoot 'backend'
$FrontendDir = Join-Path $ProjectRoot 'frontend'
$VenvDir = Join-Path $ProjectRoot '.venv'
$PythonExe = Join-Path $VenvDir 'Scripts\python.exe'
$BackendRequirements = Join-Path $BackendDir 'requirements.txt'
$EnvExample = Join-Path $BackendDir '.env.example'
$EnvFile = Join-Path $BackendDir '.env'
$PackageJson = Join-Path $FrontendDir 'package.json'
$PackageLock = Join-Path $FrontendDir 'package-lock.json'
$NodeModules = Join-Path $FrontendDir 'node_modules'
$FixtureDir = Join-Path $ProjectRoot 'tests\fixtures\alpha_approved'

function Write-Section {
    param([string]$Message)
    Write-Host ''
    Write-Host ('--- ' + $Message + ' ---') -ForegroundColor Cyan
}

function Pause-And-Exit {
    param([int]$Code = 1)
    Write-Host ''
    Read-Host '按 Enter 关闭窗口'
    exit $Code
}

function Assert-LastExitCode {
    param([string]$Action)
    if ($LASTEXITCODE -ne 0) {
        throw "$Action 失败，退出代码：$LASTEXITCODE"
    }
}

function Get-PythonVersion {
    param(
        [string]$Executable,
        [string[]]$Prefix = @()
    )

    # Do not use `python -c` here. Windows PowerShell 5.1 can strip or
    # reinterpret nested quotes when constructing native-process arguments.
    # `--version` has no embedded quoting and is reliable across PS 5.1/7.
    try {
        $versionOutput = (& $Executable @Prefix --version 2>&1 | Out-String).Trim()
        $commandExitCode = $LASTEXITCODE
        if ($commandExitCode -ne 0) { return $null }
        if ($versionOutput -match '(?i)Python\s+(\d+\.\d+\.\d+)') {
            return [version]$Matches[1]
        }
    } catch { }
    return $null
}

function Get-PythonCandidate {
    $launcher = Get-Command 'py.exe' -ErrorAction SilentlyContinue
    if ($null -ne $launcher) {
        foreach ($versionArg in @('-3.10', '-3.11', '-3.12', '-3.13', '-3.14', '-3')) {
            $version = Get-PythonVersion -Executable $launcher.Source -Prefix @($versionArg)
            if ($null -ne $version -and $version -ge [version]'3.10') {
                return [pscustomobject]@{ Path = $launcher.Source; Prefix = @($versionArg); Version = $version }
            }
        }
    }

    $python = Get-Command 'python.exe' -ErrorAction SilentlyContinue
    if ($null -ne $python) {
        $version = Get-PythonVersion -Executable $python.Source
        if ($null -ne $version -and $version -ge [version]'3.10') {
            return [pscustomobject]@{ Path = $python.Source; Prefix = @(); Version = $version }
        }
    }
    return $null
}

function Test-TcpPort {
    param([int]$Port)
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $async = $client.BeginConnect('127.0.0.1', $Port, $null, $null)
        if (-not $async.AsyncWaitHandle.WaitOne(400)) { return $false }
        $client.EndConnect($async)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Test-HttpReady {
    param([string]$Url)
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
        return ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400)
    } catch {
        return $false
    }
}

function Test-QwenApiKey {
    if (-not (Test-Path -LiteralPath $EnvFile -PathType Leaf)) { return $false }
    $matches = Select-String -LiteralPath $EnvFile -Pattern '^\s*QWEN_API_KEY\s*=' -ErrorAction SilentlyContinue
    if ($null -eq $matches) { return $false }
    $line = $matches | Select-Object -Last 1
    $value = ($line.Line -replace '^\s*QWEN_API_KEY\s*=', '').Trim()
    $value = $value.Trim([char[]]@([char]34, [char]39))
    if ([string]::IsNullOrWhiteSpace($value)) { return $false }
    if ($value -match '(?i)your[_ -]?api[_ -]?key|replace[_ -]?me|填入|这里填写|changeme') { return $false }
    return $true
}

function Test-RequiredProjectFiles {
    $requiredFiles = @(
        (Join-Path $ProjectRoot 'backend\app\alpha.py'),
        (Join-Path $ProjectRoot 'backend\app\dev.py'),
        $BackendRequirements,
        $EnvExample,
        $PackageJson,
        $PackageLock,
        (Join-Path $FixtureDir 'README.md'),
        (Join-Path $FixtureDir 'scholarship.json'),
        (Join-Path $FixtureDir 'policy.md')
    )
    $missing = @($requiredFiles | Where-Object { -not (Test-Path -LiteralPath $_) })
    if ($missing.Count -gt 0) {
        Write-Host '项目文件不完整，缺少以下文件：' -ForegroundColor Red
        foreach ($item in $missing) { Write-Host "  - $item" -ForegroundColor Red }
        throw '请先从 GitHub 完整克隆或更新 CodeMind-FZU 仓库，再运行启动脚本。'
    }
}

try {
    Write-Host ''
    Write-Host '============================================================' -ForegroundColor Cyan
    Write-Host '             CodeMind-FZU Alpha Demo Launcher' -ForegroundColor Cyan
    Write-Host '============================================================' -ForegroundColor Cyan
    Write-Host "项目目录：$ProjectRoot"
    Write-Host '脚本将自动检查环境，并在缺少依赖时安装。'

    Write-Section '1/6 项目文件检查'
    Test-RequiredProjectFiles
    Write-Host '[OK] 项目结构完整。' -ForegroundColor Green

    Write-Section '2/6 Python 环境检查'
    if (Test-Path -LiteralPath $PythonExe -PathType Leaf) {
        $pythonVersion = Get-PythonVersion -Executable $PythonExe
        if ($null -eq $pythonVersion) {
            throw '现有 .venv 无法正常运行或无法识别 Python 版本。请删除项目根目录的 .venv 文件夹后重新启动脚本。'
        }
    } else {
        $candidate = Get-PythonCandidate
        if ($null -eq $candidate) {
            throw '未找到 Python 3.10 或更高版本。请安装 Python 3.10+，并勾选 Add Python to PATH，或安装 Python Launcher。'
        }
        Write-Host "检测到 Python $($candidate.Version)，正在创建项目虚拟环境..." -ForegroundColor Yellow
        $venvArgs = @($candidate.Prefix) + @('-m', 'venv', $VenvDir)
        & $candidate.Path @venvArgs
        Assert-LastExitCode '创建 Python 虚拟环境'
        if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
            throw '虚拟环境创建后未找到 .venv\Scripts\python.exe。'
        }
        $pythonVersion = $candidate.Version
    }

    if ($pythonVersion -lt [version]'3.10') {
        throw "当前项目虚拟环境 Python $pythonVersion 过旧，要求 Python 3.10 或更高版本。请删除 .venv 后重试。"
    }
    Write-Host "[OK] Python $pythonVersion" -ForegroundColor Green

    $requirementsHash = (Get-FileHash -LiteralPath $BackendRequirements -Algorithm SHA256).Hash
    $requirementsMarker = Join-Path $VenvDir '.codemind-backend-requirements.sha256'

    # Avoid `python -c` entirely. Windows PowerShell 5.1 may pass its quoted
    # code argument differently to native executables, producing:
    #   File "<string>", line 1
    # Check each required package with `pip show` instead; this uses ordinary
    # command-line arguments and works in both Windows PowerShell 5.1 and PS 7.
    $pythonPackagesOk = $true
    foreach ($packageName in @('fastapi', 'httpx', 'pydantic', 'uvicorn')) {
        & $PythonExe -m pip show $packageName 2>$null | Out-Null
        if ($LASTEXITCODE -ne 0) {
            $pythonPackagesOk = $false
            break
        }
    }

    $savedRequirementsHash = ''
    if (Test-Path -LiteralPath $requirementsMarker) {
        $savedRequirementsHash = (Get-Content -LiteralPath $requirementsMarker -Raw).Trim()
    }
    if (-not $pythonPackagesOk -or $savedRequirementsHash -ne $requirementsHash) {
        # A freshly-created venv normally includes pip. If it does not, try
        # ensurepip before installing the project's pinned requirements.
        & $PythonExe -m pip --version 2>$null | Out-Null
        if ($LASTEXITCODE -ne 0) {
            & $PythonExe -m ensurepip --upgrade
            Assert-LastExitCode '初始化 pip'
        }
        Write-Host '正在安装/更新后端依赖（backend/requirements.txt）...' -ForegroundColor Yellow
        & $PythonExe -m pip install -r $BackendRequirements
        Assert-LastExitCode '安装后端 Python 依赖'
        Set-Content -LiteralPath $requirementsMarker -Value $requirementsHash -Encoding ASCII
    } else {
        Write-Host '[OK] 后端依赖已就绪。' -ForegroundColor Green
    }

    Write-Section '3/6 Node.js 与前端依赖检查'
    $nodeCommand = Get-Command 'node.exe' -ErrorAction SilentlyContinue
    $npmCommand = Get-Command 'npm.cmd' -ErrorAction SilentlyContinue
    if ($null -eq $nodeCommand -or $null -eq $npmCommand) {
        throw '未找到 Node.js 或 npm。请安装 Node.js 18.18 或更高版本（建议 20/22 LTS），安装后重新打开终端再运行。'
    }
    $nodeVersionText = (& $nodeCommand.Source --version | Out-String).Trim()
    if ($nodeVersionText -notmatch '^v?(\d+\.\d+\.\d+)') {
        throw "无法识别 Node.js 版本：$nodeVersionText"
    }
    $nodeVersion = [version]$Matches[1]
    if ($nodeVersion -lt [version]'18.18') {
        throw "Node.js $nodeVersion 过旧，项目要求 18.18 或更高版本。"
    }
    Write-Host "[OK] Node.js $nodeVersion" -ForegroundColor Green

    $lockHash = (Get-FileHash -LiteralPath $PackageLock -Algorithm SHA256).Hash
    $frontendMarker = Join-Path $NodeModules '.codemind-package-lock.sha256'
    $savedLockHash = ''
    if (Test-Path -LiteralPath $frontendMarker) {
        $savedLockHash = (Get-Content -LiteralPath $frontendMarker -Raw).Trim()
    }
    $viteCmd = Join-Path $NodeModules '.bin\vite.cmd'
    if (-not (Test-Path -LiteralPath $viteCmd) -or $savedLockHash -ne $lockHash) {
        Write-Host '正在执行 npm ci 安装/同步前端依赖...' -ForegroundColor Yellow
        Push-Location $FrontendDir
        try {
            & $npmCommand.Source 'ci'
            Assert-LastExitCode '安装前端依赖（npm ci）'
        } finally {
            Pop-Location
        }
        if (-not (Test-Path -LiteralPath $viteCmd)) {
            throw 'npm ci 已结束，但没有找到 Vite 启动程序 frontend\node_modules\.bin\vite.cmd。'
        }
        Set-Content -LiteralPath $frontendMarker -Value $lockHash -Encoding ASCII
    } else {
        Write-Host '[OK] 前端依赖与 package-lock.json 一致。' -ForegroundColor Green
    }

    Write-Section '4/6 环境变量与演示模式'
    if (-not (Test-Path -LiteralPath $EnvFile -PathType Leaf)) {
        Copy-Item -LiteralPath $EnvExample -Destination $EnvFile
        Write-Host '已从 backend\.env.example 创建 backend\.env。' -ForegroundColor Green
    } else {
        Write-Host '[OK] 已找到 backend\.env。' -ForegroundColor Green
    }

    $hasApiKey = Test-QwenApiKey
    if ($hasApiKey) {
        Write-Host '检测到 QWEN_API_KEY 已配置（不会显示密钥内容）。' -ForegroundColor Green
    } else {
        Write-Host '未检测到有效的 QWEN_API_KEY。真实 Qwen 模式暂不可用。' -ForegroundColor Yellow
    }

    Write-Host ''
    Write-Host '请选择本次演示模式：' -ForegroundColor Cyan
    Write-Host '  1. 真实 Qwen API + 合成测试资料（会调用模型，可能消耗 API 额度）'
    Write-Host '  2. Mock Agent（不调用模型，不需要 API Key）'
    $modeChoice = (Read-Host '输入 1 或 2，直接回车默认选择 2').Trim()
    if ([string]::IsNullOrWhiteSpace($modeChoice)) { $modeChoice = '2' }
    if ($modeChoice -notin @('1', '2')) { throw '无效选择，请输入 1 或 2。' }

    if ($modeChoice -eq '1') {
        if (-not $hasApiKey) {
            throw '真实 Qwen 模式需要 API Key。请编辑 backend\.env，填写 QWEN_API_KEY 后重新运行。也可以选择 Mock Agent 模式启动。'
        }
        $DemoMode = 'real'
        Write-Host ''
        Write-Host '注意：本模式使用真实 Qwen API，但知识资料来自 tests/fixtures/alpha_approved 合成测试夹具。' -ForegroundColor Yellow
        Write-Host '资料来源为 example.invalid，不是福州大学正式政策，演示时必须明确说明。' -ForegroundColor Yellow
        Write-Host '提交问题会产生真实模型请求，可能消耗 API 额度。' -ForegroundColor Yellow
    } else {
        $DemoMode = 'mock'
        Write-Host '[OK] 已选择 Mock Agent，不会调用 Qwen API。' -ForegroundColor Green
    }

    Write-Section '5/6 端口检查'
    $busyPorts = @()
    foreach ($port in @(8000, 5173)) {
        if (Test-TcpPort -Port $port) { $busyPorts += $port }
    }
    if ($busyPorts.Count -gt 0) {
        throw "端口 $($busyPorts -join ', ') 已被占用。请先关闭旧的 CodeMind-FZU 后端/前端终端（Ctrl+C），再重新运行。"
    }
    Write-Host '[OK] 8000 和 5173 端口均可用。' -ForegroundColor Green

    Write-Section '6/6 启动前后端'
    $rootLiteral = $ProjectRoot.Replace("'", "''")
    $pythonLiteral = $PythonExe.Replace("'", "''")
    $npmLiteral = $npmCommand.Source.Replace("'", "''")
    $frontendLiteral = $FrontendDir.Replace("'", "''")

    if ($DemoMode -eq 'real') {
        $backendCommand = @"
`$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath '$rootLiteral'
`$env:PYTHONUTF8 = '1'
`$env:ALPHA_PACKAGE_DIR = 'tests/fixtures/alpha_approved'
Write-Host 'CodeMind-FZU Backend | REAL QWEN + SYNTHETIC FIXTURE' -ForegroundColor Cyan
Write-Host '资料为 example.invalid 合成测试数据，不是正式校园政策。' -ForegroundColor Yellow
& '$pythonLiteral' -m uvicorn backend.app.alpha:app --host 127.0.0.1 --port 8000 --env-file backend/.env
if (`$LASTEXITCODE -ne 0) { Write-Host "后端进程退出，代码：`$LASTEXITCODE" -ForegroundColor Red }
Write-Host '后端终端仍保持打开，可查看上方日志。' -ForegroundColor Yellow
"@
    } else {
        $backendCommand = @"
`$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath '$rootLiteral'
`$env:PYTHONUTF8 = '1'
Write-Host 'CodeMind-FZU Backend | MOCK AGENT' -ForegroundColor Cyan
& '$pythonLiteral' -m uvicorn backend.app.dev:app --host 127.0.0.1 --port 8000
if (`$LASTEXITCODE -ne 0) { Write-Host "后端进程退出，代码：`$LASTEXITCODE" -ForegroundColor Red }
Write-Host '后端终端仍保持打开，可查看上方日志。' -ForegroundColor Yellow
"@
    }

    $frontendCommand = @"
`$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath '$frontendLiteral'
Write-Host 'CodeMind-FZU Student Web | http://127.0.0.1:5173/' -ForegroundColor Cyan
& '$npmLiteral' run dev -- --host 127.0.0.1
if (`$LASTEXITCODE -ne 0) { Write-Host "前端进程退出，代码：`$LASTEXITCODE" -ForegroundColor Red }
Write-Host '前端终端仍保持打开，可查看上方日志。' -ForegroundColor Yellow
"@

    $backendEncoded = [Convert]::ToBase64String([System.Text.Encoding]::Unicode.GetBytes($backendCommand))
    $frontendEncoded = [Convert]::ToBase64String([System.Text.Encoding]::Unicode.GetBytes($frontendCommand))
    $powershellExe = (Get-Command 'powershell.exe' -ErrorAction SilentlyContinue).Source
    if ([string]::IsNullOrWhiteSpace($powershellExe)) { throw '找不到 powershell.exe，无法创建独立服务终端。' }

    Write-Host '正在打开后端终端...' -ForegroundColor Yellow
    $backendProcess = Start-Process -FilePath $powershellExe -WorkingDirectory $ProjectRoot -ArgumentList @('-NoLogo', '-NoExit', '-EncodedCommand', $backendEncoded) -PassThru
    Start-Sleep -Milliseconds 500
    Write-Host '正在打开前端终端...' -ForegroundColor Yellow
    $frontendProcess = Start-Process -FilePath $powershellExe -WorkingDirectory $FrontendDir -ArgumentList @('-NoLogo', '-NoExit', '-EncodedCommand', $frontendEncoded) -PassThru

    Write-Host '等待后端健康检查与前端 HTTP 服务就绪（最多 60 秒）...' -ForegroundColor Yellow
    $backendReady = $false
    $frontendReady = $false
    for ($i = 0; $i -lt 60; $i++) {
        if (-not $backendReady) { $backendReady = Test-HttpReady 'http://127.0.0.1:8000/api/v1/health' }
        if (-not $frontendReady) { $frontendReady = Test-HttpReady 'http://127.0.0.1:5173/' }
        if ($backendReady -and $frontendReady) { break }
        Start-Sleep -Seconds 1
    }

    Write-Host ''
    Write-Host '==================== 启动结果 ====================' -ForegroundColor Cyan
    if ($backendReady) {
        Write-Host '[OK] 后端健康检查通过：http://127.0.0.1:8000/api/v1/health' -ForegroundColor Green
    } else {
        Write-Host '[FAIL] 后端未通过健康检查，请查看后端终端日志。' -ForegroundColor Red
    }
    if ($frontendReady) {
        Write-Host '[OK] 前端已就绪：http://127.0.0.1:5173/' -ForegroundColor Green
    } else {
        Write-Host '[FAIL] 前端未就绪，请查看前端终端日志。' -ForegroundColor Red
    }

    Write-Host ''
    Write-Host '学生端：http://127.0.0.1:5173/'
    Write-Host '管理端：http://127.0.0.1:5173/admin/index.html'
    Write-Host '后端 Swagger：http://127.0.0.1:8000/docs'
    Write-Host '后端健康检查：http://127.0.0.1:8000/api/v1/health'
    Write-Host ''
    Write-Host '结束演示：分别在后端和前端终端按 Ctrl+C。' -ForegroundColor Yellow

    if ($backendReady -and $frontendReady) {
        Start-Process 'http://127.0.0.1:5173/'
        Write-Host '浏览器已打开学生端。' -ForegroundColor Green
    } else {
        Write-Host '由于至少一个服务未就绪，未自动打开浏览器。' -ForegroundColor Yellow
        Write-Host '请先查看对应终端中的报错；修复后可重新运行本脚本。' -ForegroundColor Yellow
    }

    if ($DemoMode -eq 'real') {
        Write-Host ''
        Write-Host '演示声明：真实 Qwen API + example.invalid 合成测试资料；不得将其描述为正式校园政策问答。' -ForegroundColor Yellow
    }
    Write-Host ''
    Read-Host '按 Enter 关闭启动器窗口（不会关闭前后端服务终端）'
    exit 0
}
catch {
    Write-Host ''
    Write-Host '============================================================' -ForegroundColor Red
    Write-Host '启动失败' -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host '============================================================' -ForegroundColor Red
    Write-Host ''
    Write-Host '如果是依赖安装失败，请检查网络连接；如果是环境缺失，请按提示安装 Python 3.10+ 或 Node.js 18.18+。'
    Read-Host '按 Enter 关闭窗口'
    exit 1
}
