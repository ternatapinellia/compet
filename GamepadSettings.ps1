Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$skinsRoot = Join-Path $env:USERPROFILE '.morningmeal_Compet\skins'
$gamepadPath = Join-Path $root 'gamepad_config.json'

$controls = @('A','B','X','Y','LB','RB','LT','RT','DPadUp','DPadDown','DPadLeft','DPadRight','Start','Back','LS','RS','LS_Left','LS_Right','LS_Up','LS_Down','RS_Left','RS_Right','RS_Up','RS_Down')
$slots = @{}
for ($i = 0; $i -lt $controls.Count; $i++) { 
    $slots[$controls[$i]] = 'F' + (13 + $i) 
}

$slots['Start'] = 'TAB'
$slots['Back'] = 'ESC'

$slots['LS'] = 'WASD'
$slots['RS'] = 'ARROWS'

$slots['LS_Left'] = 'NUM4'
$slots['LS_Right'] = 'NUM6'
$slots['LS_Up'] = 'NUM8'
$slots['LS_Down'] = 'NUM2'

$slots['RS_Left'] = 'LEFT'
$slots['RS_Right'] = 'RIGHT'
$slots['RS_Up'] = 'UP'
$slots['RS_Down'] = 'DOWN'
function Read-Utf8Json([string]$path) {
    $enc = New-Object System.Text.UTF8Encoding($false)
    $txt = [System.IO.File]::ReadAllText($path, $enc)
    return ($txt | ConvertFrom-Json)
}

function Write-Utf8Json([string]$path, $obj) {
    $enc = New-Object System.Text.UTF8Encoding($false)
    $txt = $obj | ConvertTo-Json -Depth 50
    [System.IO.File]::WriteAllText($path, $txt, $enc)
}

if (-not (Test-Path -LiteralPath $skinsRoot -PathType Container)) {
    [System.Windows.Forms.MessageBox]::Show('Compet skins folder not found.','Compet Xbox Settings')
    exit 1
}

$skinDirs = @(Get-ChildItem -LiteralPath $skinsRoot -Directory | Sort-Object Name)
if ($skinDirs.Count -eq 0) {
    [System.Windows.Forms.MessageBox]::Show('No pet folders were found.','Compet Xbox Settings')
    exit 1
}

$gc = $null
if (Test-Path -LiteralPath $gamepadPath) {
    try { $gc = Read-Utf8Json $gamepadPath } catch { $gc = $null }
}

$form = New-Object System.Windows.Forms.Form
$form.Text = 'Compet Xbox Gamepad Settings'
$form.StartPosition = 'CenterScreen'
$form.Size = New-Object System.Drawing.Size -ArgumentList @(640,800)
$form.FormBorderStyle = 'FixedDialog'
$form.MaximizeBox = $false

$title = New-Object System.Windows.Forms.Label
$title.Text = 'Xbox Gamepad Mapping'
$title.Font = New-Object System.Drawing.Font -ArgumentList @('Segoe UI',12,[System.Drawing.FontStyle]::Bold)
$title.Location = New-Object System.Drawing.Point -ArgumentList @(18,15)
$title.AutoSize = $true
$form.Controls.Add($title)

$skinLabel = New-Object System.Windows.Forms.Label
$skinLabel.Text = 'Pet folder:'
$skinLabel.Location = New-Object System.Drawing.Point -ArgumentList @(20,52)
$skinLabel.AutoSize = $true
$form.Controls.Add($skinLabel)

$skinBox = New-Object System.Windows.Forms.ComboBox
$skinBox.DropDownStyle = [System.Windows.Forms.ComboBoxStyle]::DropDownList
$skinBox.Location = New-Object System.Drawing.Point -ArgumentList @(110,48)
$skinBox.Size = New-Object System.Drawing.Size -ArgumentList @(350,25)
foreach ($d in $skinDirs) { [void]$skinBox.Items.Add($d.Name) }
$skinBox.SelectedIndex = 0
$form.Controls.Add($skinBox)

$info = New-Object System.Windows.Forms.Label
$info.Text = 'Image files are read from the selected pet folder.'
$info.Location = New-Object System.Drawing.Point -ArgumentList @(20,82)
$info.Size = New-Object System.Drawing.Size -ArgumentList @(590,35)
$form.Controls.Add($info)

$panel = New-Object System.Windows.Forms.Panel
$panel.Location = New-Object System.Drawing.Point -ArgumentList @(18,125)
$panel.Size = New-Object System.Drawing.Size -ArgumentList @(595,535)
$panel.AutoScroll = $true
$form.Controls.Add($panel)

$boxes = @{}
$status = New-Object System.Windows.Forms.Label
$status.Text = 'Ready.'
$status.Location = New-Object System.Drawing.Point -ArgumentList @(290,685)
$status.Size = New-Object System.Drawing.Size -ArgumentList @(185,30)
$form.Controls.Add($status)

function Load-Skin([string]$skinName) {
    $panel.Controls.Clear()
    $script:boxes = @{}
    $skinDir = Join-Path $skinsRoot $skinName
    $configPath = Join-Path $skinDir 'config.json'
    if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) {
        $status.Text = 'config.json not found.'
        return
    }
    try { $cfg = Read-Utf8Json $configPath } catch {
        $status.Text = 'Could not read config.json.'
        return
    }

    $images = @('') + @(Get-ChildItem -LiteralPath $skinDir -File | Where-Object { $_.Extension -match '^\.(png|jpg|jpeg|gif|bmp|webp)$' } | Select-Object -ExpandProperty Name)
    $savedObj = $null
    if ($gc -and $gc.skins -and $gc.skins.PSObject.Properties[$skinName]) {
        $savedObj = $gc.skins.PSObject.Properties[$skinName].Value
    }

    $y = 8
    foreach ($c in $controls) {
        $lab = New-Object System.Windows.Forms.Label
        $lab.Text = $c + '  [' + $slots[$c] + ']'
        $lab.Location = New-Object System.Drawing.Point -ArgumentList @(8,($y + 3))
        $lab.Size = New-Object System.Drawing.Size -ArgumentList @(165,23)
        $panel.Controls.Add($lab)

        $cb = New-Object System.Windows.Forms.ComboBox
        $cb.DropDownStyle = [System.Windows.Forms.ComboBoxStyle]::DropDownList
        $cb.Location = New-Object System.Drawing.Point -ArgumentList @(180,$y)
        $cb.Size = New-Object System.Drawing.Size -ArgumentList @(370,24)
        foreach ($img in $images) { [void]$cb.Items.Add($img) }

        $old = ''
        if ($savedObj) {
            $pr = $savedObj.PSObject.Properties[$c]
            if ($pr) { $old = [string]$pr.Value }
        }
        if ($old -eq '' -and $cfg.key_mappings) {
            $pr = $cfg.key_mappings.PSObject.Properties[$slots[$c]]
            if ($pr) { $old = [string]$pr.Value }
        }

        $idx = $cb.Items.IndexOf($old)
        if ($idx -ge 0) { $cb.SelectedIndex = $idx } else { $cb.SelectedIndex = 0 }
        $panel.Controls.Add($cb)
        $script:boxes[$c] = $cb
        $y += 30
    }
    $status.Text = 'Loaded: ' + $skinName
}

$save = New-Object System.Windows.Forms.Button
$save.Text = 'Save current pet'
$save.Location = New-Object System.Drawing.Point -ArgumentList @(18,680)
$save.Size = New-Object System.Drawing.Size -ArgumentList @(140,36)
$form.Controls.Add($save)

$reset = New-Object System.Windows.Forms.Button
$reset.Text = 'Clear current'
$reset.Location = New-Object System.Drawing.Point -ArgumentList @(168,680)
$reset.Size = New-Object System.Drawing.Size -ArgumentList @(110,36)
$form.Controls.Add($reset)

$close = New-Object System.Windows.Forms.Button
$close.Text = 'Close'
$close.Location = New-Object System.Drawing.Point -ArgumentList @(503,680)
$close.Size = New-Object System.Drawing.Size -ArgumentList @(110,36)
$form.Controls.Add($close)

$skinBox.Add_SelectedIndexChanged({ Load-Skin $skinBox.SelectedItem.ToString() })
$reset.Add_Click({ foreach ($c in $controls) { $boxes[$c].SelectedIndex = 0 } })
$close.Add_Click({ $form.Close() })

$save.Add_Click({
    try {
        $skinName = $skinBox.SelectedItem.ToString()
        $skinDir = Join-Path $skinsRoot $skinName
        $configPath = Join-Path $skinDir 'config.json'
        if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) { throw 'config.json not found.' }

        $cfg = Read-Utf8Json $configPath
        $backupPath = $configPath + '.bak'
        Copy-Item -LiteralPath $configPath -Destination $backupPath -Force

        $km = [ordered]@{}
        if ($cfg.key_mappings) {
            foreach ($p in $cfg.key_mappings.PSObject.Properties) { $km[$p.Name] = $p.Value }
        }

        $saved = [ordered]@{}
        foreach ($c in $controls) {
            $img = [string]$boxes[$c].SelectedItem
            $saved[$c] = $img
            $slot = $slots[$c]
            if ($km.Contains($slot)) { [void]$km.Remove($slot) }
            if ($img -ne '') { $km[$slot] = $img }
        }

        $top = [ordered]@{}
        foreach ($p in $cfg.PSObject.Properties) {
            if ($p.Name -ne 'key_mappings') { $top[$p.Name] = $p.Value }
        }
        $top['key_mappings'] = $km
        Write-Utf8Json $configPath ([pscustomobject]$top)

        $gctop = [ordered]@{}
        if ($gc) {
            foreach ($p in $gc.PSObject.Properties) {
                if ($p.Name -ne 'mappings' -and $p.Name -ne 'skins') { $gctop[$p.Name] = $p.Value }
            }
        }
        $gctop['version'] = 5

        $gcm = [ordered]@{}
        if ($gc -and $gc.mappings) {
            foreach ($p in $gc.mappings.PSObject.Properties) { $gcm[$p.Name] = [string]$p.Value }
        }
        foreach ($c in $controls) { $gcm[$c] = $slots[$c] }
        $gctop['mappings'] = $gcm

        $gskins = [ordered]@{}
        if ($gc -and $gc.skins) {
            foreach ($p in $gc.skins.PSObject.Properties) { $gskins[$p.Name] = $p.Value }
        }
        $gskins[$skinName] = [pscustomobject]$saved
        $gctop['skins'] = $gskins
        $gc = [pscustomobject]$gctop
        Write-Utf8Json $gamepadPath $gc

        $status.Text = 'Saved: ' + $skinName
        [System.Windows.Forms.MessageBox]::Show('Saved mapping for ' + $skinName,'Compet Xbox Settings')
    } catch {
        $status.Text = 'Save failed.'
        [System.Windows.Forms.MessageBox]::Show('Save failed: ' + $_.Exception.Message,'Compet Xbox Settings')
    }
})

Load-Skin $skinBox.SelectedItem.ToString()
[void]$form.ShowDialog()
