# Create a local shortcut for Voice Access; does not install a startup task.
$ErrorActionPreference = "Stop"
$projectDir = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectDir ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $pythonPath)) {
    throw "Run uv sync --locked in the project first."
}
$outputDir = Join-Path $projectDir "data\voice"
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
$shell = New-Object -ComObject WScript.Shell
foreach ($command in @("activate", "stop")) {
    $name = if ($command -eq "activate") { "Radio take my request.lnk" } else { "Radio stop playback.lnk" }
    $shortcutPath = Join-Path $outputDir $name
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $pythonPath
    $shortcut.Arguments = '-m app.desktop ' + $command
    $shortcut.WorkingDirectory = $projectDir
    $shortcut.WindowStyle = 7
    $shortcut.Save()
    Write-Output $shortcutPath
}
