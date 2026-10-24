# Create a local shortcut for Voice Access; does not install a startup task.
$ErrorActionPreference = "Stop"
$projectDir = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectDir ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $pythonPath)) {
    throw "Run uv sync --locked in the project first."
}
$outputDir = Join-Path $projectDir "data\voice"
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
$shortcutPath = Join-Path $outputDir "Radio.lnk"
$outputPath = Join-Path $outputDir "latest.txt"
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $pythonPath
$shortcut.Arguments = '-m app.voice --output "' + $outputPath + '"'
$shortcut.WorkingDirectory = $projectDir
$shortcut.WindowStyle = 7
$shortcut.Save()
Write-Output $shortcutPath
