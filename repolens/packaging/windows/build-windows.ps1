param(
    [string]$Version = "0.1.0",
    [string]$Python = "python",
    [string]$Iscc = ""
)

$ErrorActionPreference = "Stop"
$ProjectDir = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Push-Location $ProjectDir
try {
    $PythonBase = (& $Python -c "import sys; print(sys.base_prefix)").Trim()
    if ($LASTEXITCODE -ne 0 -or -not $PythonBase) {
        throw "Unable to determine the Python runtime directory."
    }

    $nuitkaArgs = @(
        "-m", "nuitka",
        "--assume-yes-for-downloads",
        "--onefile",
        "--follow-imports",
        "--remove-output",
        "--include-data-dir=$ProjectDir\templates=templates",
        "--output-dir=$ProjectDir\dist",
        "--output-filename=RepoLens.exe"
    )

    # Conda keeps ctypes' native libffi dependency under Library\bin, where
    # Nuitka does not always discover it for one-file builds.
    $ffiDll = Join-Path $PythonBase "Library\bin\ffi-8.dll"
    if (Test-Path -LiteralPath $ffiDll) {
        $nuitkaArgs += "--include-data-files=$ffiDll=ffi-8.dll"
    }

    $nuitkaArgs += "$ProjectDir\src\repolens\__main__.py"
    & $Python @nuitkaArgs
    if ($LASTEXITCODE -ne 0) { throw "Nuitka build failed." }

    if (-not $Iscc) {
        $candidates = @(
            "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
            "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
            "$env:LocalAppData\Programs\Inno Setup 6\ISCC.exe"
        )
        $Iscc = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    }
    if (-not $Iscc) {
        throw "ISCC.exe was not found. Install Inno Setup 6 or pass -Iscc."
    }

    & $Iscc "/DAppVersion=$Version" `
        "/DSourceExe=$ProjectDir\dist\RepoLens.exe" `
        "$ProjectDir\packaging\windows\RepoLens.iss"
    if ($LASTEXITCODE -ne 0) { throw "Installer build failed." }

    Get-FileHash "$ProjectDir\dist\RepoLens.exe" -Algorithm SHA256
    Get-FileHash "$ProjectDir\dist\RepoLens-$Version-Setup-x64.exe" -Algorithm SHA256
}
finally {
    Pop-Location
}
