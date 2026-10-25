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
$shortcutNames = @{
    start = "Radio start playback.lnk"
    activate = "Radio take my request.lnk"
    stop = "Radio stop playback.lnk"
}
foreach ($command in @("start", "activate", "stop")) {
    $name = $shortcutNames[$command]
    $shortcutPath = Join-Path $outputDir $name
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $pythonPath
    $shortcut.Arguments = '-m app.desktop ' + $command
    $shortcut.WorkingDirectory = $projectDir
    $shortcut.WindowStyle = 7
    $shortcut.Save()
    Write-Output $shortcutPath
}
