import XCTest

/// Captures the Support sheet (Donate pill -> tip ladder) for the
/// IAP App Store review screenshots. The six tip products come
/// from the local StoreKit configuration file wired into the
/// scheme's TestAction (ios/Products.storekit), so no sandbox
/// account or network store is involved: the ladder renders from
/// the same product ids and prices as App Store Connect.
///
/// Run only by .github/workflows/support-sheet-capture.yml; the
/// PNG leaves the test as an XCTAttachment named "support-sheet"
/// and the workflow exports it from the .xcresult bundle.
final class SupportSheetUITests: XCTestCase {

    func testCaptureSupportSheet() throws {
        let app = XCUIApplication()

        // The first launch asks for location. Either answer is
        // fine for this capture — the Donate pill lives in the
        // fixed header and the sheet needs no location — the
        // monitor just has to clear the alert off the screen.
        addUIInterruptionMonitor(withDescription: "Location permission") { alert in
            for label in ["Don’t Allow", "Don't Allow", "Allow While Using App", "Allow Once"] {
                let button = alert.buttons[label]
                if button.exists {
                    button.tap()
                    return true
                }
            }
            return false
        }

        app.launch()
        app.tap() // nudge the interruption monitor if an alert is up

        let donate = app.buttons["Donate to support Neutral Eats"]
        XCTAssertTrue(donate.waitForExistence(timeout: 60),
                      "Donate pill never appeared")
        donate.tap()

        // The top rung of the ladder, by its accessibility label
        // ("Tip " + the product's localized displayPrice). Its
        // existence proves the StoreKit configuration applied and
        // the sheet rendered products, not the unavailable state.
        let topTip = app.buttons["Tip $50.00"]
        XCTAssertTrue(topTip.waitForExistence(timeout: 60),
                      "Tip ladder never rendered — StoreKit config not applied?")
        let firstTip = app.buttons["Tip $1.00"]
        XCTAssertTrue(firstTip.exists, "Bottom rung ($1) missing")

        // Let the sheet's presentation settle before the capture.
        Thread.sleep(forTimeInterval: 1.5)

        let shot = XCUIScreen.main.screenshot()
        let attachment = XCTAttachment(screenshot: shot)
        attachment.name = "support-sheet"
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}
