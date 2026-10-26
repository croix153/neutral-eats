import SwiftUI

/// Tokyo palette — mirrors web/preview.html's CSS variables exactly,
/// in both themes. `NEColor.mode` is the single switch: ThemeStore
/// sets it from the persisted choice before the first render and on
/// every toggle, and every color below is computed from it, so one
/// flip repaints the whole tree on the next render pass.
extension Color {
    init(hex: UInt32) {
        self.init(
            red: Double((hex >> 16) & 0xFF) / 255.0,
            green: Double((hex >> 8) & 0xFF) / 255.0,
            blue: Double(hex & 0xFF) / 255.0
        )
    }
}

enum NEThemeMode: String {
    case night, day
}

enum NEColor {
    static var mode: NEThemeMode = .night
    private static var day: Bool { return mode == .day }

    static var bg: Color { return day ? Color(hex: 0xE8ECF7) : Color(hex: 0x070912) }            // --bg
    static var panel: Color { return day ? Color(hex: 0xFFFFFF) : Color(hex: 0x101527) }        // --panel (solid)
    static var panel2: Color { return day ? Color(hex: 0xEEF1FA) : Color(hex: 0x1A2140) }       // --panel-2
    static var ink: Color { return day ? Color(hex: 0x161C33) : Color(hex: 0xEEF1FF) }          // --ink
    static var inkDim: Color { return day ? Color(hex: 0x4C5878) : Color(hex: 0xA3AED6) }       // --ink-dim
    static var inkFaint: Color { return day ? Color(hex: 0x8590B0) : Color(hex: 0x6D78A0) }     // --ink-faint
    static var accent: Color { return day ? Color(hex: 0xD92C57) : Color(hex: 0xFF4D7E) }       // --accent
    static var accentInk: Color { return Color.white }                                          // --accent-ink
    static var good: Color { return day ? Color(hex: 0x0B7EA4) : Color(hex: 0x38E1FF) }         // --good
    static var line: Color {                                                                    // --line
        return day
            ? Color(red: 30.0 / 255.0, green: 40.0 / 255.0, blue: 90.0 / 255.0, opacity: 0.14)
            : Color(red: 130.0 / 255.0, green: 150.0 / 255.0, blue: 1.0, opacity: 0.16)
    }
}

/// Owns the day/night choice (Croix, 2026-10-26: a switcher in the
/// header, top-right — the spot he marked). Default resolution mirrors
/// the web: the persisted choice ("ne-theme", same key as the web's
/// localStorage) wins; otherwise the system appearance; otherwise
/// night. ContentView observes this store, so a toggle re-renders the
/// tree against the flipped NEColor.mode.
@MainActor
final class ThemeStore: ObservableObject {
    @Published private(set) var mode: NEThemeMode

    init() {
        let stored = UserDefaults.standard.string(forKey: "ne-theme")
        let initial: NEThemeMode
        if stored == NEThemeMode.day.rawValue {
            initial = .day
        } else if stored == NEThemeMode.night.rawValue {
            initial = .night
        } else {
            initial = UITraitCollection.current.userInterfaceStyle == .light ? .day : .night
        }
        mode = initial
        NEColor.mode = initial
    }

    func toggle() {
        mode = (mode == .day) ? .night : .day
        NEColor.mode = mode
        UserDefaults.standard.set(mode.rawValue, forKey: "ne-theme")
    }
}
