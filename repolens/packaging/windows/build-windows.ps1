param(
    [string]$Version = "0.1.0",
    [string]$Python = "python",
    [string]$Iscc = ""
)

$ErrorActionPreference = "Stop"
$ProjectDir = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Push-Location $ProjectDir
try {
    & $Python -m nuitka `
        --assume-yes-for-downloads `
        --onefile `
        --follow-imports `
        "--include-data-dir=$ProjectDir\templates=templates" `
        "--output-dir=$ProjectDir\dist" `
        --output-filename=RepoLens.exe `
        "$ProjectDir\src\repolens\__main__.py"
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
