# PostToolUse hook (Windows): auto-format + auto-fix the .py file Claude just
# wrote/edited. Reads the hook payload from stdin; no-ops when the file isn't
# under this repo or ruff isn't available. Config: pyproject.toml.
$ErrorActionPreference = 'Stop'
$raw = [Console]::In.ReadToEnd()
if (-not $raw) { exit 0 }
try { $payload = $raw | ConvertFrom-Json } catch { exit 0 }
$f = $payload.tool_input.file_path
if (-not $f) { exit 0 }
if (-not $f.EndsWith('.py')) { exit 0 }
if (-not (Test-Path -LiteralPath $f)) { exit 0 }
$repoRoot = Split-Path -Parent $PSScriptRoot   # .claude/
$repoRoot = Split-Path -Parent $repoRoot       # repo root
if (-not ($f.StartsWith($repoRoot, [System.StringComparison]::OrdinalIgnoreCase))) { exit 0 }
$ruff = Join-Path $repoRoot '.venv\Scripts\ruff.exe'
if (-not (Test-Path $ruff)) {
    $onPath = Get-Command ruff -ErrorAction SilentlyContinue
    if (-not $onPath) { exit 0 }               # ruff not installed -> quiet no-op
    $ruff = $onPath.Source
}
& $ruff format -- $f
$fmtExit = $LASTEXITCODE
$out = & $ruff check --fix -- $f 2>&1
$chkExit = $LASTEXITCODE
if (($fmtExit -ne 0) -or ($chkExit -ne 0)) {
    [Console]::Error.WriteLine(($out -join [System.Environment]::NewLine))
    exit 2   # remaining findings: sent back to the model to fix
}
exit 0
