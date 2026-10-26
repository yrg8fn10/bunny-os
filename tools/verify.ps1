# Bunny OS repository verification for Windows hosts (no Python/Git required).
# Canonical checker: tools/verify.py. This mirror exists so the project can be
# validated from PowerShell before pushing to a Linux builder.
#
#   powershell -ExecutionPolicy Bypass -File tools\verify.ps1
#   powershell -ExecutionPolicy Bypass -File tools\verify.ps1 -Strict

param([switch]$Strict)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$script:Failures = 0
$script:Warnings = 0

function Write-Head([string]$Text) {
    Write-Host ""
    Write-Host "== $Text" -ForegroundColor Magenta
}

function Check([string]$Name, [bool]$Ok, [string]$Detail = "", [switch]$Warn) {
    if ($Ok) {
        Write-Host "  [ok]   $Name" -ForegroundColor Green
    } elseif ($Warn -and -not $Strict) {
        Write-Host "  [warn] $Name $Detail" -ForegroundColor Yellow
        $script:Warnings++
    } else {
        Write-Host "  [FAIL] $Name $Detail" -ForegroundColor Red
        $script:Failures++
    }
}

$Required = @(
    'VERSION',
    'build_bunny_os_iso.sh',
    'iso/profiledef.sh',
    'iso/packages.x86_64',
    'iso/pacman.conf',
    'iso/airootfs/root/customize_airootfs.sh',
    'iso/airootfs/etc/os-release',
    'iso/airootfs/etc/bunny/settings.json',
    'iso/airootfs/etc/sddm.conf.d/10-bunny.conf',
    'iso/airootfs/etc/sddm.conf.d/20-bunny-session.conf',
    'system/bin/bunny-session',
    'system/bin/bunny-panel',
    'system/bin/bunny-panel-bridge',
    'system/bin/bunnyctl',
    'system/bin/bunny-firstboot',
    'system/bin/bunny-update',
    'system/bin/bunny-health',
    'system/lib/bunny_sessiond.py',
    'system/lib/bunny_input_agent.py',
    'system/units/bunny-sessiond.service',
    'system/units/bunny-input-agent.service',
    'system/units/bunny-firstboot.service',
    'system/units/bunny-update.service',
    'system/units/bunny-update.timer',
    'system/units/bunny-health.service',
    'system/units/bunny-health.timer',
    'system/user-units/bunny-bunbun.service',
    'system/wayland-sessions/bunny-gaming.desktop',
    'system/wayland-sessions/bunny-desktop.desktop',
    'bunbun/pyproject.toml',
    'bunbun/bunbun/service.py',
    'bunbun/bunbun/mam/policy.py',
    'bunbun/bunbun/mam/engine.py',
    'bunbun/bunbun/data/persona.json',
    'bunbun/tests/test_policy.py',
    'bunbun/tests/test_engine.py',
    'bunbun/tests/test_service.py',
    'control-panel/ui/index.html',
    'control-panel/ui/js/app.js',
    'control-panel/ui/css/panel.css',
    'control-panel/ui/assets/bunny.svg',
    'control-panel/src-tauri/Cargo.toml',
    'control-panel/src-tauri/tauri.conf.json',
    'launchers/bin/bunny-launcher',
    'launchers/bin/bunny-platform-scan',
    'installer/bunny-install',
    'iso/targets/deck/target.conf',
    'iso/targets/deck/packages.x86_64',
    'iso/targets/deck/overlay/efiboot/loader/entries/01-bunny-os.conf',
    'iso/targets/deck/airootfs/etc/systemd/zram-generator.conf',
    'docs/ARCHITECTURE.md',
    'docs/BUILD.md',
    'docs/SESSIONS.md',
    'docs/BUNBUN.md',
    'docs/SAFETY-AND-LEGAL.md',
    'docs/STEAMDECK.md',
    '.github/workflows/build-iso.yml'
)

Write-Host "Bunny OS repository verification" -ForegroundColor Magenta
Write-Host "root: $Root"

# --- structure --------------------------------------------------------------
Write-Head "structure"
$missing = @()
foreach ($rel in $Required) {
    $path = Join-Path $Root ($rel -replace '/', '\')
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { $missing += $rel }
}
$missingDetail = ($missing | Select-Object -First 8) -join ', '
$presentCount = $Required.Count - $missing.Count
Check ("{0}/{1} required files present" -f $presentCount, $Required.Count) `
    ($missing.Count -eq 0) $missingDetail

$empty = @()
foreach ($rel in $Required) {
    $path = Join-Path $Root ($rel -replace '/', '\')
    if ((Test-Path -LiteralPath $path -PathType Leaf) -and (Get-Item -LiteralPath $path).Length -eq 0) {
        $empty += $rel
    }
}
Check 'no empty required files' ($empty.Count -eq 0) ($empty -join ', ')

# --- helper to enumerate project text files --------------------------------
$TextExtensions = @('.sh','.py','.js','.css','.html','.json','.md','.service','.timer','.desktop','.conf','.toml','.yml','.yaml')
$ExtraNames = @('bunnyctl','bunny-session','bunny-panel','bunny-panel-bridge','bunny-firstboot',
                'bunny-update','bunny-health','bunny-launcher','bunny-platform-scan','bunny-install',
                'bunny-cli','Makefile','VERSION')
$SkipDirs = @('build','out','node_modules','target','.git','__pycache__','vendor')

$Files = Get-ChildItem -LiteralPath $Root -Recurse -File | Where-Object {
    $parts = $_.FullName.Substring($Root.Length).Split([IO.Path]::DirectorySeparatorChar)
    $isSkipped = $false
    foreach ($part in $parts) { if ($SkipDirs -contains $part) { $isSkipped = $true } }
    (-not $isSkipped) -and ($TextExtensions -contains $_.Extension -or $ExtraNames -contains $_.Name)
}

# --- json -------------------------------------------------------------------
Write-Head "json"
$badJson = @()
foreach ($f in $Files | Where-Object { $_.Extension -eq '.json' }) {
    try { $null = Get-Content -LiteralPath $f.FullName -Raw | ConvertFrom-Json }
    catch { $badJson += "$($f.Name): $($_.Exception.Message)" }
}
Check 'all JSON parses' ($badJson.Count -eq 0) (($badJson | Select-Object -First 3) -join '; ')

# --- systemd ----------------------------------------------------------------
Write-Head "systemd"
$units = $Files | Where-Object { $_.Extension -in @('.service', '.timer') }
$badUnits = @()
foreach ($u in $units) {
    $text = Get-Content -LiteralPath $u.FullName -Raw
    if ($text -notmatch '\[Unit\]') { $badUnits += "$($u.Name): no [Unit]" }
    if ($u.Extension -eq '.service') {
        if ($text -notmatch '\[Service\]') { $badUnits += "$($u.Name): no [Service]" }
        if ($text -notmatch 'ExecStart') { $badUnits += "$($u.Name): no ExecStart" }
    }
    if ($u.Extension -eq '.timer' -and $text -notmatch '\[Timer\]') {
        $badUnits += "$($u.Name): no [Timer]"
    }
}
Check ("{0} units structurally valid" -f $units.Count) ($badUnits.Count -eq 0) ($badUnits -join '; ')

$sessiond = Get-Content -LiteralPath (Join-Path $Root 'system\units\bunny-sessiond.service') -Raw
Check 'bunny-sessiond runs as root' ($sessiond -notmatch '(?m)^User=')
$bunbunUnit = Join-Path $Root 'system\user-units\bunny-bunbun.service'
Check 'Bun Bun ships as a user unit' (Test-Path -LiteralPath $bunbunUnit -PathType Leaf) ''

$inputUnit = Get-Content -LiteralPath (Join-Path $Root 'system\units\bunny-input-agent.service') -Raw
Check 'input agent requires consent token' ($inputUnit -match 'ConditionPathExists=/etc/bunny/allow-input-agent')
Check 'input agent is masked at build time' ((Get-Content -LiteralPath (Join-Path $Root 'iso\airootfs\root\customize_airootfs.sh') -Raw) -match 'mask bunny-input-agent')

# --- desktop entries --------------------------------------------------------
Write-Head "desktop entries"
$badEntries = @()
foreach ($e in $Files | Where-Object { $_.Extension -eq '.desktop' }) {
    $text = Get-Content -LiteralPath $e.FullName -Raw
    foreach ($key in @('[Desktop Entry]', 'Name=', 'Type=', 'Exec=')) {
        if ($text -notmatch [regex]::Escape($key)) { $badEntries += "$($e.Name): $key" }
    }
}
Check 'desktop entries valid' ($badEntries.Count -eq 0) ($badEntries -join '; ')

# --- hygiene ----------------------------------------------------------------
Write-Head "hygiene"
$crlf = @()
foreach ($f in $Files) {
    $bytes = [IO.File]::ReadAllBytes($f.FullName)
    for ($i = 0; $i -lt [Math]::Min($bytes.Length - 1, 4096); $i++) {
        if ($bytes[$i] -eq 13 -and $bytes[$i + 1] -eq 10) {
            $crlf += $f.FullName.Substring($Root.Length + 1); break
        }
    }
}
Check 'no CRLF line endings' ($crlf.Count -eq 0) (($crlf | Select-Object -First 6) -join ', ')

$secretPatterns = @('sk-[A-Za-z0-9]{20,}', 'ghp_[A-Za-z0-9]{20,}', 'AKIA[0-9A-Z]{16}')
$secretHits = @()
foreach ($f in $Files) {
    $text = Get-Content -LiteralPath $f.FullName -Raw
    foreach ($pattern in $secretPatterns) {
        if ($text -match $pattern) { $secretHits += $f.Name }
    }
}
Check 'no hardcoded API keys' ($secretHits.Count -eq 0) ($secretHits -join ', ')

$allowedTokens = @(
    'iso\profiledef.sh', 'iso\airootfs\etc\os-release', 'iso\airootfs\etc\motd',
    'iso\overrides\efiboot\loader\entries\01-bunny-os.conf',
    'iso\overrides\syslinux\syslinux.cfg',
    'iso\targets\deck\overlay\efiboot\loader\entries\01-bunny-os.conf',
    'tools\verify.ps1', 'tools\verify.py'
)
$stray = @()
foreach ($f in $Files) {
    $rel = $f.FullName.Substring($Root.Length + 1)
    if ($allowedTokens -contains $rel -or $rel.StartsWith('docs\') -or $f.Name -eq 'README.md') { continue }
    $text = Get-Content -LiteralPath $f.FullName -Raw
    if ($text -match '@(VERSION|BUILD_ID|BUILD_DATE|CHANNEL)@') { $stray += $rel }
}
Check 'template tokens confined to rendered files' ($stray.Count -eq 0) ($stray -join ', ')

# --- profile ----------------------------------------------------------------
Write-Head "archiso profile"
$pkgText = Get-Content -LiteralPath (Join-Path $Root 'iso\packages.x86_64') -Raw
$packages = $pkgText -split "`r?`n" | ForEach-Object { $_.Trim() } |
    Where-Object { $_ -ne '' -and -not $_.StartsWith('#') }
$forbidden = @('heroic-games-launcher', 'heroic-games-launcher-bin', 'yay', 'paru',
               'google-chrome', 'visual-studio-code-bin', 'spotify')
$hits = $packages | Where-Object { $forbidden -contains $_ }
Check 'no AUR-only packages' ($null -eq $hits) ($hits -join ', ')
Check ("{0} explicit packages" -f $packages.Count) ($packages.Count -ge 40) ''
$badNames = @($packages | Where-Object { $_ -notmatch '^[a-z0-9@._+-]+$' })
Check 'package names well formed' ($badNames.Count -eq 0) ($badNames -join ', ')
Check 'multilib enabled' ((Get-Content -LiteralPath (Join-Path $Root 'iso\pacman.conf') -Raw) -match '\[multilib\]')

$profile = Get-Content -LiteralPath (Join-Path $Root 'iso\profiledef.sh') -Raw
foreach ($key in @('iso_name=', 'iso_label=', 'bootmodes=', 'install_dir=', 'airootfs_image_type=')) {
    Check "profiledef: $key" ($profile.Contains($key))
}
Check 'boots UEFI + BIOS' ($profile -match 'uefi.systemd-boot' -and $profile -match 'bios.syslinux')

# --- target profiles --------------------------------------------------------
Write-Head "target profiles"
$targetRoot = Join-Path $Root 'iso\targets'
$targetConfs = @()
if (Test-Path -LiteralPath $targetRoot -PathType Container) {
    $targetConfs = @(Get-ChildItem -LiteralPath $targetRoot -Directory |
        ForEach-Object { Join-Path $_.FullName 'target.conf' } |
        Where-Object { Test-Path -LiteralPath $_ -PathType Leaf })
}
Check ("{0} target profile(s)" -f $targetConfs.Count) ($targetConfs.Count -ge 1) ''
foreach ($tc in $targetConfs) {
    $tdir = Split-Path -Parent $tc
    $tname = Split-Path -Leaf $tdir
    $ttext = Get-Content -LiteralPath $tc -Raw
    Check "target ${tname}: id matches directory" ($ttext -match "BUNNY_TARGET_ID=`"$([regex]::Escape($tname))`"") ''
    foreach ($key in @('BUNNY_TARGET_NAME', 'BUNNY_ISO_BASENAME', 'BUNNY_GAMESCOPE_ARGS', 'BUNNY_KERNEL_ARGS')) {
        Check "target ${tname}: $key" ($ttext.Contains("$key=")) ''
    }
    Check "target ${tname}: packages list" (Test-Path -LiteralPath (Join-Path $tdir 'packages.x86_64') -PathType Leaf) ''
}
$deckConf = Join-Path $targetRoot 'deck\target.conf'
if (Test-Path -LiteralPath $deckConf -PathType Leaf) {
    $deckText = Get-Content -LiteralPath $deckConf -Raw
    $deckPkgs = Get-Content -LiteralPath (Join-Path $targetRoot 'deck\packages.x86_64') -Raw
    Check 'Steam Deck LCD renders 1280x800' ($deckText -match '1280 -H 800') ''
    Check 'Steam Deck sets amd_pstate=active' ($deckText -match 'amd_pstate=active') ''
    Check 'Steam Deck ships fwupd' ($deckPkgs -match '(?m)^fwupd$') ''
    Check 'Steam Deck ships zram config' (Test-Path -LiteralPath (Join-Path $targetRoot 'deck\airootfs\etc\systemd\zram-generator.conf') -PathType Leaf) ''
    $deckPkgNames = @($deckPkgs -split "`r?`n" | ForEach-Object { $_.Trim() } |
        Where-Object { $_ -ne '' -and -not $_.StartsWith('#') })
    Check 'no Valve/AUR kernel package' (-not ($deckPkgNames -contains 'steamdeck-dkms')) ''
}
$sessionScript = Get-Content -LiteralPath (Join-Path $Root 'system\bin\bunny-session') -Raw
Check 'session reads per-target config' ($sessionScript -match '/etc/bunny/target\.conf') ''
$installerScript = Get-Content -LiteralPath (Join-Path $Root 'installer\bunny-install') -Raw
Check 'installer carries target kernel args' ($installerScript -match 'BUNNY_KERNEL_ARGS') ''
$deckDoc = Join-Path $Root 'docs\STEAMDECK.md'
if (Test-Path -LiteralPath $deckDoc -PathType Leaf) {
    $deckDocText = Get-Content -LiteralPath $deckDoc -Raw
    Check 'Deck doc scopes LCD vs OLED' (($deckDocText -match '(?i)lcd') -and ($deckDocText -match '(?i)oled')) ''
    Check 'Deck doc covers SteamOS recovery' ($deckDocText -match '(?i)recovery') ''
    Check 'Deck doc names the artefact' ($deckDocText -match 'BunnyOS-deck-installer\.iso') ''
    Check 'Deck doc states dual-boot position' ($deckDocText -match '(?i)dual') ''
}

# --- bun bun safety ---------------------------------------------------------
Write-Head "Bun Bun safety invariants"
$policy = Get-Content -LiteralPath (Join-Path $Root 'bunbun\bunbun\mam\policy.py') -Raw
foreach ($pair in @(
    @('anticheat', 'anti-cheat titles denied'),
    @('competitive', 'competitive modes denied'),
    @('coop_opt_in', 'multiplayer requires opt-in'),
    @('input-token', 'input requires root token'),
    @('kid-safe-chat', 'kid-safe blocks stranger chat')
)) {
    Check $pair[1] ($policy.Contains($pair[0]))
}
$coop = Get-Content -LiteralPath (Join-Path $Root 'bunbun\bunbun\action\coop.py') -Raw
Check 'join requires player confirmation' ($coop -match 'player_confirmed')
Check 'Steam lobby deep link' ($coop -match 'joinlobby')
$servicePy = Get-Content -LiteralPath (Join-Path $Root 'bunbun\bunbun\service.py') -Raw
Check 'agent binds loopback only' ($servicePy -match '127\.0\.0\.1')
Check 'local-only advertised' ($servicePy -match 'local_only')

# --- UI ---------------------------------------------------------------------
Write-Head "control panel"
$html = Get-Content -LiteralPath (Join-Path $Root 'control-panel\ui\index.html') -Raw
Check 'app mount point' ($html -match 'id="app"')
Check 'app module loaded' ($html -match 'js/app\.js')
Check 'focus markers' ($html -match 'data-focusable')
Check 'Bun Bun panel entry' ($html -match 'Bun Bun')
$appJs = Get-Content -LiteralPath (Join-Path $Root 'control-panel\ui\js\app.js') -Raw
Check 'gamepad navigation' ($appJs -match '(?i)gamepad')
Check 'mock/offline fallback' ($appJs -match '(?i)mock')
$tauriConfig = Get-Content -LiteralPath (Join-Path $Root 'control-panel\src-tauri\tauri.conf.json') -Raw | ConvertFrom-Json
Check 'Tauri config parsed' ($null -ne $tauriConfig.app -or $null -ne $tauriConfig.tauri) ''
Check 'Tauri global API enabled' ($tauriConfig.app.withGlobalTauri -eq $true) ''
$apiJs = Get-Content -LiteralPath (Join-Path $Root 'control-panel\ui\js\api.js') -Raw
Check 'native calls not double-wrapped' (-not ($apiJs -match "_invoke\('bunny_call'")) ''
$sessiondPy = Get-Content -LiteralPath (Join-Path $Root 'system\lib\bunny_sessiond.py') -Raw
Check 'autologin drop-in is daemon-owned' (($sessiondPy -match 'refresh_sddm') -and ($sessiondPy -match '\[Autologin\]')) ''
$cargo = Get-Content -LiteralPath (Join-Path $Root 'control-panel\src-tauri\Cargo.toml') -Raw
Check 'Tauri dependency declared' ($cargo -match '(?m)^tauri\s*=') ''

# --- pipeline ---------------------------------------------------------------
Write-Head "build pipeline"
$build = Get-Content -LiteralPath (Join-Path $Root 'build_bunny_os_iso.sh') -Raw
foreach ($needle in @('BunnyOS-installer.iso', 'mkarchiso', 'validate-profile.sh',
                      'stage-profile.sh', 'build-manifest.json', '--dry-run',
                      '--target', 'iso/targets')) {
    Check "pipeline: $needle" ($build.Contains($needle))
}
$stage = Get-Content -LiteralPath (Join-Path $Root 'scripts\stage-profile.sh') -Raw
foreach ($payload in @('system/bin', 'system/units', 'bunbun', 'control-panel/ui')) {
    Check "stages $payload" ($stage.Contains($payload))
}
Check 'staging merges target overlay and packages' (($stage.Contains('--target')) -and ($stage.Contains('packages.x86_64'))) ''
Check 'staging cannot delete /' (($stage -match '\[\[ "\$\{AIR\}" != "/" \]\]') -or ($stage -match 'safe_rmrf')) ''
$workflow = Get-Content -LiteralPath (Join-Path $Root '.github\workflows\build-iso.yml') -Raw
Check 'CI can build a target profile' ($workflow.Contains('--target')) ''
Check 'CI exposes a target input' ($workflow.Contains('inputs.target')) ''

# --- summary ----------------------------------------------------------------
Write-Host ""
if ($script:Failures -eq 0) {
    Write-Host ("PASS - {0} warnings" -f $script:Warnings) -ForegroundColor Green
    exit 0
}
Write-Host ("FAIL - {0} failures, {1} warnings" -f $script:Failures, $script:Warnings) -ForegroundColor Red
exit 1
