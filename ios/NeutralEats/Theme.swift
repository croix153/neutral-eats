import SwiftUI

/// Tokyo palette — mirrors web/preview.html's CSS variables exactly.
extension Color {
    init(hex: UInt32) {
        self.init(
            red: Double((hex >> 16) & 0xFF) / 255.0,
            green: Double((hex >> 8) & 0xFF) / 255.0,
            blue: Double(hex & 0xFF) / 255.0
        )
    }
}

enum NEColor {
    static let bg = Color(hex: 0x070912)        // --bg
    static let panel = Color(hex: 0x101527)     // --panel (solid)
    static let panel2 = Color(hex: 0x1A2140)    // --panel-2
    static let ink = Color(hex: 0xEEF1FF)       // --ink
    static let inkDim = Color(hex: 0xA3AED6)    // --ink-dim
    static let inkFaint = Color(hex: 0x6D78A0)  // --ink-faint
    static let accent = Color(hex: 0xFF4D7E)    // --accent (sakura neon pink)
    static let accentInk = Color.white          // --accent-ink
    static let good = Color(hex: 0x38E1FF)      // --good (cyan)
    // --line: rgba(130,150,255,.16)
    static let line = Color(red: 130.0 / 255.0, green: 150.0 / 255.0, blue: 1.0, opacity: 0.16)
}
