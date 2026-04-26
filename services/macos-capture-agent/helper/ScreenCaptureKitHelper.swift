import AppKit
import AudioToolbox
import AVFoundation
import CoreAudio
import CoreMedia
import Darwin
import Foundation
import ScreenCaptureKit

private let thirdeyeBundleIdentifier = "com.thirdeye.desktop"
private let thirdeyeApplicationName = "thirdeye"
private let ignoredWindowOwnerNames: Set<String> = [
    "control center",
    "dock",
    "notification center",
    "wallpaper",
    "window server",
    "systemuiserver",
]
private let ignoredWindowTitleFragments = [
    "(control center)",
    "backstop",
    "menubar",
    "offscreen wallpaper window",
    "item-0",
]

private func isThirdeyeApplication(bundleIdentifier: String?, applicationName: String?) -> Bool {
    if bundleIdentifier == thirdeyeBundleIdentifier {
        return true
    }
    return applicationName?.lowercased() == thirdeyeApplicationName
}

private func isThirdeyeApplication(_ application: SCRunningApplication) -> Bool {
    isThirdeyeApplication(bundleIdentifier: application.bundleIdentifier, applicationName: application.applicationName)
}

private func isThirdeyeApplication(_ application: SCRunningApplication?) -> Bool {
    guard let application else {
        return false
    }
    return isThirdeyeApplication(application)
}

private func isReliableThirdeyeApplicationExclusion(_ application: SCRunningApplication) -> Bool {
    application.bundleIdentifier == thirdeyeBundleIdentifier
}

private func isThirdeyeWindowException(_ window: SCWindow) -> Bool {
    guard let application = window.owningApplication,
          isThirdeyeApplication(application) else {
        return false
    }
    return !isReliableThirdeyeApplicationExclusion(application)
}

private func isUserSelectableWindow(_ window: SCWindow) -> Bool {
    guard window.frame.width >= 120,
          window.frame.height >= 80,
          let application = window.owningApplication,
          !isThirdeyeApplication(application) else {
        return false
    }

    let appName = application.applicationName.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    if appName.isEmpty || ignoredWindowOwnerNames.contains(appName) {
        return false
    }

    let title = (window.title ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
    guard !title.isEmpty else {
        return false
    }

    let normalizedTitle = title.lowercased()
    if appName == "finder" && normalizedTitle == "finder" {
        return false
    }
    return !ignoredWindowTitleFragments.contains { normalizedTitle.contains($0) }
}

struct CaptureTarget: Codable {
    let id: String
    let kind: String
    let label: String
    let app_bundle_id: String?
    let app_name: String?
    let app_pid: Int32?
    let window_id: String?
    let display_id: String?
}

enum HelperError: LocalizedError {
    case invalidArguments(String)
    case unsupportedTarget(String)
    case missingDisplay
    case missingApplication
    case missingWindow
    case permissionDenied
    case systemAudioPermissionDenied(String)
    case mutedCaptureUnsupported
    case missingApplicationProcess
    case invalidAudioBuffer
    case writerFailed(String)
    case protectedApplication

    var errorDescription: String? {
        switch self {
        case .invalidArguments(let message):
            return message
        case .unsupportedTarget(let target):
            return "unsupported capture target: \(target)"
        case .missingDisplay:
            return "display target could not be resolved"
        case .missingApplication:
            return "application target could not be resolved"
        case .missingWindow:
            return "window target could not be resolved"
        case .permissionDenied:
            return "screen_recording_permission_denied"
        case .systemAudioPermissionDenied(let detail):
            return "system_audio_recording_permission_denied: \(detail)"
        case .mutedCaptureUnsupported:
            return "muted app audio capture requires macOS 14.2 or newer"
        case .missingApplicationProcess:
            return "this app's audio cannot be muted yet because no supported audio process was found"
        case .invalidAudioBuffer:
            return "live audio sample could not be converted"
        case .writerFailed(let message):
            return message
        case .protectedApplication:
            return "thirdeye cannot be recorded"
        }
    }
}

enum HelperCommand {
    case targets
    case record(
        outputFile: URL,
        recordsAudio: Bool,
        liveAudioFifoPath: URL?,
        stopFile: URL?,
        muteCommandFile: URL?,
        muteStateFile: URL?,
        target: CaptureTarget,
        muteTargetAudio: Bool
    )
    case liveAudio(
        fifoPath: URL,
        stopFile: URL?,
        muteCommandFile: URL?,
        muteStateFile: URL?,
        target: CaptureTarget,
        muteTargetAudio: Bool
    )

    static func parse(arguments: [String]) throws -> HelperCommand {
        guard arguments.count >= 2 else {
            throw HelperError.invalidArguments("usage: macos_capture_helper <targets|record|live-audio> [options]")
        }

        let command = arguments[1]
        switch command {
        case "targets":
            return .targets
        case "record":
            return .record(
                outputFile: URL(fileURLWithPath: try value(named: "--output-file", in: arguments)),
                recordsAudio: !arguments.contains("--video-only"),
                liveAudioFifoPath: optionalValue(named: "--fifo-path", in: arguments).map { URL(fileURLWithPath: $0) },
                stopFile: optionalValue(named: "--stop-file", in: arguments).map { URL(fileURLWithPath: $0) },
                muteCommandFile: optionalValue(named: "--mute-command-file", in: arguments).map { URL(fileURLWithPath: $0) },
                muteStateFile: optionalValue(named: "--mute-state-file", in: arguments).map { URL(fileURLWithPath: $0) },
                target: try parseTarget(arguments: arguments),
                muteTargetAudio: arguments.contains("--mute-target-audio")
            )
        case "live-audio":
            return .liveAudio(
                fifoPath: URL(fileURLWithPath: try value(named: "--fifo-path", in: arguments)),
                stopFile: optionalValue(named: "--stop-file", in: arguments).map { URL(fileURLWithPath: $0) },
                muteCommandFile: optionalValue(named: "--mute-command-file", in: arguments).map { URL(fileURLWithPath: $0) },
                muteStateFile: optionalValue(named: "--mute-state-file", in: arguments).map { URL(fileURLWithPath: $0) },
                target: try parseTarget(arguments: arguments),
                muteTargetAudio: arguments.contains("--mute-target-audio")
            )
        default:
            throw HelperError.invalidArguments("unknown command: \(command)")
        }
    }

    private static func parseTarget(arguments: [String]) throws -> CaptureTarget {
        let raw = try value(named: "--target-json", in: arguments)
        let data = Data(raw.utf8)
        return try JSONDecoder().decode(CaptureTarget.self, from: data)
    }

    private static func value(named flag: String, in arguments: [String]) throws -> String {
        guard let index = arguments.firstIndex(of: flag), index + 1 < arguments.count else {
            throw HelperError.invalidArguments("missing required argument: \(flag)")
        }
        return arguments[index + 1]
    }

    private static func optionalValue(named flag: String, in arguments: [String]) -> String? {
        guard let index = arguments.firstIndex(of: flag), index + 1 < arguments.count else {
            return nil
        }
        return arguments[index + 1]
    }
}

struct MuteCommand: Codable {
    let id: String
    let mute_target_audio: Bool
}

struct MuteCommandState: Codable {
    let id: String
    let ok: Bool
    let mute_target_audio: Bool
    let error: String?
}

struct ResolvedTarget {
    let filter: SCContentFilter
    let width: Int
    let height: Int
    let appProcessID: pid_t?
}

enum CaptureMode {
    case record(outputFile: URL, recordsAudio: Bool, liveAudioFifoPath: URL?, muteTargetAudio: Bool)
    case liveAudio(fifoPath: URL, muteTargetAudio: Bool)

    var muteTargetAudio: Bool {
        switch self {
        case .record(_, _, _, let muteTargetAudio):
            return muteTargetAudio
        case .liveAudio(_, let muteTargetAudio):
            return muteTargetAudio
        }
    }
}

fileprivate struct CapturedTapAudio {
    let format: AVAudioFormat
    let buffers: [Data]
    let frameCount: AVAudioFrameCount
}

final class ProcessTapAudioCapture {
    private let processID: pid_t
    private let bundleID: String?
    private let appName: String?
    private let outputQueue: DispatchQueue
    private let onAudio: (CapturedTapAudio) -> Void
    private var tapID = AudioObjectID(kAudioObjectUnknown)
    private var aggregateDeviceID = AudioObjectID(kAudioObjectUnknown)
    private var ioProcID: AudioDeviceIOProcID?
    private var tapFormat: AVAudioFormat?

    fileprivate init(processID: pid_t, bundleID: String?, appName: String?, outputQueue: DispatchQueue, onAudio: @escaping (CapturedTapAudio) -> Void) {
        self.processID = processID
        self.bundleID = bundleID
        self.appName = appName
        self.outputQueue = outputQueue
        self.onAudio = onAudio
    }

    func start() throws {
        guard ProcessInfo.processInfo.isOperatingSystemAtLeast(
            OperatingSystemVersion(majorVersion: 14, minorVersion: 2, patchVersion: 0)
        ) else {
            throw HelperError.mutedCaptureUnsupported
        }

        let relatedAudioOwnerProcessIDs = Self.relatedAudioOwnerProcessIDs(bundleID: bundleID, appName: appName, rootProcessID: processID)
        let processIDs = Self.uniqueProcessIDs(
            Self.processTreeProcessIDs(rootedAt: processID) + Self.appBundleProcessIDs(rootedAt: processID) + relatedAudioOwnerProcessIDs
        )
        let processObjectIDs = Self.audioProcessObjectIDs(for: processIDs)
        guard !processObjectIDs.isEmpty else {
            throw HelperError.missingApplicationProcess
        }

        let tapDescription = CATapDescription(stereoMixdownOfProcesses: processObjectIDs)
        tapDescription.name = "thirdeye muted app audio"
        tapDescription.isPrivate = true
        tapDescription.muteBehavior = CATapMuteBehavior.muted
        let tapBundleIDs = Self.tapBundleIDs(for: bundleID, appName: appName, rootProcessID: processID)
        if #available(macOS 26.0, *) {
            if !tapBundleIDs.isEmpty {
                tapDescription.bundleIDs = tapBundleIDs
                tapDescription.isProcessRestoreEnabled = true
            }
        }
        fputs(
            "muted app audio tap target_pid=\(processID) app_bundle_id=\(bundleID ?? "") app_name=\(appName ?? "") pids=\(processIDs.map(String.init).joined(separator: ",")) bundle_ids=\(tapBundleIDs.joined(separator: ",")) matching HAL audio driver pids=\(relatedAudioOwnerProcessIDs.map(String.init).joined(separator: ","))\n",
            stderr
        )

        var newTapID = AudioObjectID(kAudioObjectUnknown)
        var status = AudioHardwareCreateProcessTap(tapDescription, &newTapID)
        guard status == noErr else {
            throw HelperError.systemAudioPermissionDenied(Self.describe(status: status))
        }
        tapID = newTapID

        do {
            tapFormat = try Self.audioFormat(forTap: tapID)
            aggregateDeviceID = try Self.createAggregateDevice(for: tapDescription)
            try createIOProc()
            status = AudioDeviceStart(aggregateDeviceID, ioProcID)
            guard status == noErr else {
                throw HelperError.writerFailed("failed to start muted app audio tap: \(Self.describe(status: status))")
            }
        } catch {
            stop()
            throw error
        }
    }

    func stop() {
        if aggregateDeviceID != AudioObjectID(kAudioObjectUnknown), let ioProcID {
            AudioDeviceStop(aggregateDeviceID, ioProcID)
            AudioDeviceDestroyIOProcID(aggregateDeviceID, ioProcID)
            self.ioProcID = nil
        }
        if aggregateDeviceID != AudioObjectID(kAudioObjectUnknown) {
            AudioHardwareDestroyAggregateDevice(aggregateDeviceID)
            aggregateDeviceID = AudioObjectID(kAudioObjectUnknown)
        }
        if tapID != AudioObjectID(kAudioObjectUnknown) {
            AudioHardwareDestroyProcessTap(tapID)
            tapID = AudioObjectID(kAudioObjectUnknown)
        }
    }

    private func createIOProc() throws {
        var newIOProcID: AudioDeviceIOProcID?
        let queue = outputQueue
        let status = AudioDeviceCreateIOProcIDWithBlock(&newIOProcID, aggregateDeviceID, nil) { [weak self] _, inputData, _, _, _ in
            guard let self,
                  let format = self.tapFormat else {
                return
            }
            let captured = Self.copyAudio(inputData, format: format)
            guard captured.frameCount > 0 else {
                return
            }
            queue.async {
                self.onAudio(captured)
            }
        }
        guard status == noErr, let newIOProcID else {
            throw HelperError.writerFailed("failed to create muted app audio reader: \(Self.describe(status: status))")
        }
        ioProcID = newIOProcID
    }

    private static func audioProcessObjectIDs(for processIDs: [pid_t]) -> [AudioObjectID] {
        var seen = Set<AudioObjectID>()
        var objectIDs: [AudioObjectID] = []
        for processID in processIDs {
            guard let objectID = audioProcessObjectID(for: processID),
                  !seen.contains(objectID) else {
                continue
            }
            seen.insert(objectID)
            objectIDs.append(objectID)
        }
        return objectIDs
    }

    private static func audioProcessObjectID(for processID: pid_t) -> AudioObjectID? {
        var address = AudioObjectPropertyAddress(
            mSelector: kAudioHardwarePropertyTranslatePIDToProcessObject,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )
        var pid = processID
        var objectID = AudioObjectID(kAudioObjectUnknown)
        var dataSize = UInt32(MemoryLayout<AudioObjectID>.size)
        let status = withUnsafePointer(to: &pid) { pidPointer in
            withUnsafeMutablePointer(to: &objectID) { objectPointer in
                AudioObjectGetPropertyData(
                    AudioObjectID(kAudioObjectSystemObject),
                    &address,
                    UInt32(MemoryLayout<pid_t>.size),
                    pidPointer,
                    &dataSize,
                    objectPointer
                )
            }
        }
        return status == noErr && objectID != AudioObjectID(kAudioObjectUnknown) ? objectID : nil
    }

    private static func uniqueProcessIDs(_ processIDs: [pid_t]) -> [pid_t] {
        var seen = Set<pid_t>()
        var ordered: [pid_t] = []
        for processID in processIDs where processID > 0 && !seen.contains(processID) {
            seen.insert(processID)
            ordered.append(processID)
        }
        return ordered
    }

    private static func allProcessIDs() -> [pid_t] {
        let processCount = proc_listallpids(nil, 0)
        guard processCount > 0 else {
            return []
        }

        let capacity = Int(processCount) + 256
        var processIDs = [pid_t](repeating: 0, count: capacity)
        let actualCount = processIDs.withUnsafeMutableBufferPointer { buffer -> Int32 in
            proc_listallpids(buffer.baseAddress, Int32(buffer.count * MemoryLayout<pid_t>.stride))
        }
        return processIDs.prefix(max(0, Int(actualCount))).filter { $0 > 0 }
    }

    private static func processTreeProcessIDs(rootedAt rootPID: pid_t) -> [pid_t] {
        let processIDs = allProcessIDs()
        guard !processIDs.isEmpty else {
            return [rootPID]
        }

        var childrenByParent: [pid_t: [pid_t]] = [:]

        for processID in processIDs {
            var processInfo = proc_bsdinfo()
            let result = withUnsafeMutablePointer(to: &processInfo) { pointer -> Int32 in
                proc_pidinfo(processID, PROC_PIDTBSDINFO, 0, pointer, Int32(MemoryLayout<proc_bsdinfo>.stride))
            }
            guard result == Int32(MemoryLayout<proc_bsdinfo>.stride) else {
                continue
            }
            childrenByParent[pid_t(processInfo.pbi_ppid), default: []].append(processID)
        }

        var seen = Set<pid_t>([rootPID])
        var ordered: [pid_t] = [rootPID]
        var pending: [pid_t] = [rootPID]
        while let parent = pending.popLast() {
            for child in childrenByParent[parent] ?? [] where !seen.contains(child) {
                seen.insert(child)
                ordered.append(child)
                pending.append(child)
            }
        }
        return ordered
    }

    private static func appBundleProcessIDs(rootedAt rootPID: pid_t) -> [pid_t] {
        guard let bundleRootPath = appBundleRootPath(for: rootPID) else {
            return [rootPID]
        }

        let prefix = bundleRootPath + "/"
        return allProcessIDs().filter { processID in
            guard let path = executablePath(for: processID) else {
                return false
            }
            return path == bundleRootPath || path.hasPrefix(prefix)
        }
    }

    private static func tapBundleIDs(for bundleID: String?, appName: String?, rootProcessID: pid_t) -> [String] {
        var values: [String] = []
        if let bundleID, !bundleID.isEmpty {
            values.append(bundleID)
        }
        values.append(contentsOf: bundleIDsInAppBundle(rootedAt: rootProcessID))
        values.append(contentsOf: knownAudioOwnerBundleIDs(for: bundleID, appName: appName))
        return uniqueStrings(values)
    }

    private static func relatedAudioOwnerProcessIDs(bundleID: String?, appName: String?, rootProcessID: pid_t) -> [pid_t] {
        let audioOwnerBundleIDs = Set(knownAudioOwnerBundleIDs(for: bundleID, appName: appName))
        let executableFragments = knownAudioOwnerExecutableFragments(for: bundleID, appName: appName)
        guard !audioOwnerBundleIDs.isEmpty || !executableFragments.isEmpty else {
            return []
        }

        return allProcessIDs().filter { processID in
            guard processID != rootProcessID else {
                return false
            }
            if let processBundleID = bundleIdentifier(for: processID),
               audioOwnerBundleIDs.contains(processBundleID) {
                return true
            }
            guard let path = executablePath(for: processID) else {
                return false
            }
            return executableFragments.contains { path.contains($0) }
        }
    }

    private static func knownAudioOwnerBundleIDs(for bundleID: String?, appName: String?) -> [String] {
        switch normalizedKnownAudioOwnerKey(bundleID: bundleID, appName: appName) {
        case "zoom":
            return ["zoom.us.ZoomAudioDevice"]
        case "teams":
            return ["com.microsoft.MSTeamsAudioDevice", "com.microsoft.teams2.agent"]
        default:
            return []
        }
    }

    private static func knownAudioOwnerExecutableFragments(for bundleID: String?, appName: String?) -> [String] {
        switch normalizedKnownAudioOwnerKey(bundleID: bundleID, appName: appName) {
        case "zoom":
            return ["ZoomAudioDevice.driver", "ZoomAudioDevice"]
        case "teams":
            return ["MSTeamsAudioDevice.driver", "MSTeamsAudioDevice", "com.microsoft.teams2.agent"]
        default:
            return []
        }
    }

    private static func normalizedKnownAudioOwnerKey(bundleID: String?, appName: String?) -> String? {
        let normalizedBundleID = bundleID?.lowercased()
        let normalizedAppName = appName?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if normalizedBundleID == "us.zoom.xos" || normalizedAppName == "zoom" || normalizedAppName == "zoom.us" {
            return "zoom"
        }
        if normalizedBundleID == "com.microsoft.teams2" || normalizedAppName == "microsoft teams" {
            return "teams"
        }
        return nil
    }

    private static func bundleIDsInAppBundle(rootedAt rootProcessID: pid_t) -> [String] {
        guard let bundleRootPath = appBundleRootPath(for: rootProcessID),
              let enumerator = FileManager.default.enumerator(
                at: URL(fileURLWithPath: bundleRootPath),
                includingPropertiesForKeys: [.isRegularFileKey],
                options: [.skipsHiddenFiles]
              ) else {
            return []
        }

        var bundleIDs: [String] = []
        for case let url as URL in enumerator where url.lastPathComponent == "Info.plist" {
            guard let payload = NSDictionary(contentsOf: url),
                  let identifier = payload["CFBundleIdentifier"] as? String,
                  !identifier.isEmpty else {
                continue
            }
            bundleIDs.append(identifier)
        }
        return uniqueStrings(bundleIDs)
    }

    private static func appBundleRootPath(for processID: pid_t) -> String? {
        return bundleRootPath(for: processID, extensions: [".app"])
    }

    private static func bundleRootPath(for processID: pid_t, extensions: [String]) -> String? {
        guard let executablePath = executablePath(for: processID),
              let range = extensions.compactMap({ executablePath.range(of: $0, options: [.caseInsensitive]) }).first else {
            return nil
        }
        return String(executablePath[..<range.upperBound])
    }

    private static func bundleIdentifier(for processID: pid_t) -> String? {
        guard let bundleRootPath = bundleRootPath(for: processID, extensions: [".app", ".driver", ".appex", ".xpc"]) else {
            return nil
        }
        let infoPlistURL = URL(fileURLWithPath: bundleRootPath).appendingPathComponent("Contents/Info.plist")
        guard let payload = NSDictionary(contentsOf: infoPlistURL),
              let identifier = payload["CFBundleIdentifier"] as? String,
              !identifier.isEmpty else {
            return nil
        }
        return identifier
    }

    private static func executablePath(for processID: pid_t) -> String? {
        var buffer = [CChar](repeating: 0, count: 4096)
        let result = proc_pidpath(processID, &buffer, UInt32(buffer.count))
        guard result > 0 else {
            return nil
        }
        return String(cString: buffer)
    }

    private static func uniqueStrings(_ values: [String]) -> [String] {
        var seen = Set<String>()
        var ordered: [String] = []
        for value in values where !seen.contains(value) {
            seen.insert(value)
            ordered.append(value)
        }
        return ordered
    }

    private static func audioFormat(forTap tapID: AudioObjectID) throws -> AVAudioFormat {
        var address = AudioObjectPropertyAddress(
            mSelector: kAudioTapPropertyFormat,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )
        var streamDescription = AudioStreamBasicDescription()
        var dataSize = UInt32(MemoryLayout<AudioStreamBasicDescription>.size)
        let status = AudioObjectGetPropertyData(tapID, &address, 0, nil, &dataSize, &streamDescription)
        guard status == noErr,
              let format = AVAudioFormat(streamDescription: &streamDescription) else {
            throw HelperError.writerFailed("failed to read muted app audio format: \(describe(status: status))")
        }
        return format
    }

    private static func createAggregateDevice(for tapDescription: CATapDescription) throws -> AudioObjectID {
        let aggregateUID = "com.thirdeye.muted-app-audio.\(UUID().uuidString)"
        let description: [String: Any] = [
            kAudioAggregateDeviceNameKey: "thirdeye muted app audio",
            kAudioAggregateDeviceUIDKey: aggregateUID,
            kAudioAggregateDeviceIsPrivateKey: true,
            kAudioAggregateDeviceTapAutoStartKey: false,
            kAudioAggregateDeviceTapListKey: [
                [kAudioSubTapUIDKey: tapDescription.uuid.uuidString]
            ],
        ]
        var deviceID = AudioObjectID(kAudioObjectUnknown)
        let status = AudioHardwareCreateAggregateDevice(description as CFDictionary, &deviceID)
        guard status == noErr, deviceID != AudioObjectID(kAudioObjectUnknown) else {
            throw HelperError.writerFailed("failed to create muted app audio device: \(describe(status: status))")
        }
        return deviceID
    }

    private static func copyAudio(_ inputData: UnsafePointer<AudioBufferList>, format: AVAudioFormat) -> CapturedTapAudio {
        let audioBuffers = UnsafeMutableAudioBufferListPointer(UnsafeMutablePointer(mutating: inputData))
        let buffers = audioBuffers.map { buffer -> Data in
            guard let data = buffer.mData,
                  buffer.mDataByteSize > 0 else {
                return Data()
            }
            return Data(bytes: data, count: Int(buffer.mDataByteSize))
        }
        let bytesPerFrame = max(Int(format.streamDescription.pointee.mBytesPerFrame), 1)
        let firstBufferSize = audioBuffers.first.map { Int($0.mDataByteSize) } ?? 0
        let frameCount = AVAudioFrameCount(firstBufferSize / bytesPerFrame)
        return CapturedTapAudio(format: format, buffers: buffers, frameCount: frameCount)
    }

    fileprivate static func describe(status: OSStatus) -> String {
        let bigEndian = UInt32(bitPattern: status).bigEndian
        let text = withUnsafeBytes(of: bigEndian) { rawBuffer -> String? in
            guard let baseAddress = rawBuffer.baseAddress else {
                return nil
            }
            let data = Data(bytes: baseAddress, count: rawBuffer.count)
            let scalarText = String(data: data, encoding: .macOSRoman)
            return scalarText?.allSatisfy { $0.isASCII && !$0.isWhitespace } == true ? scalarText : nil
        }
        if let text {
            return "\(status) (\(text))"
        }
        return "\(status)"
    }
}

final class StreamController: NSObject, SCStreamOutput, SCStreamDelegate {
    private let mode: CaptureMode
    private let target: CaptureTarget
    private var stream: SCStream?
    private var streamWidth = 0
    private var streamHeight = 0
    private var targetAppProcessID: pid_t?
    private var targetAudioMuted: Bool
    private var writer: AVAssetWriter?
    private var videoInput: AVAssetWriterInput?
    private var audioInput: AVAssetWriterInput?
    private var liveAudioFileDescriptor: Int32?
    private var liveAudioConverter: AVAudioConverter?
    private var liveAudioSourceFormat: AVAudioFormat?
    private var recordingAudioFormat: AVAudioFormat?
    private var processTapAudioCapture: ProcessTapAudioCapture?
    private var didStartWriting = false
    private var didFinish = false
    private var stopError: Error?
    private var recordingSessionStartTime: CMTime?
    private var latestRecordingPresentationTime: CMTime?
    private var mutedRecordingAudioStartTime: CMTime?
    private var mutedRecordingAudioFramePosition: AVAudioFramePosition = 0
    private var didLogRecordingAudioSampleBufferFailure = false
    private var didLogRecordingAudioAppendFailure = false
    private var finishContinuation: CheckedContinuation<Void, Error>?
    private let outputQueue = DispatchQueue(label: "macos.capture.helper.output")
    private let audioWriteQueue = DispatchQueue(label: "macos.capture.helper.audio-writer")
    private static let liveAudioOutputFormat = AVAudioFormat(
        commonFormat: .pcmFormatInt16,
        sampleRate: 16_000,
        channels: 1,
        interleaved: true
    )!

    init(mode: CaptureMode, target: CaptureTarget) {
        self.mode = mode
        self.target = target
        self.targetAudioMuted = mode.muteTargetAudio
    }

    func start() async throws {
        let content: SCShareableContent
        do {
            content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: true)
        } catch {
            throw Self.normalize(error: error)
        }

        let resolved = try resolveTarget(from: content, target: target)
        streamWidth = resolved.width
        streamHeight = resolved.height
        targetAppProcessID = resolved.appProcessID
        let configuration = Self.makeConfiguration(mode: mode, width: resolved.width, height: resolved.height, muteTargetAudio: targetAudioMuted)
        if case .record(let outputFile, let recordsAudio, let liveAudioFifoPath, _) = mode {
            try prepareWriter(
                outputFile: outputFile,
                width: resolved.width,
                height: resolved.height,
                audioSampleRate: Self.audioSampleRate(for: mode),
                audioChannelCount: Self.audioChannelCount(for: mode),
                recordsAudio: recordsAudio
            )
            if let liveAudioFifoPath {
                try prepareFIFO(at: liveAudioFifoPath)
            }
        }
        if case .liveAudio(let fifoPath, _) = mode {
                try prepareFIFO(at: fifoPath)
        }

        if targetAudioMuted {
            try startProcessTapAudioCapture()
        }

        let stream = SCStream(filter: resolved.filter, configuration: configuration, delegate: self)
        self.stream = stream
        if case .record = mode {
            try stream.addStreamOutput(self, type: .screen, sampleHandlerQueue: outputQueue)
        }
        if Self.hasAudioOutput(for: mode) {
            try stream.addStreamOutput(self, type: .audio, sampleHandlerQueue: outputQueue)
        }
        try await stream.startCapture()
    }

    func waitUntilStopped() async throws {
        if didFinish {
            if let stopError {
                throw stopError
            }
            return
        }
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            finishContinuation = continuation
        }
    }

    func stop(error: Error? = nil) async throws {
        guard !didFinish else {
            return
        }
        stopError = error
        didFinish = true
        if let stream {
            try? await stream.stopCapture()
        }
        stream = nil
        stopProcessTapAudioCapture()

        if didStartWriting, let videoInput {
            videoInput.markAsFinished()
        }
        if didStartWriting, let audioInput {
            audioInput.markAsFinished()
        }
        if let fileDescriptor = liveAudioFileDescriptor {
            close(fileDescriptor)
            liveAudioFileDescriptor = nil
        }

        if let writer {
            guard didStartWriting else {
                writer.cancelWriting()
                if let stopError {
                    finishContinuation?.resume(throwing: stopError)
                } else {
                    finishContinuation?.resume()
                }
                finishContinuation = nil
                return
            }
            await withCheckedContinuation { (continuation: CheckedContinuation<Void, Never>) in
                writer.finishWriting {
                    continuation.resume()
                }
            }
            if writer.status == .failed {
                finishContinuation?.resume(throwing: HelperError.writerFailed(writer.error?.localizedDescription ?? "recording finalization failed"))
            } else {
                finishContinuation?.resume()
            }
            finishContinuation = nil
            return
        }

        if let stopError {
            finishContinuation?.resume(throwing: stopError)
        } else {
            finishContinuation?.resume()
        }
        finishContinuation = nil
    }

    func setTargetAudioMuted(_ muteTargetAudio: Bool) async throws {
        guard targetAudioMuted != muteTargetAudio else {
            return
        }

        if muteTargetAudio {
            try startProcessTapAudioCapture()
            resetMutedRecordingAudioClock()
            targetAudioMuted = true
            do {
                try await updateStreamAudioConfiguration()
            } catch {
                stopProcessTapAudioCapture()
                targetAudioMuted = false
                throw error
            }
            return
        }

        targetAudioMuted = false
        resetMutedRecordingAudioClock()
        do {
            try await updateStreamAudioConfiguration()
            stopProcessTapAudioCapture()
        } catch {
            targetAudioMuted = true
            throw error
        }
    }

    func stream(_ stream: SCStream, didStopWithError error: Error) {
        Task {
            try? await stop(error: Self.normalize(error: error))
        }
    }

    func stream(_ stream: SCStream, didOutputSampleBuffer sampleBuffer: CMSampleBuffer, of outputType: SCStreamOutputType) {
        guard CMSampleBufferIsValid(sampleBuffer) else {
            return
        }
        switch mode {
        case .record:
            appendRecordingSample(sampleBuffer, outputType: outputType)
        case .liveAudio:
            if outputType == .audio {
                writeLiveAudioSample(sampleBuffer)
            }
        }
    }

    private func appendRecordingSample(_ sampleBuffer: CMSampleBuffer, outputType: SCStreamOutputType) {
        guard let writer else {
            return
        }
        if outputType == .screen, !Self.isCompleteScreenSample(sampleBuffer) {
            return
        }
        let presentationTime = CMSampleBufferGetPresentationTimeStamp(sampleBuffer)
        rememberRecordingPresentationTime(presentationTime)
        if !didStartWriting {
            writer.startWriting()
            writer.startSession(atSourceTime: presentationTime)
            didStartWriting = true
            recordingSessionStartTime = presentationTime
        }
        switch outputType {
        case .screen:
            if let videoInput, videoInput.isReadyForMoreMediaData {
                videoInput.append(sampleBuffer)
            }
        case .audio:
            appendRecordingAudioSample(sampleBuffer)
            writeLiveAudioSample(sampleBuffer)
        default:
            break
        }
    }

    private static func isCompleteScreenSample(_ sampleBuffer: CMSampleBuffer) -> Bool {
        guard let attachments = CMSampleBufferGetSampleAttachmentsArray(sampleBuffer, createIfNecessary: false) as? [[SCStreamFrameInfo: Any]],
              let rawStatus = attachments.first?[SCStreamFrameInfo.status] as? Int,
              let status = SCFrameStatus(rawValue: rawStatus) else {
            return false
        }
        return status == .complete
    }

    private func startProcessTapAudioCapture() throws {
        if processTapAudioCapture != nil {
            return
        }
        guard let targetAppProcessID else {
            throw HelperError.missingApplicationProcess
        }
        let processTapAudioCapture = ProcessTapAudioCapture(
            processID: targetAppProcessID,
            bundleID: target.app_bundle_id,
            appName: target.app_name,
            outputQueue: outputQueue
        ) { [weak self] captured in
            self?.writeProcessTapAudio(captured)
        }
        try processTapAudioCapture.start()
        self.processTapAudioCapture = processTapAudioCapture
    }

    private func stopProcessTapAudioCapture() {
        processTapAudioCapture?.stop()
        processTapAudioCapture = nil
    }

    private func updateStreamAudioConfiguration() async throws {
        guard let stream else {
            return
        }
        let configuration = Self.makeConfiguration(
            mode: mode,
            width: streamWidth,
            height: streamHeight,
            muteTargetAudio: targetAudioMuted
        )
        try await stream.updateConfiguration(configuration)
    }

    private func writeLiveAudioSample(_ sampleBuffer: CMSampleBuffer) {
        guard let fileDescriptor = liveAudioFileDescriptor,
              let data = liveAudioLinear16Data(from: sampleBuffer),
              !data.isEmpty else {
            return
        }
        audioWriteQueue.async {
            Self.writeAll(data, to: fileDescriptor)
        }
    }

    private func writeProcessTapAudio(_ captured: CapturedTapAudio) {
        guard targetAudioMuted else {
            return
        }
        guard let sourceBuffer = pcmBuffer(from: captured) else {
            return
        }
        appendMutedRecordingAudio(sourceBuffer)

        guard let fileDescriptor = liveAudioFileDescriptor,
              let data = liveAudioLinear16Data(from: sourceBuffer),
              !data.isEmpty else {
            return
        }
        audioWriteQueue.async {
            Self.writeAll(data, to: fileDescriptor)
        }
    }

    private func appendMutedRecordingAudio(_ sourceBuffer: AVAudioPCMBuffer) {
        guard case .record = mode,
              targetAudioMuted,
              sourceBuffer.frameLength > 0 else {
            return
        }
        guard didStartWriting,
              let recordingSessionStartTime else {
            return
        }
        if mutedRecordingAudioStartTime == nil {
            mutedRecordingAudioStartTime = latestRecordingPresentationTime ?? recordingSessionStartTime
        }
        guard let mutedRecordingAudioStartTime else {
            return
        }
        guard let normalizedBuffer = normalizedRecordingAudioBuffer(sourceBuffer) else {
            return
        }

        let frameOffset = CMTime(
            seconds: Double(mutedRecordingAudioFramePosition) / normalizedBuffer.format.sampleRate,
            preferredTimescale: 600_000
        )
        mutedRecordingAudioFramePosition += AVAudioFramePosition(normalizedBuffer.frameLength)

        appendNormalizedRecordingAudioBuffer(
            normalizedBuffer,
            presentationTime: CMTimeAdd(mutedRecordingAudioStartTime, frameOffset),
            failurePrefix: "muted recording audio append failed"
        )
    }

    private func appendRecordingAudioSample(_ sampleBuffer: CMSampleBuffer) {
        guard let sourceBuffer = recordingAudioBuffer(from: sampleBuffer) else {
            return
        }
        appendRecordingAudioBuffer(
            sourceBuffer,
            presentationTime: CMSampleBufferGetPresentationTimeStamp(sampleBuffer),
            failurePrefix: "recording audio append failed"
        )
    }

    private func appendRecordingAudioBuffer(_ sourceBuffer: AVAudioPCMBuffer, presentationTime: CMTime, failurePrefix: String) {
        guard let normalizedBuffer = normalizedRecordingAudioBuffer(sourceBuffer) else {
            return
        }
        appendNormalizedRecordingAudioBuffer(normalizedBuffer, presentationTime: presentationTime, failurePrefix: failurePrefix)
    }

    private func appendNormalizedRecordingAudioBuffer(_ sourceBuffer: AVAudioPCMBuffer, presentationTime: CMTime, failurePrefix: String) {
        guard let audioInput,
              audioInput.isReadyForMoreMediaData else {
            return
        }
        guard let recordingSampleBuffer = recordingAudioSampleBuffer(from: sourceBuffer, presentationTime: presentationTime) else {
            return
        }
        if !audioInput.append(recordingSampleBuffer) {
            logRecordingAudioAppendFailure(prefix: failurePrefix)
            return
        }
    }

    private func recordingAudioBuffer(from sampleBuffer: CMSampleBuffer) -> AVAudioPCMBuffer? {
        guard let formatDescription = CMSampleBufferGetFormatDescription(sampleBuffer) else {
            return nil
        }
        let sourceFormat = AVAudioFormat(cmAudioFormatDescription: formatDescription)
        let frameCount = CMSampleBufferGetNumSamples(sampleBuffer)
        guard frameCount > 0,
              let sourceBuffer = AVAudioPCMBuffer(pcmFormat: sourceFormat, frameCapacity: AVAudioFrameCount(frameCount)) else {
            return nil
        }
        sourceBuffer.frameLength = AVAudioFrameCount(frameCount)
        let copyStatus = CMSampleBufferCopyPCMDataIntoAudioBufferList(
            sampleBuffer,
            at: 0,
            frameCount: Int32(frameCount),
            into: sourceBuffer.mutableAudioBufferList
        )
        guard copyStatus == noErr else {
            return nil
        }
        return sourceBuffer
    }

    private func normalizedRecordingAudioBuffer(_ sourceBuffer: AVAudioPCMBuffer) -> AVAudioPCMBuffer? {
        guard sourceBuffer.frameLength > 0 else {
            return nil
        }
        if recordingAudioFormat == nil {
            recordingAudioFormat = sourceBuffer.format
        }
        guard let targetFormat = recordingAudioFormat else {
            return sourceBuffer
        }
        if Self.formatsMatch(sourceBuffer.format, targetFormat) {
            return sourceBuffer
        }
        guard let converter = AVAudioConverter(from: sourceBuffer.format, to: targetFormat) else {
            return nil
        }
        let sampleRateRatio = targetFormat.sampleRate / sourceBuffer.format.sampleRate
        let estimatedFrames = Int(ceil(Double(sourceBuffer.frameLength) * sampleRateRatio)) + 512
        guard let outputBuffer = AVAudioPCMBuffer(
            pcmFormat: targetFormat,
            frameCapacity: AVAudioFrameCount(max(1, estimatedFrames))
        ) else {
            return nil
        }

        var didProvideInput = false
        var conversionError: NSError?
        let conversionStatus = converter.convert(to: outputBuffer, error: &conversionError) { _, inputStatus in
            if didProvideInput {
                inputStatus.pointee = .noDataNow
                return nil
            }
            didProvideInput = true
            inputStatus.pointee = .haveData
            return sourceBuffer
        }
        guard conversionStatus != .error,
              outputBuffer.frameLength > 0 else {
            return nil
        }
        return outputBuffer
    }

    private func logRecordingAudioAppendFailure(prefix: String) {
        guard !didLogRecordingAudioAppendFailure else {
            return
        }
        didLogRecordingAudioAppendFailure = true
        let writerStatus = writer.map { "\($0.status.rawValue)" } ?? "missing"
        let writerError = writer?.error?.localizedDescription ?? "none"
        fputs("\(prefix) writer_status=\(writerStatus) writer_error=\(writerError)\n", stderr)
    }

    private func rememberRecordingPresentationTime(_ presentationTime: CMTime) {
        guard presentationTime.isValid,
              !presentationTime.isIndefinite,
              !presentationTime.isNegativeInfinity,
              !presentationTime.isPositiveInfinity else {
            return
        }
        if let latestRecordingPresentationTime,
           CMTimeCompare(presentationTime, latestRecordingPresentationTime) <= 0 {
            return
        }
        latestRecordingPresentationTime = presentationTime
    }

    private func resetMutedRecordingAudioClock() {
        mutedRecordingAudioStartTime = nil
        mutedRecordingAudioFramePosition = 0
    }

    private func pcmBuffer(from captured: CapturedTapAudio) -> AVAudioPCMBuffer? {
        guard captured.frameCount > 0,
              let buffer = AVAudioPCMBuffer(pcmFormat: captured.format, frameCapacity: captured.frameCount) else {
            return nil
        }
        buffer.frameLength = captured.frameCount
        let destinationBuffers = UnsafeMutableAudioBufferListPointer(buffer.mutableAudioBufferList)
        let count = min(destinationBuffers.count, captured.buffers.count)
        for index in 0..<count {
            guard let destination = destinationBuffers[index].mData else {
                continue
            }
            let source = captured.buffers[index]
            let byteCount = min(source.count, Int(destinationBuffers[index].mDataByteSize))
            source.copyBytes(to: destination.assumingMemoryBound(to: UInt8.self), count: byteCount)
            destinationBuffers[index].mDataByteSize = UInt32(byteCount)
        }
        return buffer
    }

    private func recordingAudioSampleBuffer(from sourceBuffer: AVAudioPCMBuffer, presentationTime: CMTime) -> CMSampleBuffer? {
        let formatDescription = sourceBuffer.format.formatDescription

        var sampleBuffer: CMSampleBuffer?
        let createStatus = CMAudioSampleBufferCreateWithPacketDescriptions(
            allocator: kCFAllocatorDefault,
            dataBuffer: nil,
            dataReady: false,
            makeDataReadyCallback: nil,
            refcon: nil,
            formatDescription: formatDescription,
            sampleCount: CMItemCount(sourceBuffer.frameLength),
            presentationTimeStamp: presentationTime,
            packetDescriptions: nil,
            sampleBufferOut: &sampleBuffer
        )
        guard createStatus == noErr,
              let sampleBuffer else {
            logRecordingAudioSampleBufferFailure(stage: "create", status: createStatus, sourceBuffer: sourceBuffer)
            return nil
        }

        let dataStatus = CMSampleBufferSetDataBufferFromAudioBufferList(
            sampleBuffer,
            blockBufferAllocator: kCFAllocatorDefault,
            blockBufferMemoryAllocator: kCFAllocatorDefault,
            flags: 0,
            bufferList: sourceBuffer.audioBufferList
        )
        guard dataStatus == noErr else {
            logRecordingAudioSampleBufferFailure(stage: "set_data_buffer", status: dataStatus, sourceBuffer: sourceBuffer)
            return nil
        }
        let readyStatus = CMSampleBufferSetDataReady(sampleBuffer)
        guard readyStatus == noErr else {
            logRecordingAudioSampleBufferFailure(stage: "set_data_ready", status: readyStatus, sourceBuffer: sourceBuffer)
            return nil
        }
        return sampleBuffer
    }

    private func logRecordingAudioSampleBufferFailure(stage: String, status: OSStatus, sourceBuffer: AVAudioPCMBuffer) {
        guard !didLogRecordingAudioSampleBufferFailure else {
            return
        }
        didLogRecordingAudioSampleBufferFailure = true
        let asbd = sourceBuffer.format.streamDescription.pointee
        fputs(
            "recording audio sample buffer failed stage=\(stage) status=\(ProcessTapAudioCapture.describe(status: status)) sample_rate=\(asbd.mSampleRate) format_id=\(asbd.mFormatID) format_flags=\(asbd.mFormatFlags) bytes_per_packet=\(asbd.mBytesPerPacket) frames_per_packet=\(asbd.mFramesPerPacket) bytes_per_frame=\(asbd.mBytesPerFrame) channels_per_frame=\(asbd.mChannelsPerFrame) bits_per_channel=\(asbd.mBitsPerChannel) interleaved=\(sourceBuffer.format.isInterleaved) common_format=\(sourceBuffer.format.commonFormat.rawValue) frame_length=\(sourceBuffer.frameLength)\n",
            stderr
        )
    }

    private func liveAudioLinear16Data(from sampleBuffer: CMSampleBuffer) -> Data? {
        guard let formatDescription = CMSampleBufferGetFormatDescription(sampleBuffer) else {
            return nil
        }
        let sourceFormat = AVAudioFormat(cmAudioFormatDescription: formatDescription)
        let frameCount = CMSampleBufferGetNumSamples(sampleBuffer)
        guard frameCount > 0,
              let sourceBuffer = AVAudioPCMBuffer(pcmFormat: sourceFormat, frameCapacity: AVAudioFrameCount(frameCount)) else {
            return nil
        }
        sourceBuffer.frameLength = AVAudioFrameCount(frameCount)
        let copyStatus = CMSampleBufferCopyPCMDataIntoAudioBufferList(
            sampleBuffer,
            at: 0,
            frameCount: Int32(frameCount),
            into: sourceBuffer.mutableAudioBufferList
        )
        guard copyStatus == noErr else {
            return nil
        }

        return liveAudioLinear16Data(from: sourceBuffer)
    }

    private func liveAudioLinear16Data(from sourceBuffer: AVAudioPCMBuffer) -> Data? {
        let sourceFormat = sourceBuffer.format
        guard let converter = liveAudioConverter(for: sourceFormat) else {
            return nil
        }
        let sampleRateRatio = Self.liveAudioOutputFormat.sampleRate / sourceFormat.sampleRate
        let estimatedFrames = Int(ceil(Double(sourceBuffer.frameLength) * sampleRateRatio)) + 512
        guard let outputBuffer = AVAudioPCMBuffer(
            pcmFormat: Self.liveAudioOutputFormat,
            frameCapacity: AVAudioFrameCount(max(1, estimatedFrames))
        ) else {
            return nil
        }

        var didProvideInput = false
        var conversionError: NSError?
        let conversionStatus = converter.convert(to: outputBuffer, error: &conversionError) { _, inputStatus in
            if didProvideInput {
                inputStatus.pointee = .noDataNow
                return nil
            }
            didProvideInput = true
            inputStatus.pointee = .haveData
            return sourceBuffer
        }
        guard conversionStatus != .error,
              outputBuffer.frameLength > 0 else {
            return nil
        }

        let audioBuffer = outputBuffer.audioBufferList.pointee.mBuffers
        guard let audioData = audioBuffer.mData,
              audioBuffer.mDataByteSize > 0 else {
            return nil
        }
        return Data(bytes: audioData, count: Int(audioBuffer.mDataByteSize))
    }

    private func liveAudioConverter(for sourceFormat: AVAudioFormat) -> AVAudioConverter? {
        if liveAudioConverter == nil || !Self.formatsMatch(liveAudioSourceFormat, sourceFormat) {
            liveAudioSourceFormat = sourceFormat
            liveAudioConverter = AVAudioConverter(from: sourceFormat, to: Self.liveAudioOutputFormat)
        }
        return liveAudioConverter
    }

    private static func formatsMatch(_ lhs: AVAudioFormat?, _ rhs: AVAudioFormat) -> Bool {
        guard let lhs else {
            return false
        }
        return lhs.commonFormat == rhs.commonFormat
            && lhs.sampleRate == rhs.sampleRate
            && lhs.channelCount == rhs.channelCount
            && lhs.isInterleaved == rhs.isInterleaved
    }

    private static func writeAll(_ data: Data, to fileDescriptor: Int32) {
        data.withUnsafeBytes { buffer in
            guard let baseAddress = buffer.baseAddress else {
                return
            }
            var offset = 0
            while offset < buffer.count {
                let written = Darwin.write(fileDescriptor, baseAddress.advanced(by: offset), buffer.count - offset)
                if written > 0 {
                    offset += written
                    continue
                }
                if written == -1 && errno == EINTR {
                    continue
                }
                return
            }
        }
    }

    private func prepareWriter(outputFile: URL, width: Int, height: Int, audioSampleRate: Int, audioChannelCount: Int, recordsAudio: Bool) throws {
        try FileManager.default.createDirectory(at: outputFile.deletingLastPathComponent(), withIntermediateDirectories: true)
        if FileManager.default.fileExists(atPath: outputFile.path) {
            try FileManager.default.removeItem(at: outputFile)
        }

        let writer = try AVAssetWriter(outputURL: outputFile, fileType: .mp4)
        let videoInput = AVAssetWriterInput(
            mediaType: .video,
            outputSettings: [
                AVVideoCodecKey: AVVideoCodecType.h264,
                AVVideoWidthKey: width,
                AVVideoHeightKey: height,
            ]
        )
        videoInput.expectsMediaDataInRealTime = true

        let audioInput: AVAssetWriterInput?
        if recordsAudio {
            let input = AVAssetWriterInput(
                mediaType: .audio,
                outputSettings: [
                    AVFormatIDKey: kAudioFormatMPEG4AAC,
                    AVSampleRateKey: audioSampleRate,
                    AVNumberOfChannelsKey: audioChannelCount,
                    AVEncoderBitRateKey: audioSampleRate == 16_000 ? 64_000 : 192_000,
                ]
            )
            input.expectsMediaDataInRealTime = true
            audioInput = input
        } else {
            audioInput = nil
        }

        if writer.canAdd(videoInput) {
            writer.add(videoInput)
        }
        if let audioInput, writer.canAdd(audioInput) {
            writer.add(audioInput)
        }

        self.writer = writer
        self.videoInput = videoInput
        self.audioInput = audioInput
    }

    private func prepareFIFO(at fifoPath: URL) throws {
        let directory = fifoPath.deletingLastPathComponent()
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        unlink(fifoPath.path)
        if mkfifo(fifoPath.path, 0o644) != 0 {
            throw HelperError.writerFailed("failed to create live audio fifo at \(fifoPath.path)")
        }
        let fileDescriptor = open(fifoPath.path, O_RDWR | O_NONBLOCK)
        if fileDescriptor < 0 {
            throw HelperError.writerFailed("failed to open live audio fifo at \(fifoPath.path)")
        }
        liveAudioFileDescriptor = fileDescriptor
    }

    private static func makeConfiguration(mode: CaptureMode, width: Int, height: Int, muteTargetAudio: Bool) -> SCStreamConfiguration {
        let configuration = SCStreamConfiguration()
        configuration.width = width
        configuration.height = height
        configuration.minimumFrameInterval = CMTime(value: 1, timescale: Int32(Self.framesPerSecond()))
        configuration.showsCursor = true
        configuration.capturesAudio = capturesAudio(for: mode, muteTargetAudio: muteTargetAudio)
        configuration.sampleRate = audioSampleRate(for: mode)
        configuration.channelCount = audioChannelCount(for: mode)
        return configuration
    }

    private static func capturesAudio(for mode: CaptureMode, muteTargetAudio: Bool) -> Bool {
        return !muteTargetAudio && hasAudioOutput(for: mode)
    }

    private static func hasAudioOutput(for mode: CaptureMode) -> Bool {
        switch mode {
        case .record(_, let recordsAudio, let liveAudioFifoPath, _):
            return recordsAudio || liveAudioFifoPath != nil
        case .liveAudio:
            return true
        }
    }

    private static func audioSampleRate(for mode: CaptureMode) -> Int {
        switch mode {
        case .record:
            return 48_000
        case .liveAudio:
            return 16_000
        }
    }

    private static func audioChannelCount(for mode: CaptureMode) -> Int {
        switch mode {
        case .record:
            return 2
        case .liveAudio:
            return 1
        }
    }

    private static func framesPerSecond() -> Int {
        Int(ProcessInfo.processInfo.environment["RECORDING_FPS"] ?? "15") ?? 15
    }

    private static func normalizedDimension(envKey: String, fallback: Int) -> Int {
        Int(ProcessInfo.processInfo.environment[envKey] ?? "") ?? fallback
    }

    private func resolveTarget(from content: SCShareableContent, target: CaptureTarget) throws -> ResolvedTarget {
        switch target.kind {
        case "display":
            let display = content.displays.first { "\($0.displayID)" == target.display_id || $0.displayID.description == target.display_id }
                ?? content.displays.first
            guard let display else {
                throw HelperError.missingDisplay
            }
            let excludedApplications = content.applications.filter(isReliableThirdeyeApplicationExclusion)
            let exceptingWindows = content.windows.filter(isThirdeyeWindowException)
            let filter = if excludedApplications.isEmpty && !exceptingWindows.isEmpty {
                SCContentFilter(display: display, excludingWindows: exceptingWindows)
            } else {
                SCContentFilter(display: display, excludingApplications: excludedApplications, exceptingWindows: exceptingWindows)
            }
            let width = Self.normalizedDimension(envKey: "RECORDING_WIDTH", fallback: 1280)
            let height = Self.normalizedDimension(envKey: "RECORDING_HEIGHT", fallback: 720)
            return ResolvedTarget(filter: filter, width: width, height: height, appProcessID: nil)
        case "application":
            if isThirdeyeApplication(bundleIdentifier: target.app_bundle_id, applicationName: target.app_name) {
                throw HelperError.protectedApplication
            }
            guard let display = content.displays.first else {
                throw HelperError.missingDisplay
            }
            let targetAppPID = target.app_pid
            let application = if let targetAppPID {
                content.applications.first { application in
                    application.processID == targetAppPID
                } ?? content.applications.first {
                    $0.bundleIdentifier == target.app_bundle_id || $0.applicationName == target.app_name
                }
            } else {
                content.applications.first {
                    $0.bundleIdentifier == target.app_bundle_id || $0.applicationName == target.app_name
                }
            }
            guard let application else {
                throw HelperError.missingApplication
            }
            if isThirdeyeApplication(application) {
                throw HelperError.protectedApplication
            }
            let filter = SCContentFilter(display: display, including: [application], exceptingWindows: [])
            let width = Self.normalizedDimension(envKey: "RECORDING_WIDTH", fallback: 1280)
            let height = Self.normalizedDimension(envKey: "RECORDING_HEIGHT", fallback: 720)
            return ResolvedTarget(filter: filter, width: width, height: height, appProcessID: application.processID)
        case "window":
            if isThirdeyeApplication(bundleIdentifier: target.app_bundle_id, applicationName: target.app_name) {
                throw HelperError.protectedApplication
            }
            let window = content.windows.first { "\($0.windowID)" == target.window_id || "\($0.windowID)" == target.id.replacingOccurrences(of: "window:", with: "") }
            guard let window else {
                throw HelperError.missingWindow
            }
            if isThirdeyeApplication(window.owningApplication) {
                throw HelperError.protectedApplication
            }
            let display = Self.display(containing: window, from: content.displays, requestedDisplayID: target.display_id)
            guard let display else {
                throw HelperError.missingDisplay
            }
            let filter = SCContentFilter(display: display, including: [window])
            let fallbackWidth = max(Int(window.frame.width), 1280)
            let fallbackHeight = max(Int(window.frame.height), 720)
            let width = Self.normalizedDimension(envKey: "RECORDING_WIDTH", fallback: fallbackWidth)
            let height = Self.normalizedDimension(envKey: "RECORDING_HEIGHT", fallback: fallbackHeight)
            return ResolvedTarget(filter: filter, width: width, height: height, appProcessID: window.owningApplication?.processID)
        default:
            throw HelperError.unsupportedTarget(target.kind)
        }
    }

    private static func display(containing window: SCWindow, from displays: [SCDisplay], requestedDisplayID: String?) -> SCDisplay? {
        if let requestedDisplayID,
           let display = displays.first(where: { "\($0.displayID)" == requestedDisplayID }) {
            return display
        }

        let midpoint = CGPoint(x: window.frame.midX, y: window.frame.midY)
        return displays.first(where: { $0.frame.contains(midpoint) }) ?? displays.first
    }

    private static func normalize(error: Error) -> Error {
        let description = error.localizedDescription.lowercased()
        if description.contains("not authorized") || description.contains("permission") {
            return HelperError.permissionDenied
        }
        return error
    }
}

func emitJSON(_ object: Any) throws {
    let data = try JSONSerialization.data(withJSONObject: object, options: [.prettyPrinted, .sortedKeys])
    if let text = String(data: data, encoding: .utf8) {
        print(text)
    }
}

func listTargets() async throws {
    let content: SCShareableContent
    do {
        content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: true)
    } catch {
        throw HelperError.permissionDenied
    }

    var payload: [[String: Any]] = []

    for display in content.displays {
        payload.append([
            "id": "display:\(display.displayID)",
            "kind": "display",
            "label": "Display \(display.displayID)",
            "display_id": "\(display.displayID)",
            "app_bundle_id": NSNull(),
            "app_name": NSNull(),
            "app_pid": NSNull(),
            "window_id": NSNull(),
        ])
    }

    let selectableWindows = content.windows.filter(isUserSelectableWindow)
    let selectableApplications = Dictionary(
        grouping: selectableWindows.compactMap(\.owningApplication),
        by: { $0.processID }
    ).compactMap { _, applications in applications.first }

    for app in selectableApplications.sorted(by: { $0.applicationName < $1.applicationName }) {
        payload.append([
            "id": "application:\(app.processID)",
            "kind": "application",
            "label": app.applicationName,
            "display_id": NSNull(),
            "app_bundle_id": app.bundleIdentifier,
            "app_name": app.applicationName,
            "app_pid": app.processID,
            "window_id": NSNull(),
        ])
    }

    for window in selectableWindows.sorted(by: { lhs, rhs in
        let lhsAppName = lhs.owningApplication?.applicationName ?? ""
        let rhsAppName = rhs.owningApplication?.applicationName ?? ""
        if lhsAppName == rhsAppName {
            return (lhs.title ?? "") < (rhs.title ?? "")
        }
        return lhsAppName < rhsAppName
    }) {
        guard let app = window.owningApplication else {
            continue
        }
        let windowLabel = (window.title ?? app.applicationName).trimmingCharacters(in: .whitespacesAndNewlines)
        let windowID = String(window.windowID)
        payload.append([
            "id": "window:\(windowID)",
            "kind": "window",
            "label": windowLabel,
            "display_id": NSNull(),
            "app_bundle_id": app.bundleIdentifier,
            "app_name": app.applicationName,
            "app_pid": app.processID,
            "window_id": windowID,
        ])
    }

    try emitJSON(["targets": payload])
}

func runStream(command: HelperCommand) async throws {
    let target: CaptureTarget
    let mode: CaptureMode
    let stopFile: URL?
    let muteCommandFile: URL?
    let muteStateFile: URL?
    switch command {
    case .record(let outputFile, let recordsAudio, let liveAudioFifoPath, let commandStopFile, let commandMuteFile, let commandMuteStateFile, let captureTarget, let muteTargetAudio):
        target = captureTarget
        mode = .record(outputFile: outputFile, recordsAudio: recordsAudio, liveAudioFifoPath: liveAudioFifoPath, muteTargetAudio: muteTargetAudio)
        stopFile = commandStopFile
        muteCommandFile = commandMuteFile
        muteStateFile = commandMuteStateFile
    case .liveAudio(let fifoPath, let commandStopFile, let commandMuteFile, let commandMuteStateFile, let captureTarget, let muteTargetAudio):
        target = captureTarget
        mode = .liveAudio(fifoPath: fifoPath, muteTargetAudio: muteTargetAudio)
        stopFile = commandStopFile
        muteCommandFile = commandMuteFile
        muteStateFile = commandMuteStateFile
    case .targets:
        return
    }

    let controller = StreamController(mode: mode, target: target)
    var stopSignals = sigset_t()
    sigemptyset(&stopSignals)
    sigaddset(&stopSignals, SIGINT)
    sigaddset(&stopSignals, SIGTERM)
    pthread_sigmask(SIG_BLOCK, &stopSignals, nil)
    let signalWatcher = Thread {
        var waitSet = stopSignals
        var receivedSignal: Int32 = 0
        if sigwait(&waitSet, &receivedSignal) == 0 {
            Task {
                try? await controller.stop()
            }
        }
    }
    signalWatcher.start()
    let stopFileWatcher = makeStopFileWatcher(stopFile: stopFile, controller: controller)
    let muteCommandFileWatcher = makeMuteCommandFileWatcher(
        commandFile: muteCommandFile,
        stateFile: muteStateFile,
        controller: controller
    )

    try await controller.start()
    try await controller.waitUntilStopped()

    _ = signalWatcher
    _ = stopFileWatcher
    _ = muteCommandFileWatcher
}

func makeStopFileWatcher(stopFile: URL?, controller: StreamController) -> Task<Void, Never>? {
    guard let stopFile else {
        return nil
    }
    return Task.detached {
        while !Task.isCancelled {
            if FileManager.default.fileExists(atPath: stopFile.path) {
                try? await controller.stop()
                return
            }
            try? await Task.sleep(nanoseconds: 100_000_000)
        }
    }
}

func makeMuteCommandFileWatcher(commandFile: URL?, stateFile: URL?, controller: StreamController) -> Task<Void, Never>? {
    guard let commandFile, let stateFile else {
        return nil
    }
    return Task.detached {
        var lastCommandID: String?
        while !Task.isCancelled {
            if let data = try? Data(contentsOf: commandFile),
               let command = try? JSONDecoder().decode(MuteCommand.self, from: data),
               command.id != lastCommandID {
                lastCommandID = command.id
                do {
                    try await controller.setTargetAudioMuted(command.mute_target_audio)
                    try writeMuteCommandState(
                        stateFile,
                        state: MuteCommandState(
                            id: command.id,
                            ok: true,
                            mute_target_audio: command.mute_target_audio,
                            error: nil
                        )
                    )
                } catch {
                    let message = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
                    try? writeMuteCommandState(
                        stateFile,
                        state: MuteCommandState(
                            id: command.id,
                            ok: false,
                            mute_target_audio: command.mute_target_audio,
                            error: message
                        )
                    )
                }
            }
            try? await Task.sleep(nanoseconds: 100_000_000)
        }
    }
}

func writeMuteCommandState(_ stateFile: URL, state: MuteCommandState) throws {
    let data = try JSONEncoder().encode(state)
    try FileManager.default.createDirectory(at: stateFile.deletingLastPathComponent(), withIntermediateDirectories: true)
    try data.write(to: stateFile, options: [.atomic])
}

@main
struct ScreenCaptureKitHelper {
    static func main() async {
        do {
            let command = try HelperCommand.parse(arguments: CommandLine.arguments)
            switch command {
            case .targets:
                try await listTargets()
            case .record, .liveAudio:
                try await runStream(command: command)
            }
        } catch {
            let message = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
            fputs("\(message)\n", stderr)
            exit(1)
        }
    }
}
