$ErrorActionPreference = "Stop"

if ($env:OS -ne "Windows_NT") {
    throw "请在 Windows 原生 PowerShell 中运行此脚本，不要在 WSL 或 Linux 上打 Windows 包。"
}
if ($env:WSL_DISTRO_NAME) {
    throw "检测到 WSL。请打开 Windows 终端（PowerShell 或 Windows Terminal），不要在 WSL 里打包。"
}

Set-Location (Split-Path -Parent $PSScriptRoot)
$root = (Get-Location).Path
$venvDir = Join-Path $root ".venv-desktop"
$venvPython = Join-Path $venvDir "Scripts\python.exe"
$spec = Join-Path $root "packaging\learning-loop.spec"
$reqs = Join-Path $root "requirements-desktop.txt"
$exe = Join-Path $root "dist\LearningLoop\LearningLoop.exe"

function Get-PackagingPython {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        foreach ($ver in @("3.12", "3.13", "3.11", "3.10")) {
            $exePath = & py "-$ver" -c "import sys; print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $exePath) {
                Write-Host "Using Python $ver at $($exePath.Trim())"
                return $exePath.Trim()
            }
        }
    }
    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) {
        throw "找不到 Python。请安装 Python 3.12 或 3.13（https://www.python.org/downloads/），安装时勾选 Add python.exe to PATH。"
    }
    $verText = & python -c "import sys; print('%d.%d' % (sys.version_info.major, sys.version_info.minor))"
    $parts = $verText.Trim() -split "\."
    $major = [int]$parts[0]
    $minor = [int]$parts[1]
    if ($major -ne 3 -or $minor -lt 10) {
        throw "当前 python 是 $verText，本项目需要 3.10+（建议 3.12 或 3.13）。不要用 3.9 打包。"
    }
    Write-Host "Using python $verText"
    return $python.Source
}

$packPython = Get-PackagingPython

$venvOk = $false
if (Test-Path $venvPython) {
    $venvVer = & $venvPython -c "import sys; print('%d.%d' % (sys.version_info.major, sys.version_info.minor))" 2>$null
    if ($venvVer -match '^3\.(10|11|12|13)$') {
        $venvOk = $true
    } else {
        Write-Host "Existing .venv-desktop is Python $venvVer, recreating with 3.10+"
        Remove-Item -Recurse -Force $venvDir
    }
}
if (-not $venvOk) {
    Write-Host "Creating .venv-desktop"
    & $packPython -m venv $venvDir
}

Write-Host "Installing packaging dependencies"
& $venvPython -m pip install -U pip
& $venvPython -m pip install -r $reqs

Write-Host "Running PyInstaller"
& $venvPython -m PyInstaller $spec --noconfirm --clean

if (-not (Test-Path $exe)) {
    throw "打包结束但没有生成 $exe"
}

Write-Host "OK: $exe"
Write-Host "请双击该 exe，确认窗口能打开后再分发整个 dist\LearningLoop 文件夹。"
Write-Host "数据目录: $env:LOCALAPPDATA\LearningLoop"
