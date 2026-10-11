启动：双击 Start-Compet-Xbox.bat。它会后台启动 Compet 和 Xbox 桥接，不保留额外 CMD 窗口。
设置：把这些文件放到桌宠软件的同目录下，双击 GamepadSettings.bat。设置窗口会自动扫描 _internal\skins 下的所有桌宠文件夹，可逐只桌宠设置 Xbox 按键。
原版 Compet.exe 与原有文件保持不变。
1.本补丁是按照competexe进行制作的，理论上其他打字桌宠软件也适用，但请更改patsettingps1中的扫描文件夹。
2.本补丁适配xbox按钮，读取f13-f24，tab，esc，上下左右按键和小数字键盘的2468按键，如果其他打字桌宠软件不监听这些按钮，那么便无法实现，需要更改所有ps1和补丁包的json文件，对相应的按键进行修改。
3.先设置后启动，方能正常使用。直接启动vbs文件即可。

Start: Double-click Start-Compet-Xbox.bat. It will launch Compet and the Xbox bridge in the background without keeping an extra CMD window open.
Settings: Put these files in the same directory as the desktop pet software.Double-click GamepadSettings.bat. The settings window will automatically scan all desktop pet folders under _internalskins, allowing you to set Xbox buttons for each pet individually.
The original Compet.exe and original files remain unchanged.
1. This patch is made based on competexe and, in theory, can be used with other typing desktop pet software, but you need to change the scanned folders in patsettingps1.
2. This patch supports Xbox buttons, reading F13-F24, Tab, Esc, arrow keys, and the 2468 keys on the numeric keypad. If other typing desktop pet software doesn’t listen to these buttons, it won’t work. You would need to modify all ps1 scripts and the JSON files in the patch package to adjust the relevant keys.
3. Set up first, then start for it to work properly. You can also just run the VBS file directly.


【运行时补丁 / Runtime patches】
  启动器 CompetLauncher.exe 会在注入输入修正之外，按文件是否存在自动注入：
    CompetGifFix.dll    -> 让皮肤支持 GIF / WebP 动图
    CompetSoundFix.dll  -> 编号音效轮换（spam_01..spam_10）+ 修复切换后不出声
  删除对应的 DLL 即可关闭该补丁，不改动 Compet.exe 本体，重启即还原。

  音效用法：把同一句的多条音效命名为 前缀_编号.wav（如 spam_01.wav ... spam_10.wav），
  放进 _internal\assets\sounds\，然后在设置里选其中任意一条即可。
  打字时会在这组音效之间轮流播放。

  日志：注入结果写入 %USERPROFILE%\_compet_sound_fix.log（音效）、
        CompetGifFix.log（动图）。出错时另有 _compet_*_fix_error.log。

  Runtime patches: the launcher injects CompetGifFix.dll (GIF/WebP skins) and
  CompetSoundFix.dll (rotating numbered sounds + playback fix) when present.
  Sounds are grouped by the "name_NN.wav" pattern inside _internal\assets\sounds.
