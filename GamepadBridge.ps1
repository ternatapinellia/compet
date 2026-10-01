$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$configPath = Join-Path $root 'gamepad_config.json'
$logPath = Join-Path $root 'gamepad_bridge_error.txt'

Add-Type @'
using System;
using System.Runtime.InteropServices;

public static class XInputBridge {

    [StructLayout(LayoutKind.Sequential)]
    public struct GAMEPAD {
        public ushort wButtons;
        public byte bLeftTrigger;
        public byte bRightTrigger;
        public short sThumbLX;
        public short sThumbLY;
        public short sThumbRX;
        public short sThumbRY;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct STATE {
        public uint dwPacketNumber;
        public GAMEPAD Gamepad;
    }

    [DllImport("xinput1_4.dll", EntryPoint="XInputGetState")]
    public static extern uint GetState(
        uint userIndex,
        out STATE state
    );

    [DllImport("user32.dll", SetLastError=true)]
    public static extern void keybd_event(
        byte bVk,
        byte bScan,
        uint dwFlags,
        UIntPtr dwExtraInfo
    );

    public const uint KEYEVENTF_KEYUP = 0x0002;
    public const uint KEYEVENTF_SCANCODE = 0x0008;
}
'@


# ============================================================
# 普通虚拟键
# ============================================================

function Send-VirtualKey([string]$token, [bool]$down) {

    $m = @{
        F13=0x7C
        F14=0x7D
        F15=0x7E
        F16=0x7F
        F17=0x80
        F18=0x81
        F19=0x82
        F20=0x83
        F21=0x84
        F22=0x85
        F23=0x86
        F24=0x87

        W=0x57
        A=0x41
        S=0x53
        D=0x44

        UP=0x26
        DOWN=0x28
        LEFT=0x25
        RIGHT=0x27

        TAB=0x09
        ESC=0x1B
    }

    if (-not $m.ContainsKey($token)) {
        return
    }

    if ($down) {
        $flags = 0
    }
    else {
        $flags = [XInputBridge]::KEYEVENTF_KEYUP
    }

    [XInputBridge]::keybd_event(
        [byte]$m[$token],
        0,
        $flags,
        [UIntPtr]::Zero
    )
}


# ============================================================
# 小键盘 8 / 2 / 4 / 6
# 使用 Scan Code，不依赖 NumLock
# ============================================================

function Send-NumpadScanCode([string]$token, [bool]$down) {

    $scan = @{
        NUM8 = 0x48
        NUM2 = 0x50
        NUM4 = 0x4B
        NUM6 = 0x4D
    }

    if (-not $scan.ContainsKey($token)) {
        return
    }

    $flags = [XInputBridge]::KEYEVENTF_SCANCODE

    if (-not $down) {
        $flags = $flags -bor [XInputBridge]::KEYEVENTF_KEYUP
    }

    [XInputBridge]::keybd_event(
        0,
        [byte]$scan[$token],
        $flags,
        [UIntPtr]::Zero
    )
}


# ============================================================
# 统一发送键
# ============================================================

function Send-Key([string]$token, [bool]$down) {

    switch ($token) {

        'NUM2' {
            Send-NumpadScanCode $token $down
            return
        }

        'NUM4' {
            Send-NumpadScanCode $token $down
            return
        }

        'NUM6' {
            Send-NumpadScanCode $token $down
            return
        }

        'NUM8' {
            Send-NumpadScanCode $token $down
            return
        }

        default {
            Send-VirtualKey $token $down
            return
        }
    }
}


# ============================================================
# 读取配置
# ============================================================

if (-not (Test-Path -LiteralPath $configPath)) {

    'gamepad_config.json not found.' |
        Set-Content -LiteralPath $logPath

    exit 1
}


try {

    $jsonText = Get-Content -Raw -LiteralPath $configPath
    $jsonText = $jsonText.TrimStart([char]0xFEFF)

    $cfg = $jsonText | ConvertFrom-Json
}
catch {

    $_.Exception.ToString() |
        Set-Content -LiteralPath $logPath

    exit 1
}


# ============================================================
# 建立映射
# ============================================================

$map = @{}

foreach ($p in $cfg.mappings.PSObject.Properties) {

    $map[$p.Name] = [string]$p.Value
}


# ============================================================
# 普通按键状态
# ============================================================

$last = @{}

foreach ($k in $map.Keys) {

    $last[$k] = $false
}


# ============================================================
# LS 专用状态
#
# 水平：
#  0 = 中间
#  1 = 右
# -1 = 左
#
# 垂直：
#  0 = 中间
#  1 = 上
# -1 = 下
# ============================================================

$lsHorizontal = 0
$lsVertical = 0


# ============================================================
# LS 参数
# ============================================================

$LS_ENGAGE = 12000
$LS_RELEASE = 7000


# ============================================================
# 主循环
# ============================================================

while ($true) {

    $found = $false


    # ========================================================
    # 检查 XInput 手柄
    # ========================================================

    for ($i = 0; $i -lt 4; $i++) {

        $state = New-Object XInputBridge+STATE

        if (
            [XInputBridge]::GetState(
                $i,
                [ref]$state
            ) -eq 0
        ) {

            $found = $true
            break
        }
    }


    if ($found) {

        $b = $state.Gamepad.wButtons


        # ====================================================
        # Xbox 实体按钮
        # ====================================================

        $names = @{
            A         = 0x1000
            B         = 0x2000
            X         = 0x4000
            Y         = 0x8000

            LB        = 0x0100
            RB        = 0x0200

            DPadUp    = 0x0001
            DPadDown  = 0x0002
            DPadLeft  = 0x0004
            DPadRight = 0x0008

            Start     = 0x0010
            Back      = 0x0020

            LS        = 0x0040
            RS        = 0x0080
        }


        foreach ($n in $names.Keys) {

            $down = (($b -band $names[$n]) -ne 0)

            if ($last[$n] -ne $down) {

                if ($map.ContainsKey($n)) {

                    Send-Key $map[$n] $down
                }

                $last[$n] = $down
            }
        }


        # ====================================================
        # LT
        # ====================================================

        $ltDown = ($state.Gamepad.bLeftTrigger -ge 30)

        if ($last['LT'] -ne $ltDown) {

            if ($map.ContainsKey('LT')) {

                Send-Key $map['LT'] $ltDown
            }

            $last['LT'] = $ltDown
        }


        # ====================================================
        # RT
        # ====================================================

        $rtDown = ($state.Gamepad.bRightTrigger -ge 30)

        if ($last['RT'] -ne $rtDown) {

            if ($map.ContainsKey('RT')) {

                Send-Key $map['RT'] $rtDown
            }

            $last['RT'] = $rtDown
        }


        # ====================================================
        # RS
        # ====================================================

        $rx = $state.Gamepad.sThumbRX
        $ry = $state.Gamepad.sThumbRY


        # RS 左

        $rsLeft = ($rx -le -12000)

        if ($last['RS_Left'] -ne $rsLeft) {

            if ($map.ContainsKey('RS_Left')) {

                Send-Key $map['RS_Left'] $rsLeft
            }

            $last['RS_Left'] = $rsLeft
        }


        # RS 右

        $rsRight = ($rx -ge 12000)

        if ($last['RS_Right'] -ne $rsRight) {

            if ($map.ContainsKey('RS_Right')) {

                Send-Key $map['RS_Right'] $rsRight
            }

            $last['RS_Right'] = $rsRight
        }


        # RS 下

        $rsDown = ($ry -le -12000)

        if ($last['RS_Down'] -ne $rsDown) {

            if ($map.ContainsKey('RS_Down')) {

                Send-Key $map['RS_Down'] $rsDown
            }

            $last['RS_Down'] = $rsDown
        }


        # RS 上

        $rsUp = ($ry -ge 12000)

        if ($last['RS_Up'] -ne $rsUp) {

            if ($map.ContainsKey('RS_Up')) {

                Send-Key $map['RS_Up'] $rsUp
            }

            $last['RS_Up'] = $rsUp
        }


        # ====================================================
        # LS
        #
        # 水平方向只允许 LEFT / RIGHT 二选一
        # 垂直方向只允许 UP / DOWN 二选一
        #
        # 按住 LS：
        # KeyDown 一次
        # 持续保持
        #
        # 回中：
        # KeyUp 一次
        # ====================================================

        $lx = $state.Gamepad.sThumbLX
        $ly = $state.Gamepad.sThumbLY


        # ====================================================
        # LS 水平
        # ====================================================

        if ($lsHorizontal -eq 0) {

            if ($lx -le -$LS_ENGAGE) {

                if ($map.ContainsKey('LS_Left')) {

                    Send-Key $map['LS_Left'] $true
                }

                $lsHorizontal = -1
            }

            elseif ($lx -ge $LS_ENGAGE) {

                if ($map.ContainsKey('LS_Right')) {

                    Send-Key $map['LS_Right'] $true
                }

                $lsHorizontal = 1
            }
        }


        elseif ($lsHorizontal -eq -1) {

            # 正在向左

            if ($lx -ge -$LS_RELEASE) {

                if ($map.ContainsKey('LS_Left')) {

                    Send-Key $map['LS_Left'] $false
                }

                $lsHorizontal = 0
            }
        }


        elseif ($lsHorizontal -eq 1) {

            # 正在向右

            if ($lx -le $LS_RELEASE) {

                if ($map.ContainsKey('LS_Right')) {

                    Send-Key $map['LS_Right'] $false
                }

                $lsHorizontal = 0
            }
        }


        # ====================================================
        # LS 垂直
        # ====================================================

        if ($lsVertical -eq 0) {

            if ($ly -le -$LS_ENGAGE) {

                if ($map.ContainsKey('LS_Down')) {

                    Send-Key $map['LS_Down'] $true
                }

                $lsVertical = -1
            }

            elseif ($ly -ge $LS_ENGAGE) {

                if ($map.ContainsKey('LS_Up')) {

                    Send-Key $map['LS_Up'] $true
                }

                $lsVertical = 1
            }
        }


        elseif ($lsVertical -eq -1) {

            # 正在向下

            if ($ly -ge -$LS_RELEASE) {

                if ($map.ContainsKey('LS_Down')) {

                    Send-Key $map['LS_Down'] $false
                }

                $lsVertical = 0
            }
        }


        elseif ($lsVertical -eq 1) {

            # 正在向上

            if ($ly -le $LS_RELEASE) {

                if ($map.ContainsKey('LS_Up')) {

                    Send-Key $map['LS_Up'] $false
                }

                $lsVertical = 0
            }
        }

    }
    else {

        # ====================================================
        # 手柄断开
        # ====================================================

        foreach ($n in @($map.Keys)) {

            if ($last.ContainsKey($n)) {

                if ($last[$n]) {

                    Send-Key $map[$n] $false

                    $last[$n] = $false
                }
            }
        }


        # ====================================================
        # 释放 LS
        # ====================================================

        if ($lsHorizontal -eq -1) {

            if ($map.ContainsKey('LS_Left')) {

                Send-Key $map['LS_Left'] $false
            }
        }

        elseif ($lsHorizontal -eq 1) {

            if ($map.ContainsKey('LS_Right')) {

                Send-Key $map['LS_Right'] $false
            }
        }


        if ($lsVertical -eq -1) {

            if ($map.ContainsKey('LS_Down')) {

                Send-Key $map['LS_Down'] $false
            }
        }

        elseif ($lsVertical -eq 1) {

            if ($map.ContainsKey('LS_Up')) {

                Send-Key $map['LS_Up'] $false
            }
        }


        $lsHorizontal = 0
        $lsVertical = 0
    }


    Start-Sleep -Milliseconds 12
}