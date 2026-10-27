import StoreKit
import SwiftUI

/// The tip jar (build 21, Croix 2026-10-27): a ladder of seven
/// consumable "Supporter Tip" products in App Store Connect
/// (ai.croix.neutraleats.tip.099 … .4999, $0.99–$49.99). Croix's
/// shape for it: a tip buys NOTHING — no features, no content, no
/// status — so the app's neutrality rule survives contact with
/// commerce: the results are identical whether or not anyone tips.
///
/// Everything runs through StoreKit 2 with no server component:
/// there is nothing to validate against, no account, and nothing
/// is recorded anywhere off the device beyond Apple's own
/// transaction ledger. Prices are ALWAYS the product's localized
/// `displayPrice` from the store — never a hardcoded string — so
/// the ladder reads correctly in every storefront currency.
@MainActor
final class TipStore: ObservableObject {
    /// Cheapest → priciest, matching the ASC product ladder.
    static let productIDs: [String] = [
        "ai.croix.neutraleats.tip.099",
        "ai.croix.neutraleats.tip.199",
        "ai.croix.neutraleats.tip.299",
        "ai.croix.neutraleats.tip.499",
        "ai.croix.neutraleats.tip.999",
        "ai.croix.neutraleats.tip.1999",
        "ai.croix.neutraleats.tip.4999",
    ]

    enum LoadState {
        case idle, loading, loaded, failed
    }

    @Published private(set) var products: [Product] = []
    @Published private(set) var loadState: LoadState = .idle
    /// The product whose purchase sheet is in flight, if any —
    /// drives the spinner on that one button and mutes the rest.
    @Published private(set) var purchasingID: String? = nil
    /// A tip cleared (here, or via Transaction.updates): the sheet
    /// swaps to its thank-you form until acknowledged.
    @Published var justTipped: Bool = false
    /// A purchase came back .pending (Ask to Buy, carrier
    /// approval): noted in the sheet, never treated as an error.
    @Published var purchasePending: Bool = false

    /// The entry points (summary-card heart, list row) render only
    /// once products are actually in hand — if the store can't be
    /// reached or the products aren't live yet, the section simply
    /// doesn't exist. A free app should never nag about a tip jar
    /// it can't even stock.
    var hasProducts: Bool { loadState == .loaded && !products.isEmpty }

    private var updatesTask: Task<Void, Never>?

    init() {
        // Purchases can complete outside the sheet's lifetime
        // (a pending tip approved later, a purchase finished on
        // another device): finish every verified tip transaction
        // and say thanks if the sheet happens to be watching.
        updatesTask = Task { [weak self] in
            for await result in Transaction.updates {
                guard let self = self else { return }
                if case .verified(let transaction) = result,
                   Self.productIDs.contains(transaction.productID) {
                    await transaction.finish()
                    self.justTipped = true
                }
            }
        }
    }

    deinit {
        updatesTask?.cancel()
    }

    func load() async {
        guard loadState == .idle else { return }
        loadState = .loading
        do {
            let fetched = try await Product.products(for: Self.productIDs)
            products = fetched.sorted { $0.price < $1.price }
            loadState = products.isEmpty ? .failed : .loaded
        } catch {
            loadState = .failed
        }
    }

    /// Run one tip purchase. Cancellation is silent (the user
    /// changed their mind — nothing to say), errors are silent
    /// (a tip jar never gets to nag), pending is noted in the
    /// sheet, and success finishes the transaction and flips the
    /// thank-you state.
    func tip(_ product: Product) async {
        guard purchasingID == nil else { return }
        purchasingID = product.id
        purchasePending = false
        defer { purchasingID = nil }
        do {
            switch try await product.purchase() {
            case .success(let verification):
                if case .verified(let transaction) = verification {
                    await transaction.finish()
                    justTipped = true
                }
            case .userCancelled:
                break
            case .pending:
                purchasePending = true
            @unknown default:
                break
            }
        } catch {
            // Silent by design — see above.
        }
    }

    /// The sheet is leaving: clear the transient states so the
    /// next open starts from the ladder, not yesterday's thanks.
    func acknowledge() {
        justTipped = false
        purchasePending = false
    }
}

/// The Support sheet: pitch, the tip ladder, and the thank-you
/// form. Presented from the bottom card's summary heart button and
/// the list's last row; wears the same panel chrome and system
/// type as the rest of the card system (Raleway stays on the
/// wordmark only).
struct SupportSheet: View {
    @ObservedObject var tips: TipStore
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            if tips.justTipped {
                thankYou
            } else {
                ladder
            }
            Spacer(minLength: 0)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .background(NEColor.panel)
        .onDisappear { tips.acknowledge() }
    }

    private var header: some View {
        HStack(spacing: 10) {
            Image(systemName: "heart.fill")
                .font(.system(size: 15))
                .foregroundColor(NEColor.accentInk)
                .frame(width: 34, height: 34)
                .background(NEColor.accent)
                .clipShape(Circle())
            Text("Support Neutral Eats")
                .font(.system(size: 17, weight: .bold))
                .foregroundColor(NEColor.ink)
            Spacer(minLength: 4)
            Button {
                dismiss()
            } label: {
                Image(systemName: "xmark")
                    .font(.system(size: 11, weight: .bold))
                    .foregroundColor(NEColor.inkDim)
                    .frame(width: 28, height: 28)
                    .background(NEColor.panel2)
                    .clipShape(Circle())
            }
        }
        .padding(.horizontal, 16)
        .padding(.top, 16)
        .padding(.bottom, 6)
    }

    private var ladder: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Neutral Eats is free, with no ads — forever. Tips cover the servers and data. They buy nothing; the app is identical either way.")
                .font(.system(size: 14))
                .foregroundColor(NEColor.inkDim)
                .fixedSize(horizontal: false, vertical: true)

            if tips.loadState == .loading || tips.loadState == .idle {
                HStack {
                    Spacer()
                    ProgressView().tint(NEColor.accent)
                    Spacer()
                }
                .padding(.vertical, 18)
            } else if tips.products.isEmpty {
                Text("Tips aren't available right now — the app is free either way.")
                    .font(.system(size: 13.5))
                    .foregroundColor(NEColor.inkFaint)
            } else {
                LazyVGrid(
                    columns: [GridItem(.flexible()), GridItem(.flexible()), GridItem(.flexible())],
                    spacing: 10
                ) {
                    ForEach(tips.products, id: \.id) { product in
                        tipButton(product)
                    }
                }
            }

            if tips.purchasePending {
                Text("Your tip is pending approval — thank you for the thought; it lands when it clears.")
                    .font(.system(size: 12.5))
                    .foregroundColor(NEColor.inkFaint)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(.horizontal, 16)
        .padding(.top, 8)
    }

    private func tipButton(_ product: Product) -> some View {
        let busy = tips.purchasingID != nil
        let mine = tips.purchasingID == product.id
        return Button {
            Task { await tips.tip(product) }
        } label: {
            Group {
                if mine {
                    ProgressView().tint(NEColor.accentText)
                } else {
                    // The store's own localized price string —
                    // never a hardcoded amount (see TipStore).
                    Text(product.displayPrice)
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundColor(NEColor.accentText)
                }
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 13)
            .background(NEColor.panel2)
            .clipShape(RoundedRectangle(cornerRadius: 12))
            .overlay(RoundedRectangle(cornerRadius: 12).stroke(NEColor.line, lineWidth: 1))
        }
        .disabled(busy)
        .opacity(busy && !mine ? 0.55 : 1)
        .accessibilityLabel("Tip \(product.displayPrice)")
    }

    private var thankYou: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Thank you!")
                .font(.system(size: 20, weight: .bold))
                .foregroundColor(NEColor.ink)
            Text("Tips like yours keep the servers on and the results unsponsored — and the app is exactly the same as it was a minute ago. That's the point.")
                .font(.system(size: 14))
                .foregroundColor(NEColor.inkDim)
                .fixedSize(horizontal: false, vertical: true)
            Button {
                dismiss()
            } label: {
                Text("Done")
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundColor(NEColor.accentInk)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 12)
                    .background(NEColor.accent)
                    .clipShape(RoundedRectangle(cornerRadius: 12))
            }
            .padding(.top, 8)
        }
        .padding(.horizontal, 16)
        .padding(.top, 8)
    }
}
