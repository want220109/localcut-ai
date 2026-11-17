# Verify subprocess failures and report writing without running any installer.
$ErrorActionPreference = 'Stop'
$source = Join-Path $PSScriptRoot 'windows-local-test.ps1'
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($source, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count) { throw ($parseErrors | Out-String) }
$definitions = $ast.FindAll({ param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $false)
foreach ($definition in $definitions) { . ([scriptblock]::Create($definition.Extent.Text)) }
$results = Join-Path ([IO.Path]::GetTempPath()) ('localcut-launcher-test-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $results | Out-Null
$summary = [ordered]@{ status = 'NOT_STARTED'; steps = @(); installer = $null; installedApp = $null }
$executable = (Get-Process -Id $PID).Path
try {
    $project = Join-Path $results ('manifest-' + [char]0xD55C + [char]0xAE00)
    New-Item -ItemType Directory -Path $project | Out-Null
    # Real non-BOM UTF-8 bytes, not JSON unicode escapes. Also safe to parse as a
    # PowerShell 5.1 script on machines whose system code page is Korean (949).
    $korean = ([string][char]0xB85C) + [char]0xCEEC + ' ' + [char]0xD3B8 + [char]0xC9D1 + [char]0xAE30
    $manifest = '{"version":"0.1.0","description":"' + $korean + '"}'
    [IO.File]::WriteAllText((Join-Path $project 'package.json'), $manifest, (New-Object System.Text.UTF8Encoding($false)))
    if ((Get-ProjectVersion $project) -ne '0.1.0') { throw 'Non-BOM UTF-8 Korean manifest could not be read' }
    New-Item -ItemType Directory -Path (Join-Path $project 'release') | Out-Null
    $fixtureInstaller = Join-Path $project 'release\LocalCut-AI-0.1.0-x64-Setup.exe'
    [IO.File]::WriteAllText($fixtureInstaller, 'fixture only - never executed')
    if ((Get-BuiltInstaller $project) -ne $fixtureInstaller) { throw 'Resume did not find the existing installer' }
    Remove-Item -LiteralPath $fixtureInstaller
    $noInstaller = $false
    try { Get-BuiltInstaller $project | Out-Null } catch { $noInstaller = $_.Exception.Message -like '*installer not found*' }
    if (-not $noInstaller) { throw 'Resume must fail before installation when the existing installer is absent' }
    Invoke-Step 'pass-fixture' $executable @('-NoLogo','-NoProfile','-Command','exit 0')
    if ($summary.steps.Count -ne 1 -or $summary.steps[0].exitCode -ne 0) { throw 'Passing subprocess was not recorded correctly' }
    $failed = $false
    try { Invoke-Step 'fail-fixture' $executable @('-NoLogo','-NoProfile','-Command','exit 7') }
    catch { $failed = $_.Exception.Message -like '*exit 7*' }
    if (-not $failed -or $summary.steps[1].exitCode -ne 7) { throw 'Nonzero subprocess exit must stop the test and remain in the report' }
    $missing = $false
    try { Invoke-Step 'missing-fixture' (Join-Path $results 'does-not-exist.exe') @() }
    catch { $missing = $_.Exception.Message -like '*not found*' }
    if (-not $missing) { throw 'Missing executable was treated as success' }
    Save-Result 'FAILED' 'Expected test fixture failure'
    $report = Get-Content -LiteralPath (Join-Path $results 'result.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($report.status -ne 'FAILED' -or $report.steps.Count -ne 2) { throw 'Failure report did not preserve subprocess results' }
    if (-not (Test-Path -LiteralPath (Join-Path $results 'RESULT.txt'))) { throw 'Readable result summary was not created' }
    Write-Host 'PASS: UTF-8 Korean manifest, existing installer resume, syntax, native exit codes, missing executable and failure report' -ForegroundColor Green
} finally {
    Remove-Item -LiteralPath $results -Recurse -Force
}
