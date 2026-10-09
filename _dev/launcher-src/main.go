package main

import (
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"syscall"
	"time"
	"unsafe"

	"golang.org/x/sys/windows"
)

// ── Windows API constants ──────────────────────────────────────────────

const (
	KEYEVENTF_KEYUP    = 0x0002
	KEYEVENTF_SCANCODE = 0x0008

	PROCESS_ALL_ACCESS = 0x1FFFFF
	MEM_COMMIT         = 0x00001000
	MEM_RESERVE        = 0x00002000
	MEM_RELEASE        = 0x8000
	PAGE_READWRITE     = 0x04

	SW_HIDE = 0
)

var (
	user32   = windows.NewLazySystemDLL("user32.dll")
	kernel32 = windows.NewLazySystemDLL("kernel32.dll")
	shell32  = windows.NewLazySystemDLL("shell32.dll")
	xinputDLL = windows.NewLazySystemDLL("xinput1_4.dll")

	procKeybdEvent          = user32.NewProc("keybd_event")
	procOpenProcess         = kernel32.NewProc("OpenProcess")
	procVirtualAllocEx      = kernel32.NewProc("VirtualAllocEx")
	procWriteProcessMemory  = kernel32.NewProc("WriteProcessMemory")
	procGetModuleHandle     = kernel32.NewProc("GetModuleHandleW")
	procGetProcAddress      = kernel32.NewProc("GetProcAddress")
	procCreateRemoteThread   = kernel32.NewProc("CreateRemoteThread")
	procWaitForSingleObject  = kernel32.NewProc("WaitForSingleObject")
	procVirtualFreeEx       = kernel32.NewProc("VirtualFreeEx")
	procCloseHandle         = kernel32.NewProc("CloseHandle")
	procShellExecute        = shell32.NewProc("ShellExecuteW")
	procXInputGetState      = xinputDLL.NewProc("XInputGetState")
)

// ── XInput types ──────────────────────────────────────────────────────────

type XInputGamepad struct {
	Buttons      uint16
	LeftTrigger  uint8
	RightTrigger uint8
	ThumbLX      int16
	ThumbLY      int16
	ThumbRX      int16
	ThumbRY      int16
}

type XInputState struct {
	PacketNumber uint32
	Gamepad      XInputGamepad
}

// ── JSON config types ──────────────────────────────────────────────────────

type Config struct {
	Version  int               `json:"version"`
	Mappings map[string]string `json:"mappings"`
}

// ── Virtual key codes ─────────────────────────────────────────────────────

var vkMap = map[string]byte{
	"F13": 0x7C, "F14": 0x7D, "F15": 0x7E, "F16": 0x7F,
	"F17": 0x80, "F18": 0x81, "F19": 0x82, "F20": 0x83,
	"F21": 0x84, "F22": 0x85, "F23": 0x86, "F24": 0x87,
	"W": 0x57, "A": 0x41, "S": 0x53, "D": 0x44,
	"UP": 0x26, "DOWN": 0x28, "LEFT": 0x25, "RIGHT": 0x27,
	"TAB": 0x09, "ESC": 0x1B,
}

var numpadScanMap = map[string]byte{
	"NUM8": 0x48, "NUM2": 0x50, "NUM4": 0x4B, "NUM6": 0x4D,
}

var wasdKeys = []string{"W", "A", "S", "D"}
var arrowKeys = []string{"UP", "DOWN", "LEFT", "RIGHT"}

var compositeTokens = map[string][]string{
	"WASD":   wasdKeys,
	"ARROWS": arrowKeys,
}

// Xbox button bitmasks
var buttonNames = map[string]uint16{
	"DPadUp":    0x0001,
	"DPadDown":  0x0002,
	"DPadLeft":  0x0004,
	"DPadRight": 0x0008,
	"Start":     0x0010,
	"Back":      0x0020,
	"LS":        0x0040,
	"RS":        0x0080,
	"LB":        0x0100,
	"RB":        0x0200,
	"A":         0x1000,
	"B":         0x2000,
	"X":         0x4000,
	"Y":         0x8000,
}

// ── Helpers ───────────────────────────────────────────────────────────────

func sendKey(vk byte, down bool) {
	flags := uintptr(0)
	if !down {
		flags = KEYEVENTF_KEYUP
	}
	procKeybdEvent.Call(uintptr(vk), 0, flags, 0)
}

func sendScanKey(scan byte, down bool) {
	flags := uintptr(KEYEVENTF_SCANCODE)
	if !down {
		flags |= KEYEVENTF_KEYUP
	}
	procKeybdEvent.Call(0, uintptr(scan), flags, 0)
}

func sendToken(token string, down bool) {
	if vk, ok := numpadScanMap[token]; ok {
		sendScanKey(vk, down)
		return
	}
	if vk, ok := vkMap[token]; ok {
		sendKey(vk, down)
	}
}

func sendComposite(tokens []string, down bool) {
	for _, t := range tokens {
		sendToken(t, down)
	}
}

// ── Config loader ─────────────────────────────────────────────────────────

func loadConfig(exeDir string) (*Config, error) {
	path := filepath.Join(exeDir, "gamepad_config.json")
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("cannot read %s: %w", path, err)
	}
	if len(data) >= 3 && data[0] == 0xEF && data[1] == 0xBB && data[2] == 0xBF {
		data = data[3:]
	}
	var cfg Config
	if err := json.Unmarshal(data, &cfg); err != nil {
		return nil, fmt.Errorf("cannot parse config: %w", err)
	}
	return &cfg, nil
}

// ── DLL injection ─────────────────────────────────────────────────────────

func injectDLL(pid uint32, dllPath string) error {
	dllPathUTF16, err := syscall.UTF16FromString(dllPath)
	if err != nil {
		return err
	}
	dllPathBytes := unsafe.Slice((*byte)(unsafe.Pointer(&dllPathUTF16[0])), len(dllPathUTF16)*2)

	hProc, _, _ := procOpenProcess.Call(PROCESS_ALL_ACCESS, 0, uintptr(pid))
	if hProc == 0 {
		return fmt.Errorf("OpenProcess failed (run as admin)")
	}
	defer procCloseHandle.Call(hProc)

	memCommitReserve := uintptr(MEM_COMMIT | MEM_RESERVE)
	mem, _, _ := procVirtualAllocEx.Call(hProc, 0, uintptr(len(dllPathBytes)), memCommitReserve, PAGE_READWRITE)
	if mem == 0 {
		return fmt.Errorf("VirtualAllocEx failed")
	}
	defer procVirtualFreeEx.Call(hProc, mem, 0, MEM_RELEASE)

	var written uintptr
	ok, _, _ := procWriteProcessMemory.Call(hProc, mem, uintptr(unsafe.Pointer(&dllPathBytes[0])), uintptr(len(dllPathBytes)), uintptr(unsafe.Pointer(&written)))
	if ok == 0 {
		return fmt.Errorf("WriteProcessMemory failed")
	}

	kernel32Name, _ := syscall.UTF16PtrFromString("kernel32.dll")
	k32, _, _ := procGetModuleHandle.Call(uintptr(unsafe.Pointer(kernel32Name)))
	if k32 == 0 {
		return fmt.Errorf("GetModuleHandle(kernel32.dll) failed")
	}

	funcName := []byte("LoadLibraryW")
	funcName = append(funcName, 0)
	loadLib, _, _ := procGetProcAddress.Call(k32, uintptr(unsafe.Pointer(&funcName[0])))
	if loadLib == 0 {
		return fmt.Errorf("GetProcAddress(LoadLibraryW) failed")
	}

	var tid uint32
	th, _, _ := procCreateRemoteThread.Call(hProc, 0, 0, loadLib, mem, 0, uintptr(unsafe.Pointer(&tid)))
	if th == 0 {
		return fmt.Errorf("CreateRemoteThread failed")
	}
	defer procCloseHandle.Call(th)
	procWaitForSingleObject.Call(th, 5000)
	return nil
}

// ── Run Compet.exe + inject ────────────────────────────────────────────────

func launchAndInject(exeDir string) error {
	exePath := filepath.Join(exeDir, "Compet.exe")
	dllPath := filepath.Join(exeDir, "CompetInputFix.dll")

	if _, err := os.Stat(dllPath); err != nil {
		return fmt.Errorf("CompetInputFix.dll not found: %w", err)
	}

	cmd := exec.Command(exePath)
	cmd.Dir = exeDir
	if err := cmd.Start(); err != nil {
		return fmt.Errorf("failed to start Compet.exe: %w", err)
	}

	pid := uint32(cmd.Process.Pid)

	time.Sleep(3 * time.Second)

	if err := injectDLL(pid, dllPath); err != nil {
		fmt.Printf("Warning: input-fix DLL injection failed: %v\n", err)
		fmt.Println("The app will still run, but keyboard/gamepad input fixes may not be active.")
	} else {
		fmt.Println("Compet input fix injected successfully.")
	}

	// Optional: animated-image (GIF / WebP) support.  Only injected when the
	// companion DLL is present, so deleting CompetGifFix.dll disables it.
	gifDLL := filepath.Join(exeDir, "CompetGifFix.dll")
	if _, statErr := os.Stat(gifDLL); statErr == nil {
		time.Sleep(2 * time.Second)
		if err := injectDLL(pid, gifDLL); err != nil {
			fmt.Printf("Warning: GIF-fix DLL injection failed: %v\n", err)
		} else {
			fmt.Println("Compet animated-image (GIF) support injected successfully.")
		}
	}

	return nil
}

// ── Elevation check ──────────────────────────────────────────────────────

func isAdmin() bool {
	var sid *windows.SID
	err := windows.AllocateAndInitializeSid(
		&windows.SECURITY_NT_AUTHORITY, 2,
		windows.SECURITY_BUILTIN_DOMAIN_RID,
		windows.DOMAIN_ALIAS_RID_ADMINS,
		0, 0, 0, 0, 0, 0,
		&sid,
	)
	if err != nil {
		return false
	}
	defer windows.FreeSid(sid)
	token := windows.GetCurrentProcessToken()
	isMember, err := token.IsMember(sid)
	return err == nil && isMember
}

func selfElevate() {
	exePath, _ := os.Executable()
	verb, _ := syscall.UTF16PtrFromString("runas")
	exe, _ := syscall.UTF16PtrFromString(exePath)
	procShellExecute.Call(0, uintptr(unsafe.Pointer(verb)), uintptr(unsafe.Pointer(exe)), 0, 0, SW_HIDE)
	os.Exit(0)
}

// ── Gamepad loop ────────────────────────────────────────────────────────

func gamepadLoop(cfg *Config) {
	mappings := cfg.Mappings

	// Track composite actions
	isComposite := make(map[string]bool)
	for gpBtn, token := range mappings {
		if _, ok := compositeTokens[token]; ok {
			isComposite[gpBtn] = true
		}
	}

	// Stick state
	lsH := 0
	lsV := 0

	const (
		LS_ENGAGE  = 12000
		LS_RELEASE = 7000
		RS_DEAD    = 12000
		TRIG_DEAD  = 30
	)

	lastButtons := make(map[string]bool)
	for name := range buttonNames {
		lastButtons[name] = false
	}
	lastLT := false
	lastRT := false

	// RS + LS last
	lastRS := map[string]bool{
		"RS_Left": false, "RS_Right": false,
		"RS_Up": false, "RS_Down": false,
	}
	lastLS := map[string]bool{
		"LS_Left": false, "LS_Right": false,
		"LS_Up": false, "LS_Down": false,
	}

	press := func(gpBtn string) {
		token := mappings[gpBtn]
		if comp, ok := compositeTokens[token]; ok {
			sendComposite(comp, true)
		} else {
			sendToken(token, true)
		}
	}
	release := func(gpBtn string) {
		token := mappings[gpBtn]
		if comp, ok := compositeTokens[token]; ok {
			sendComposite(comp, false)
		} else {
			sendToken(token, false)
		}
	}

	has := func(key string) bool {
		_, ok := mappings[key]
		return ok
	}

	for {
		connected := false
		var state XInputState
		for i := uintptr(0); i < 4; i++ {
			ret, _, _ := procXInputGetState.Call(i, uintptr(unsafe.Pointer(&state)))
			if ret == 0 {
				connected = true
				break
			}
		}

		if connected {
			b := state.Gamepad.Buttons

			// ── Digital buttons ──
			for name, mask := range buttonNames {
				down := (b & mask) != 0
				if lastButtons[name] != down {
					if _, ok := mappings[name]; ok {
						if down {
							press(name)
						} else {
							release(name)
						}
					}
					lastButtons[name] = down
				}
			}

			// ── LT ──
			ltDown := state.Gamepad.LeftTrigger >= TRIG_DEAD
			if lastLT != ltDown && has("LT") {
				if ltDown { press("LT") } else { release("LT") }
				lastLT = ltDown
			}

			// ── RT ──
			rtDown := state.Gamepad.RightTrigger >= TRIG_DEAD
			if lastRT != rtDown && has("RT") {
				if rtDown { press("RT") } else { release("RT") }
				lastRT = rtDown
			}

			// ── RS ──
			rx := state.Gamepad.ThumbRX
			ry := state.Gamepad.ThumbRY

			checkRS := func(dir string, cond bool) {
				if lastRS[dir] != cond && has(dir) {
					if cond { press(dir) } else { release(dir) }
					lastRS[dir] = cond
				}
			}
			checkRS("RS_Left", rx <= -RS_DEAD)
			checkRS("RS_Right", rx >= RS_DEAD)
			checkRS("RS_Down", ry <= -RS_DEAD)
			checkRS("RS_Up", ry >= RS_DEAD)

			// ── LS: horizontal ──
			lx := state.Gamepad.ThumbLX
			ly := state.Gamepad.ThumbLY

			switch lsH {
			case 0:
				if lx <= -LS_ENGAGE && has("LS_Left") {
					press("LS_Left"); lastLS["LS_Left"] = true; lsH = -1
				} else if lx >= LS_ENGAGE && has("LS_Right") {
					press("LS_Right"); lastLS["LS_Right"] = true; lsH = 1
				}
			case -1:
				if lx >= -LS_RELEASE {
					if has("LS_Left") { release("LS_Left") }
					lastLS["LS_Left"] = false; lsH = 0
				}
			case 1:
				if lx <= LS_RELEASE {
					if has("LS_Right") { release("LS_Right") }
					lastLS["LS_Right"] = false; lsH = 0
				}
			}

			// ── LS: vertical ──
			switch lsV {
			case 0:
				if ly <= -LS_ENGAGE && has("LS_Down") {
					press("LS_Down"); lastLS["LS_Down"] = true; lsV = -1
				} else if ly >= LS_ENGAGE && has("LS_Up") {
					press("LS_Up"); lastLS["LS_Up"] = true; lsV = 1
				}
			case -1:
				if ly >= -LS_RELEASE {
					if has("LS_Down") { release("LS_Down") }
					lastLS["LS_Down"] = false; lsV = 0
				}
			case 1:
				if ly <= LS_RELEASE {
					if has("LS_Up") { release("LS_Up") }
					lastLS["LS_Up"] = false; lsV = 0
				}
			}

		} else {
			// Controller disconnected — release all
			for name, held := range lastButtons {
				if held {
					if _, ok := mappings[name]; ok { release(name) }
					lastButtons[name] = false
				}
			}
			if lastLT && has("LT") { release("LT"); lastLT = false }
			if lastRT && has("RT") { release("RT"); lastRT = false }
			for dir, held := range lastRS {
				if held && has(dir) { release(dir); lastRS[dir] = false }
			}
			for dir, held := range lastLS {
				if held && has(dir) { release(dir); lastLS[dir] = false }
			}
			lsH, lsV = 0, 0
		}

		time.Sleep(12 * time.Millisecond)
	}
}

// ── Main ──────────────────────────────────────────────────────────────────

func main() {
	exeDir, _ := os.Executable()
	exeDir = filepath.Dir(exeDir)

	if !isAdmin() {
		selfElevate()
		return
	}

	fmt.Println("Compet Launcher v1.0 — Xbox Gamepad Edition")
	fmt.Println("============================================")

	cfg, err := loadConfig(exeDir)
	if err != nil {
		fmt.Printf("Config: %v (gamepad disabled)\n", err)
	}

	go func() {
		if err := launchAndInject(exeDir); err != nil {
			fmt.Printf("Launch error: %v\n", err)
			os.Exit(1)
		}
	}()

	time.Sleep(5 * time.Second)

	if cfg != nil {
		fmt.Println("Gamepad bridge active. Close this window to stop.")
		gamepadLoop(cfg)
	} else {
		fmt.Println("Press Ctrl+C to exit.")
		select {}
	}
}
