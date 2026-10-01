// NMOS for macOS (Phase 23 step 4): a menu-bar item that runs the services bundled inside the app.
//
// The app holds Python, PostgreSQL and the sidecar in Contents/Resources and starts nmos_launcher.py from there. It is
// read-only and sealed by its (ad hoc) signature, so the data, the .env and the log live in
// ~/Library/Application Support/NMOS (PHASE-23 Q3). Build: swiftc -O NMOSApp.swift -o NMOS (see build_bundle.py).
import AppKit
import ServiceManagement

let resources = Bundle.main.resourceURL!
let support = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
    .appendingPathComponent("NMOS", isDirectory: true)
let logURL = support.appendingPathComponent("nmos.log")

func readEnv(_ url: URL) -> [String: String] {
    guard let text = try? String(contentsOf: url, encoding: .utf8) else { return [:] }
    var env: [String: String] = [:]
    for raw in text.split(whereSeparator: \.isNewline) {
        let line = raw.trimmingCharacters(in: .whitespaces)
        guard !line.hasPrefix("#"), let eq = line.firstIndex(of: "=") else { continue }
        let key = line[..<eq].trimmingCharacters(in: .whitespaces)
        let value = line[line.index(after: eq)...].trimmingCharacters(in: .whitespaces)
            .trimmingCharacters(in: CharacterSet(charactersIn: "\"'"))
        env[key] = value
    }
    return env
}

/// The plugin's icon (adapters/pocketrisu-plugin/src/icon.ts: "M6 19V5l12 14V9.5" and a dot at 18,5.5) as a template
/// image, so the menu bar tints it for light and dark.
func glyph() -> NSImage {
    let image = NSImage(size: NSSize(width: 18, height: 18), flipped: true) { rect in
        let s = rect.width / 24
        let path = NSBezierPath()
        path.lineWidth = 2 * s
        path.lineCapStyle = .round
        path.lineJoinStyle = .round
        path.move(to: NSPoint(x: 6 * s, y: 19 * s))
        path.line(to: NSPoint(x: 6 * s, y: 5 * s))
        path.line(to: NSPoint(x: 18 * s, y: 19 * s))
        path.line(to: NSPoint(x: 18 * s, y: 9.5 * s))
        NSColor.black.setStroke()
        path.stroke()
        let r = 1.9 * s
        NSColor.black.setFill()
        NSBezierPath(ovalIn: NSRect(x: 18 * s - r, y: 5.5 * s - r, width: 2 * r, height: 2 * r)).fill()
        return true
    }
    image.isTemplate = true
    return image
}

/// The log opened for appending (O_APPEND): every write lands at the end, whoever writes. A handle that only seeks to
/// the end once keeps its own offset, and the launcher's output then overwrote the app's own lines.
func appendHandle() -> FileHandle? {
    let fd = open(logURL.path, O_WRONLY | O_APPEND | O_CREAT, 0o600)
    return fd < 0 ? nil : FileHandle(fileDescriptor: fd, closeOnDealloc: true)
}

func alert(_ text: String) {
    NSApp.activate(ignoringOtherApps: true)
    let a = NSAlert()
    a.messageText = "NMOS"
    a.informativeText = text
    a.runModal()
}

/// The launcher's last lines, where a refusal (newer data, a port in use, already running) says what to do.
func lastLog(_ lines: Int = 6) -> String {
    guard let text = try? String(contentsOf: logURL, encoding: .utf8) else { return "" }
    let mine = text.split(whereSeparator: \.isNewline).filter { $0.hasPrefix("[nmos]") }
    return mine.suffix(lines).joined(separator: "\n")
}

final class AppDelegate: NSObject, NSApplicationDelegate, NSMenuItemValidation {
    var item: NSStatusItem!
    var statusLine: NSMenuItem!
    var loginLine: NSMenuItem!
    var launcher: Process?
    var state = "starting"  // starting | running | stopped | failed | stopping
    var timer: Timer?
    var url = "http://127.0.0.1:8790"
    var token: String?  // NMOS_AUTH_TOKEN: /v1/health asks for it like every endpoint

    func applicationDidFinishLaunching(_ notification: Notification) {
        let me = Bundle.main.bundleIdentifier ?? ""
        if NSRunningApplication.runningApplications(withBundleIdentifier: me).count > 1 {
            alert("NMOS가 이미 실행 중이에요. 메뉴 막대의 NMOS 아이콘을 확인해 주세요.")
            NSApp.terminate(nil)
            return
        }
        try? FileManager.default.createDirectory(at: support, withIntermediateDirectories: true,
                                                 attributes: [.posixPermissions: 0o700])
        let env = readEnv(support.appendingPathComponent(".env"))
        url = "http://\(env["NMOS_SIDECAR_BIND"] ?? "127.0.0.1"):\(env["NMOS_SIDECAR_PORT"] ?? "8790")"
        token = env["NMOS_AUTH_TOKEN"].flatMap { $0.isEmpty ? nil : $0 }
        copyPlugin()
        buildMenu()
        start()
        timer = Timer.scheduledTimer(withTimeInterval: 2, repeats: true) { [weak self] _ in self?.poll() }
    }

    /// The plugin file outside the app, where a browser's file dialog can reach it.
    func copyPlugin() {
        let dir = support.appendingPathComponent("plugin", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let dest = dir.appendingPathComponent("nmos-pocketrisu.js")
        try? FileManager.default.removeItem(at: dest)
        try? FileManager.default.copyItem(at: resources.appendingPathComponent("plugin/nmos-pocketrisu.js"), to: dest)
    }

    func buildMenu() {
        item = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        item.button?.image = glyph()
        item.button?.toolTip = "NMOS"
        let menu = NSMenu()
        statusLine = NSMenuItem(title: "NMOS: 시작하는 중…", action: nil, keyEquivalent: "")
        statusLine.isEnabled = false
        menu.addItem(statusLine)
        menu.addItem(.separator())
        menu.addItem(withTitle: "대시보드 열기", action: #selector(openDashboard), keyEquivalent: "").target = self
        menu.addItem(withTitle: "사이드카 주소 복사", action: #selector(copyURL), keyEquivalent: "").target = self
        menu.addItem(withTitle: "플러그인 파일 위치 열기", action: #selector(openPlugin), keyEquivalent: "").target = self
        menu.addItem(withTitle: "로그 폴더 열기", action: #selector(openLogs), keyEquivalent: "").target = self
        menu.addItem(.separator())
        loginLine = NSMenuItem(title: "로그인 시 NMOS 실행", action: #selector(toggleLogin), keyEquivalent: "")
        loginLine.target = self
        menu.addItem(loginLine)
        menu.addItem(.separator())
        menu.addItem(withTitle: "NMOS 종료", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        item.menu = menu
        refresh()
    }

    /// State changes go to the log too, which is where support (and the CI smoke) can see what the menu shows.
    func setState(_ new: String) {
        state = new
        appendHandle()?.write("[app] state: \(new)\n".data(using: .utf8)!)
        refresh()
    }

    func refresh() {
        let text = ["starting": "시작하는 중…", "running": "실행 중 — \(url)", "stopped": "멈춤 — 로그를 확인해 주세요",
                    "failed": "시작 실패 — 로그를 확인해 주세요", "stopping": "끄는 중…"][state] ?? state
        statusLine.title = "NMOS: \(text)"
        item.button?.appearsDisabled = state != "running"
        loginLine.state = SMAppService.mainApp.status == .enabled ? .on : .off
    }

    func start() {
        let p = Process()
        p.executableURL = resources.appendingPathComponent("python/bin/python3")
        p.arguments = [resources.appendingPathComponent("nmos_launcher.py").path]
        var env = ProcessInfo.processInfo.environment
        env["NMOS_DATA_DIR"] = support.path
        env["NMOS_ENV_FILE"] = support.appendingPathComponent(".env").path
        env["PYTHONUTF8"] = "1"
        env["PYTHONDONTWRITEBYTECODE"] = "1"  // the app is sealed: nothing is written inside it
        p.environment = env
        if let h = appendHandle() {
            p.standardOutput = h
            p.standardError = h
        }
        p.terminationHandler = { proc in
            DispatchQueue.main.async { self.exited(proc.terminationStatus) }
        }
        do {
            try p.run()
            launcher = p
        } catch {
            state = "failed"
            refresh()
            alert("NMOS를 시작할 수 없어요: \(error.localizedDescription)")
        }
    }

    func exited(_ code: Int32) {
        if state == "stopping" { return }
        let wasRunning = state == "running"
        setState(wasRunning ? "stopped" : "failed")
        alert(wasRunning ? "NMOS의 서비스가 멈췄어요. 메뉴의 '로그 폴더 열기'에서 nmos.log를 확인해 주세요."
                         : "NMOS를 시작하지 못했어요.\n\n\(lastLog())")
    }

    func poll() {
        guard state == "starting" || state == "running", let health = URL(string: url + "/v1/health") else { return }
        var request = URLRequest(url: health)
        request.timeoutInterval = 1.5
        if let token { request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
        URLSession.shared.dataTask(with: request) { data, _, _ in
            let ok = data.flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: Any] }?["ok"] as? Bool ?? false
            DispatchQueue.main.async {
                if ok && self.state == "starting" { self.setState("running") }
                self.refresh()
            }
        }.resume()
    }

    /// The Inspector's first page (PHASE-23 Q8), with the token when one is set (the page asks for it).
    /// Only RFC 3986 unreserved characters stay as they are: `&`, `=` and `+` (a space to the server) are escaped.
    @objc func openDashboard() {
        var page = url + "/dashboard"
        let unreserved = CharacterSet(charactersIn: "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")
        if let token, let q = token.addingPercentEncoding(withAllowedCharacters: unreserved) {
            page += "?token=\(q)"
        }
        if let target = URL(string: page) { NSWorkspace.shared.open(target) }
    }

    /// The menu enables items itself (autoenablesItems); the dashboard waits until NMOS answers, like the Windows tray.
    func validateMenuItem(_ menuItem: NSMenuItem) -> Bool {
        menuItem.action != #selector(openDashboard) || state == "running"
    }

    @objc func copyURL() {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(url, forType: .string)
    }

    @objc func openPlugin() {
        NSWorkspace.shared.activateFileViewerSelecting([support.appendingPathComponent("plugin/nmos-pocketrisu.js")])
    }

    @objc func openLogs() {
        NSWorkspace.shared.open(support)
    }

    @objc func toggleLogin() {
        do {
            if SMAppService.mainApp.status == .enabled {
                try SMAppService.mainApp.unregister()
            } else {
                try SMAppService.mainApp.register()
            }
        } catch {
            alert("로그인 시 실행 설정을 바꾸지 못했어요.\n\n\(error.localizedDescription)\n\n"
                  + "NMOS.app을 응용 프로그램 폴더로 옮긴 뒤 다시 해 주세요.")
        }
        if SMAppService.mainApp.status == .requiresApproval { SMAppService.openSystemSettingsLoginItems() }
        refresh()
    }

    /// Quit, sign-out or shut-down: stop the launcher (SIGINT: it stops the sidecar, the worker and PostgreSQL) first.
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        guard let p = launcher, p.isRunning else { return .terminateNow }
        setState("stopping")
        p.interrupt()
        DispatchQueue.global().async {
            let deadline = Date().addingTimeInterval(60)
            while p.isRunning && Date() < deadline { Thread.sleep(forTimeInterval: 0.2) }
            if p.isRunning { p.terminate() }
            DispatchQueue.main.async { NSApp.reply(toApplicationShouldTerminate: true) }
        }
        return .terminateLater
    }
}

// `NMOS --login-item on|off|status`: the menu's login-item switch without the menu (CI, support).
if let i = CommandLine.arguments.firstIndex(of: "--login-item") {
    let what = CommandLine.arguments.count > i + 1 ? CommandLine.arguments[i + 1] : "status"
    do {
        if what == "on" { try SMAppService.mainApp.register() }
        if what == "off" { try SMAppService.mainApp.unregister() }
    } catch {
        print("error: \(error.localizedDescription)")
    }
    let names: [SMAppService.Status: String] = [.notRegistered: "notRegistered", .enabled: "enabled",
                                                .requiresApproval: "requiresApproval", .notFound: "notFound"]
    print(names[SMAppService.mainApp.status] ?? "unknown")
    exit(0)
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.accessory)
app.run()
