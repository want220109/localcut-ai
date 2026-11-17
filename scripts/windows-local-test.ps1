[CmdletBinding()]
param(
    [switch]$CheckOnly,
    [switch]$ResumeInstall,
    [switch]$UpdateExisting,
    [switch]$NoLaunch
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$root = Split-Path -Parent $PSScriptRoot
$results = Join-Path $root 'windows-results'
$summary = [ordered]@{
    timestamp = (Get-Date -Format 'o')
    status = 'NOT_STARTED'
    mode = $(if ($ResumeInstall) { 'RESUME_INSTALL_ONLY' } elseif ($UpdateExisting) { 'UPDATE_EXISTING_BUILD' } else { 'FULL_BUILD_AND_TEST' })
    platform = [Environment]::OSVersion.VersionString
    steps = @()
    installer = $null
    installedApp = $null
    speechRecognition = 'NOT_RUN: download a model with consent and test a Korean video in the app'
    liveUpdate = 'NOT_RUN: release feed and two real versions are required'
}

function Save-Result([string]$Status, [string]$Message) {
    $summary.status = $Status
    $summary.message = $Message
    $summary | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $results 'result.json') -Encoding UTF8
    @(
        "LocalCut AI - Windows test result: $Status"
        $Message
        "Mode: $($summary.mode)"
        ''
        'Completed stages:'
        (($summary.steps | ForEach-Object { "  $($_.name): exit=$($_.exitCode)" }) -join "`r`n")
        ''
        "Installer: $($summary.installer)"
        "Installed app: $($summary.installedApp)"
        ''
        'Actual Korean speech recognition: NOT TESTED by the automatic suite.'
        'In the app, choose a model, consent to the download, then analyze a short Korean video.'
        'Live online update: NOT TESTED. No release was published.'
        'No videos or transcripts were uploaded. No paid API was used.'
        ''
        'For troubleshooting, paste the contents of this RESULT.txt into the chat.'
        'Detailed local logs are in this windows-results folder.'
    ) | Set-Content -LiteralPath (Join-Path $results 'RESULT.txt') -Encoding UTF8
}

function Invoke-Step([string]$Name, [string]$Executable, [string[]]$Arguments) {
    if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) { throw "Required executable not found: $Executable" }
    $index = $summary.steps.Count + 1
    Write-Host "`n[$index] $Name" -ForegroundColor Cyan
    $log = Join-Path $results ('{0:D2}-{1}.log' -f $index, ($Name -replace '[^a-zA-Z0-9-]', '-'))
    $savedPreference = $ErrorActionPreference
    try {
        # Windows PowerShell 5 represents native stderr as ErrorRecords. Preserve those
        # as log lines; only the process exit code determines whether a stage passed.
        $ErrorActionPreference = 'Continue'
        $global:LASTEXITCODE = 0
        & $Executable @Arguments 2>&1 |
            ForEach-Object { $_.ToString() } |
            Tee-Object -FilePath $log |
            ForEach-Object { Write-Host $_ }
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $savedPreference
    }
    $summary.steps += [ordered]@{ name = $Name; exitCode = $code; log = $log }
    if ($code -ne 0) { throw "$Name failed (exit $code). See $log" }
    Save-Result 'RUNNING' ("Completed: $Name. Remaining stages have not passed yet.")
}

function Find-Python312 {
    $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($launcher) {
        try {
            $candidate = & $launcher.Source -3.12 -c 'import sys; print(sys.executable)' 2>$null
            if ($LASTEXITCODE -eq 0 -and $candidate -and (Test-Path -LiteralPath $candidate)) { return [string]$candidate }
        } catch { }
    }
    $candidates = @((Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'))
    $command = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($command -and $command.Source -notlike '*\WindowsApps\*') { $candidates += $command.Source }
    foreach ($candidate in $candidates) {
        if (-not (Test-Path -LiteralPath $candidate)) { continue }
        try {
            & $candidate -c 'import sys; raise SystemExit(0 if sys.version_info[:2] == (3,12) else 1)' 2>$null
            if ($LASTEXITCODE -eq 0) { return $candidate }
        } catch { }
    }
    return $null
}

function Find-Node {
    $command = Get-Command node.exe -ErrorAction SilentlyContinue
    if (-not $command) { return $null }
    $version = & $command.Source -p 'process.versions.node'
    if ($LASTEXITCODE -ne 0 -or [version]$version -lt [version]'22.12.0') { return $null }
    return $command.Source
}

function Assert-AppClosed {
    if (Get-Process -Name 'LocalCut AI' -ErrorAction SilentlyContinue) {
        throw 'LocalCut AI is running. Finish your editing, close the app, then run this test again. The test will not force-close it.'
    }
}

function Get-ProjectVersion([string]$Directory) {
    # Windows PowerShell 5.1 defaults to the system ANSI code page. This manifest
    # contains Korean UTF-8 without a BOM, so the encoding must be explicit.
    $manifest = Get-Content -LiteralPath (Join-Path $Directory 'package.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $version = [string]$manifest.version
    if ($version -notmatch '^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$') { throw 'Invalid project version in package.json' }
    return $version
}

function Get-BuiltInstaller([string]$Directory) {
    $version = Get-ProjectVersion $Directory
    $installer = Join-Path $Directory "release\LocalCut-AI-$version-x64-Setup.exe"
    if (-not (Test-Path -LiteralPath $installer -PathType Leaf)) {
        throw 'Existing installer not found. Run START-WINDOWS-TEST.cmd for a full build, or place this fix inside the original LocalCut-AI folder.'
    }
    return $installer
}

try {
    if ($ResumeInstall -and $UpdateExisting) { throw 'Choose either resume installation or update existing sources, not both.' }
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT -or -not [Environment]::Is64BitOperatingSystem) {
        throw 'This launcher requires Windows 10/11 x64. Linux test results do not establish Windows compatibility.'
    }
    if ($root.StartsWith('\\')) { throw 'Extract the ZIP to a local drive, for example C:\LocalCut, before running the test.' }
    if (-not (Test-Path -LiteralPath (Join-Path $root 'package.json'))) { throw 'Extract the entire source ZIP first.' }
    New-Item -ItemType Directory -Force -Path $results | Out-Null
    Set-Location -LiteralPath $root
    $previousResult = Join-Path $results 'result.json'
    if (Test-Path -LiteralPath $previousResult) {
        Copy-Item -LiteralPath $previousResult -Destination (Join-Path $results ('result.previous.' + [guid]::NewGuid().ToString('N') + '.json'))
    }
    Save-Result 'RUNNING' 'Tests are in progress. No complete Windows result is available yet.'
    Assert-AppClosed
    if ($UpdateExisting) {
        foreach ($relative in @('.venv-win\Scripts\python.exe','node_modules\electron\install.js','vendor\media\ffmpeg.exe','vendor\media\ffprobe.exe')) {
            if (-not (Test-Path -LiteralPath (Join-Path $root $relative))) {
                throw 'Existing build tools were not found. Copy the update into the ORIGINAL LocalCut-AI folder, or use START-WINDOWS-TEST.cmd for a first-time build.'
            }
        }
        Write-Host 'Updating the app using existing local dependencies. Model and user jobs are preserved.' -ForegroundColor Green
    }
    if ($ResumeInstall) {
        $summary.installer = Get-BuiltInstaller $root
        Write-Host 'Continuing with the existing installer. Previous build stages will not be repeated.' -ForegroundColor Green
    }

    Write-Host 'LocalCut AI - FREE local Windows build and test' -ForegroundColor Green
    if ($ResumeInstall) {
        Write-Host 'Build stages are skipped. Installation and the installed-app test use your existing files.'
    } else {
        Write-Host 'Requires internet downloads and at least 6 GB of free disk space.'
    }
    Write-Host 'This does not publish releases or call paid APIs. Model download is a separate consent action in the app.'
    $python = Find-Python312
    $node = Find-Node
    if (-not $python -or -not $node) {
        $missing = @()
        if (-not $python) { $missing += 'Python 3.12 x64' }
        if (-not $node) { $missing += 'Node.js 22.12+ (LTS)' }
        if ($CheckOnly) { throw ('Missing free build tools: ' + ($missing -join ', ')) }
        Write-Host ('Missing free build tools: ' + ($missing -join ', ')) -ForegroundColor Yellow
        Write-Host 'Choosing Y installs them with Windows Package Manager and accepts the displayed package/source agreements.'
        $choice = Read-Host 'Install these free tools? Windows may ask for administrator approval. [Y/N]'
        if ($choice -notmatch '^[Yy]$') { throw 'Prerequisite installation declined. Install Python 3.12 and Node.js LTS manually, then retry.' }
        $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
        if (-not $winget) { throw 'winget is unavailable. Install Python 3.12 from python.org and Node.js LTS from nodejs.org, then rerun this launcher.' }
        if (-not $python) {
            Invoke-Step 'Install-free-Python' $winget.Source @('install','--exact','--id','Python.Python.3.12','--source','winget','--scope','user','--accept-package-agreements','--accept-source-agreements')
        }
        if (-not $node) {
            Invoke-Step 'Install-free-Node-LTS' $winget.Source @('install','--exact','--id','OpenJS.NodeJS.LTS','--source','winget','--accept-package-agreements','--accept-source-agreements')
        }
        $env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')
        $python = Find-Python312
        $node = Find-Node
    }
    if (-not $python -or -not $node) { throw 'Build tools are not available yet. Restart this launcher after the installations complete.' }
    $npm = (Get-Command npm.cmd -ErrorAction Stop).Source
    $npx = (Get-Command npx.cmd -ErrorAction Stop).Source
    Invoke-Step 'Python-x64-check' $python @('-c','import struct,sys; assert sys.version_info[:2] == (3,12) and struct.calcsize(chr(80))==8; print(sys.version)')
    Invoke-Step 'Node-version-check' $node @('-p','process.versions.node')
    if ($CheckOnly) {
        Save-Result 'PREREQUISITES_ONLY' 'Prerequisites are available. No build, installer, model or application test was run.'
        Write-Host 'Prerequisite check passed.' -ForegroundColor Green
        exit 0
    }

    $drive = New-Object System.IO.DriveInfo ([IO.Path]::GetPathRoot($root))
    if (-not $ResumeInstall -and $drive.AvailableFreeSpace -lt 6GB) { throw 'At least 6 GB free disk space is required before downloading build dependencies.' }
    $env:PIP_DISABLE_PIP_VERSION_CHECK = '1'
    $env:CSC_IDENTITY_AUTO_DISCOVERY = 'false'
    $venv = Join-Path $root '.venv-win'
    if (-not $ResumeInstall -and -not $UpdateExisting) {
        Invoke-Step 'Create-local-Python-environment' $python @('-m','venv',$venv)
    }
    $python = Join-Path $venv 'Scripts\python.exe'
    $env:LOCALCUT_PYTHON = $python
    $env:LOCALCUT_MEDIA_DIR = Join-Path $root 'vendor\media'
    Remove-Item Env:\LOCALCUT_PACKAGED_EXE -ErrorAction SilentlyContinue
    if (-not $ResumeInstall) {
    if (-not $UpdateExisting) {
    Invoke-Step 'Install-locked-Python-dependencies' $python @('-m','pip','install','-r','requirements-dev.txt','-c','constraints.txt')
    Invoke-Step 'Install-locked-Node-dependencies' $npm @('ci')
    }
    Invoke-Step 'Download-Electron-runtime' $node @('node_modules/electron/install.js')
    Invoke-Step 'Verify-Windows-FFmpeg-download' $python @('scripts/prepare-media.py')
    Invoke-Step 'Python-tests' $python @('-m','pytest','-q','--junitxml=windows-results/python.xml')
    Invoke-Step 'Node-policy-tests' $npm @('run','test:desktop')
    Invoke-Step 'Build-desktop-UI' $npm @('run','build')
    Invoke-Step 'Real-Electron-edit-and-restart-test' $node @('scripts/electron-smoke.cjs')
    Invoke-Step 'Bundle-Python-runtime' $python @('scripts/build-engine.py')
    Invoke-Step 'Test-bundled-engine' $python @('scripts/frozen-smoke.py')
    Invoke-Step 'Build-Windows-installer-no-publish' $npx @('electron-builder','--config','electron-builder.cjs','--win','nsis','--x64','--publish','never')
    }

    $installer = Get-BuiltInstaller $root
    $summary.installer = $installer
    (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash | Set-Content -LiteralPath (Join-Path $results 'installer-sha256.txt') -Encoding ASCII
    Assert-AppClosed
    Write-Host "`nInstalling the locally built app for this user. Existing job data is preserved." -ForegroundColor Cyan
    $process = Start-Process -FilePath $installer -ArgumentList '/S' -PassThru -Wait
    $summary.steps += [ordered]@{ name = 'Install-for-current-user'; exitCode = $process.ExitCode }
    if ($process.ExitCode -ne 0) { throw "Installer exited with code $($process.ExitCode)" }
    $installed = Join-Path $env:LOCALAPPDATA 'Programs\LocalCut AI\LocalCut AI.exe'
    foreach ($relative in @('LocalCut AI.exe','resources\engine\localcut-engine.exe','resources\media\ffmpeg.exe','resources\media\ffprobe.exe')) {
        if (-not (Test-Path -LiteralPath (Join-Path (Split-Path $installed) $relative))) { throw "Missing installed component: $relative" }
    }
    $summary.installedApp = $installed
    $env:LOCALCUT_PACKAGED_EXE = $installed
    Invoke-Step 'Installed-app-edit-and-restart-test' $node @('scripts/electron-smoke.cjs')
    if ($ResumeInstall) {
        Save-Result 'INSTALLED_APP_TEST_PASSED' 'Existing installer installed successfully and installed app tests passed. Earlier build/test stages were not rerun. Actual speech and online updates remain separate tests.'
    } else {
        Save-Result 'AUTOMATED_WINDOWS_TESTS_PASSED' 'Local build, source app, bundled engine, installer and installed app tests passed. Actual speech and online updates remain separate tests.'
    }
    Write-Host "`nThis run passed. Check its mode and completed stages in: $results\RESULT.txt" -ForegroundColor Green
    if (-not $NoLaunch) { Start-Process -FilePath $installed | Out-Null }
    exit 0
} catch {
    $message = $_.Exception.Message
    Write-Host "`nSTOPPED: $message" -ForegroundColor Red
    if (Test-Path -LiteralPath $results) { Save-Result 'FAILED' $message }
    exit 1
}
