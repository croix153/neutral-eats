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

    // Day values realigned 2026-10-26 to the Creams Tokyo DAY spec
    // (Croix: "that blue and vermillion"): washi paper #FAF7F2,
    // ai-iro indigo #165E83, shu-iro vermillion #EB471F, warm stone
    // text. accentText is vermillion deepened for small text
    // (#C6360F, ~5:1 on washi); user is the you-are-here star in
    // the theme's location color (indigo day / cyan night = --good;
    // gold retired 2026-10-26 evening, read off-palette).
    static var bg: Color { return day ? Color(hex: 0xFAF7F2) : Color(hex: 0x070912) }            // --bg
    static var panel: Color { return day ? Color(hex: 0xFFFFFF) : Color(hex: 0x101527) }        // --panel (solid)
    static var panel2: Color { return day ? Color(hex: 0xF5EFE4) : Color(hex: 0x1A2140) }       // --panel-2
    static var ink: Color { return day ? Color(hex: 0x2B2B2B) : Color(hex: 0xEEF1FF) }          // --ink
    static var inkDim: Color { return day ? Color(hex: 0x44403C) : Color(hex: 0xA3AED6) }       // --ink-dim
    static var inkFaint: Color { return day ? Color(hex: 0x857E73) : Color(hex: 0x6D78A0) }     // --ink-faint
    static var accent: Color { return day ? Color(hex: 0xEB471F) : Color(hex: 0xFF4D7E) }       // --accent
    static var accentText: Color { return day ? Color(hex: 0xC6360F) : Color(hex: 0xFF4D7E) }   // --accent-text
    static var brand: Color { return day ? Color(hex: 0x165E83) : Color(hex: 0xFF4D7E) }        // --brand
    static var user: Color { return day ? Color(hex: 0x165E83) : Color(hex: 0x38E1FF) }         // --user (star, = --good)
    static var accentInk: Color { return Color.white }                                          // --accent-ink
    static var good: Color { return day ? Color(hex: 0x165E83) : Color(hex: 0x38E1FF) }         // --good
    static var line: Color {                                                                    // --line
        return day
            ? Color(red: 105.0 / 255.0, green: 88.0 / 255.0, blue: 70.0 / 255.0, opacity: 0.18)
            : Color(red: 130.0 / 255.0, green: 150.0 / 255.0, blue: 1.0, opacity: 0.16)
    }
}

/// The switcher's three states: follow the device (the default
/// Croix asked for, 2026-10-26), or an explicit day / night override.
enum NEThemePreference: String {
    case auto, day, night
}

/// Owns the theme preference (Croix, 2026-10-26: a switcher in the
/// header, top-right — the spot he marked). The default is AUTO:
/// the app matches the device's own light/dark setting, live. The
/// switcher cycles auto → day → night → auto, so a manual choice is
/// never a trap — one more stop on the cycle hands control back to
/// the device. ContentView computes the effective mode from the
/// preference + the environment color scheme and sets NEColor.mode
/// at the top of its body, so every render reads fresh colors.
@MainActor
final class ThemeStore: ObservableObject {
    @Published private(set) var preference: NEThemePreference

    private static let prefKey = "ne-theme-preference"
    private static let migrationKey = "ne-theme-v2-migrated"

    init() {
        let defaults = UserDefaults.standard
        if !defaults.bool(forKey: ThemeStore.migrationKey) {
            // Build 8 persisted an explicit day/night choice under
            // "ne-theme"; Croix's verdict was that a test tap
            // shouldn't stick forever — v2 starts from auto (device)
            // and only the new 3-state preference is honored.
            defaults.removeObject(forKey: "ne-theme")
            defaults.set(true, forKey: ThemeStore.migrationKey)
            defaults.set(NEThemePreference.auto.rawValue, forKey: ThemeStore.prefKey)
        }
        let raw = defaults.string(forKey: ThemeStore.prefKey)
        preference = NEThemePreference(rawValue: raw ?? "") ?? .auto
    }

    func cycle() {
        switch preference {
        case .auto: preference = .day
        case .day: preference = .night
        case .night: preference = .auto
        }
        UserDefaults.standard.set(preference.rawValue, forKey: ThemeStore.prefKey)
    }

    func effective(system: ColorScheme) -> NEThemeMode {
        switch preference {
        case .day: return .day
        case .night: return .night
        case .auto: return system == .light ? .day : .night
        }
    }
}
