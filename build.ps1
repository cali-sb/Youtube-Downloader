# Compila la app (PyInstaller) y el instalador (Inno Setup) con la versión de src\version.py.
# Uso: .\build.ps1   ->  installer_output\YouTubeDownloader-Setup-vX.Y.Z.exe
# Sin $ErrorActionPreference = "Stop": en Windows PowerShell 5.1 convierte en error lo que
# PyInstaller escribe por stderr (sus mensajes INFO). Los fallos se miran con $LASTEXITCODE.
Set-Location $PSScriptRoot

$match = Select-String -Path "src\version.py" -Pattern '__version__\s*=\s*"([^"]+)"'
if (-not $match) { throw "No encuentro __version__ en src\version.py" }
$version = $match.Matches[0].Groups[1].Value
Write-Host "Versión $version"

$iscc = @(
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "No encuentro ISCC.exe (Inno Setup 6)" }

# Python y FFmpeg viajan dentro del instalador: no publicar con versiones sin parches.
$pyVersion = [version](& .\venv\Scripts\python.exe -c "import platform; print(platform.python_version())")
if ($pyVersion -lt [version]"3.13.17") { throw "Python $pyVersion sin parches: hace falta 3.13.17 o posterior." }
$ffmpegLine = (& "C:\ffmpeg\bin\ffmpeg.exe" -hide_banner -version | Select-Object -First 1)
if ($ffmpegLine -notmatch '^ffmpeg version n(\d+\.\d+(\.\d+)?)' -or [version]($Matches[1] + $(if ($Matches[2]) { '' } else { '.0' })) -lt [version]"8.1.2") {
    throw "FFmpeg sin parches o de rama master ($ffmpegLine): hace falta n8.1.2 o posterior."
}

& .\venv\Scripts\python.exe -m PyInstaller --noconfirm --clean YouTubeDownloader.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller ha fallado" }

# Comprueba el paquete real antes de generar el instalador.
$qtExe = Join-Path $PSScriptRoot 'dist\YouTubeDownloader\YouTubeDownloader.exe'
$qtSmoke = Start-Process -FilePath $qtExe -ArgumentList '--smoke-test' -PassThru -WindowStyle Hidden
if (-not $qtSmoke.WaitForExit(30000)) {
    Stop-Process -Id $qtSmoke.Id
    throw 'La comprobación de arranque no terminó.'
}
$qtSmoke.Refresh()
if ($qtSmoke.ExitCode -ne 0) { throw "La app no arranca (código $($qtSmoke.ExitCode))." }

# Aparta el antiguo paquete onefile: no debe confundirse con el paquete Qt actual.
$qtOldExe = Join-Path $PSScriptRoot 'dist\YouTubeDownloader.exe'
if (Test-Path -LiteralPath $qtOldExe) {
    Move-Item -LiteralPath $qtOldExe -Destination (Join-Path $PSScriptRoot "build\obsolete-single-file-$([guid]::NewGuid()).exe.disabled")
}
$qtShell = New-Object -ComObject WScript.Shell
$qtShortcut = $qtShell.CreateShortcut((Join-Path $PSScriptRoot 'dist\YouTubeDownloader.lnk'))
$qtShortcut.TargetPath = $qtExe
$qtShortcut.WorkingDirectory = Split-Path -Parent $qtExe
$qtShortcut.Description = 'YouTube Downloader — Qt Quick'
$qtShortcut.Save()

& $iscc "/DMyAppVersion=$version" installer.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup ha fallado" }

$setup = "installer_output\YouTubeDownloader-Setup-v$version.exe"
Write-Host "Instalador: $setup"
Write-Host "SHA-256:    $((Get-FileHash $setup -Algorithm SHA256).Hash.ToLower())"
