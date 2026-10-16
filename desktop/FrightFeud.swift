import AppKit
import Foundation
import Darwin

// Keep the browser handoff narrower than a general URL opener.
func gameURL(_ raw: String) -> URL? {
    guard let parts = URLComponents(string: raw), parts.scheme == "http",
          let host = parts.host?.lowercased(),
          host == "localhost" || host == "127.0.0.1" || host.hasSuffix(".localhost"),
          let port = parts.port, (1...65535).contains(port),
          parts.user == nil, parts.password == nil,
          parts.percentEncodedPath == "/apps/fright-feud/",
          parts.query == nil else { return nil }
    if let fragment = parts.percentEncodedFragment {
        guard fragment.range(of: "^(atrium_state_token|ff_board)=[A-Za-z0-9_-]+$", options: .regularExpression) != nil else { return nil }
    }
    return parts.url
}

final class Launcher: NSObject, NSApplicationDelegate {
    let headless: Bool
    let forwarded: [String]
    let resources: URL
    let home: String
    var window: NSWindow?
    var status: NSTextField?
    var spinner: NSProgressIndicator?
    var process: Process?
    var timedOut = false
    var finished = false

    init(headless: Bool, forwarded: [String], resources: URL, home: String) {
        self.headless = headless
        self.forwarded = forwarded
        self.resources = resources
        self.home = home
        super.init()
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        if !headless { showWindow() }
        DispatchQueue.global(qos: .userInitiated).async { self.launchCoordinator() }
    }

    func showWindow() {
        let panel = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 460, height: 150), styleMask: [.titled, .closable], backing: .buffered, defer: false)
        panel.title = "Fright Feud"
        panel.center()
        panel.isReleasedWhenClosed = false
        let label = NSTextField(wrappingLabelWithString: "Getting Fright Feud ready…")
        label.frame = NSRect(x: 65, y: 42, width: 365, height: 65)
        label.font = NSFont.systemFont(ofSize: 15)
        let progress = NSProgressIndicator(frame: NSRect(x: 24, y: 62, width: 24, height: 24))
        progress.style = .spinning
        progress.startAnimation(nil)
        panel.contentView?.addSubview(label)
        panel.contentView?.addSubview(progress)
        self.status = label
        self.spinner = progress
        self.window = panel
        panel.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    func fail(_ message: String) {
        guard !finished else { return }
        finished = true
        spinner?.stopAnimation(nil)
        let guidance = "See \(home)/Library/Application Support/Fright Feud for logs."
        if headless {
            let event = ["event": "error", "message": "\(message)\n\(guidance)"]
            if let data = try? JSONSerialization.data(withJSONObject: event), var text = String(data: data, encoding: .utf8) {
                text += "\n"
                FileHandle.standardOutput.write(Data(text.utf8))
            }
            exit(1)
        }
        status?.stringValue = "Fright Feud could not start."
        let alert = NSAlert()
        alert.messageText = "Fright Feud could not start"
        alert.informativeText = "\(message)\n\n\(guidance)\nYou can reopen Fright Feud to try again."
        alert.alertStyle = .warning
        alert.addButton(withTitle: "Close")
        alert.runModal()
        NSApp.terminate(nil)
    }

    func launchCoordinator() {
        #if arch(arm64)
        let architecture = "arm64"
        #else
        let architecture = "x86_64"
        #endif
        let task = Process()
        let output = Pipe()
        let errors = Pipe()
        task.executableURL = resources.appendingPathComponent("runtimes/\(architecture)/python/bin/python3.12")
        task.arguments = ["-I", "-B", resources.appendingPathComponent("launcher.py").path, "--resources", resources.path, "--bundle", Bundle.main.bundleURL.path] + forwarded
        task.standardOutput = output
        task.standardError = errors
        task.standardInput = FileHandle.nullDevice
        var environment = ProcessInfo.processInfo.environment
        // Avoid injecting Python configuration from the launching shell.
        for key in environment.keys where key.hasPrefix("PYTHON") { environment.removeValue(forKey: key) }
        task.environment = environment
        let stderrLock = NSLock()
        var stderrTail = Data()
        errors.fileHandleForReading.readabilityHandler = { handle in
            let data = handle.availableData
            stderrLock.lock()
            stderrTail.append(data)
            if stderrTail.count > 8192 { stderrTail = Data(stderrTail.suffix(8192)) }
            stderrLock.unlock()
        }
        do { try task.run() } catch {
            errors.fileHandleForReading.readabilityHandler = nil
            DispatchQueue.main.async { self.fail("The bundled Python runtime could not start: \(error.localizedDescription)") }
            return
        }
        DispatchQueue.main.async {
            self.process = task
            DispatchQueue.main.asyncAfter(deadline: .now() + 150) {
                guard !self.finished, task.isRunning else { return }
                self.timedOut = true
                task.terminate()
                DispatchQueue.main.asyncAfter(deadline: .now() + 2) {
                    if task.isRunning { kill(task.processIdentifier, SIGKILL) }
                }
            }
        }
        var pending = Data()
        var ready: URL?
        var failure: String?
        var total = 0
        func consume(_ line: Data) {
            guard !line.isEmpty else { return }
            guard let event = try? JSONSerialization.jsonObject(with: line) as? [String: Any], let kind = event["event"] as? String else {
                failure = "The launcher returned an unreadable response."
                return
            }
            switch kind {
            case "status":
                if let message = event["message"] as? String {
                    DispatchQueue.main.async { self.status?.stringValue = String(message.prefix(500)) }
                }
            case "error": failure = event["message"] as? String ?? "The engine could not start."
            case "ready":
                guard let raw = event["url"] as? String, let url = gameURL(raw) else {
                    failure = "The engine returned an unsafe game address."
                    return
                }
                ready = url
            default: failure = "The launcher returned an unknown response."
            }
            if headless {
                FileHandle.standardOutput.write(line)
                FileHandle.standardOutput.write(Data([10]))
            }
        }
        while true {
            let chunk = output.fileHandleForReading.availableData
            if chunk.isEmpty { break }
            total += chunk.count
            if total > 262144 {
                failure = "The launcher produced too much output."
                if task.isRunning { task.terminate() }
                continue
            }
            pending.append(chunk)
            while let newline = pending.firstIndex(of: 10) {
                consume(Data(pending[..<newline]))
                pending.removeSubrange(...newline)
            }
        }
        if !pending.isEmpty { consume(pending) }
        task.waitUntilExit()
        errors.fileHandleForReading.readabilityHandler = nil
        stderrLock.lock()
        let diagnostic = String(data: stderrTail, encoding: .utf8) ?? ""
        stderrLock.unlock()
        DispatchQueue.main.async {
            if self.timedOut {
                self.fail("Starting Fright Feud took too long. Please reopen the app.")
            } else if let error = failure {
                self.fail(error)
            } else if task.terminationStatus != 0 || ready == nil {
                let detail = diagnostic.isEmpty ? "The launcher exited without a game address." : String(diagnostic.suffix(2000))
                self.fail(detail)
            } else if let url = ready {
                self.spinner?.stopAnimation(nil)
                if self.headless { exit(0) }
                if NSWorkspace.shared.open(url) {
                    self.finished = true
                    NSApp.terminate(nil)
                } else {
                    self.fail("The browser could not open \(url.absoluteString).")
                }
            }
        }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }

    func applicationWillTerminate(_ notification: Notification) {
        // This is only the short-lived coordinator, never a previously running engine.
        if let task = process, task.isRunning { task.terminate() }
    }
}

let arguments = Array(CommandLine.arguments.dropFirst())
if arguments.first == "--validate-url" {
    exit(arguments.count == 2 && gameURL(arguments[1]) != nil ? 0 : 1)
}
var headless = false
var forwarded: [String] = []
var home = FileManager.default.homeDirectoryForCurrentUser.path
var resources = Bundle.main.resourceURL ?? Bundle.main.bundleURL.appendingPathComponent("Contents/Resources")
var index = 0
while index < arguments.count {
    let argument = arguments[index]
    if argument == "--headless" { headless = true }
    else if ["--home", "--port", "--resources"].contains(argument), index + 1 < arguments.count {
        index += 1
        let value = arguments[index]
        if argument == "--resources" { resources = URL(fileURLWithPath: value) }
        else {
            if argument == "--home" { home = value }
            forwarded.append(contentsOf: [argument, value])
        }
    } else if !argument.hasPrefix("-psn_") {
        fputs("Unsupported launcher argument: \(argument)\n", stderr)
        exit(2)
    }
    index += 1
}
let application = NSApplication.shared
application.setActivationPolicy(headless ? .prohibited : .regular)
let delegate = Launcher(headless: headless, forwarded: forwarded, resources: resources, home: home)
application.delegate = delegate
application.run()
