=======================================================
           Compet — Xbox Gamepad Edition
=======================================================

【What's new】
  原版启动链路需要 3 个脚本（start.vbs → start.bat → GamepadBridge.ps1），
  现在只需要一个 CompettLauncher.exe 即可完成所有工作。

【Files you need】
  CompetLauncher.exe     ← 启动这个！(管理员权限自动提权)
  Compet.exe             ← 桌面宠物主程序
  CompetInputFix.dll     ← 输入修正 DLL
  gamepad_config.json    ← 手柄按键映射配置
  _internal/             ← 运行时依赖（Qt DLL、皮肤、音效等）
  GamepadSettings.ps1    ← 手柄映射 GUI 配置工具（可选）
  GamepadSettings.bat    ← 同上，双击打开

【How to use】
  1. 双击 CompetLauncher.exe
  2. 点击 UAC 弹窗的"是"（需要管理员权限来注入 DLL）
  3. 桌面宠物出现，手柄即可操作

【Handy button mapping (Xbox controller → PC keys)】
  A/B/X/Y       →  F13/F14/F15/F16
  LB/RB         →  F17/F18
  LT/RT         →  F19/F20
  DPad          →  F21–F24
  Start         →  TAB
  Back          →  ESC
  Left Stick    →  WASD / Numpad 8426
  Right Stick   →  Arrow keys

  修改按键：双击 GamepadSettings.bat 打开 GUI 配置。

【Build from source】
  源码在 _dev/ 目录：_dev/launcher-src（启动器）、_dev/injector-src（动图补丁）

【Tech stack】
  Go + Windows API (XInput, keybd_event, DLL injection)
  无需 PowerShell、无需 vbs，单文件启动器完成一切。

=======================================================

【Animated skins (GIF / WebP)】
  皮肤图片可以使用动图：把 idle_image / tap_images / key_mappings 里的图片
  换成一个 .gif 或 .webp 文件即可，宠物会逐帧播放；PNG 等静态图完全保持原样。
  例：把 skins\myskin\config.json 里的 "idle_image" 改成 "idle.gif"。

  说明：
    - 该功能由 CompetGifFix.dll + CompetGifFix.py 在启动时注入实现，
      不修改 Compet.exe 本体，重启即还原。
    - 删除 CompetGifFix.dll 即可完全关闭此功能（启动器会自动跳过）。
    - 若动图不显示，检查 CompetGifFix.log 和 %USERPROFILE%\_compet_gif_fix_error.log。

【Build from source】
  安装 Go 后运行 _dev\launcher-src\build-launcher.bat 生成 CompetLauncher.exe。
  重新编译动图补丁 DLL：运行 _dev\injector-src\build-giffix.bat（需要 C 编译器，脚本会自动探测 zig）。