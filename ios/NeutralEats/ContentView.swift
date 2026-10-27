import SwiftUI
import MapKit
import CoreLocation

/// Main screen — map + ONE bottom card (redesigned again in
/// build 13, 2026-10-26, at Croix's direction: the Map/List
/// switcher is GONE):
///
///   - A fixed, solid header stack: wordmark, search, filter
///     chips. Content never slides under it.
///   - Below it, the map fills the whole region, and ONE card is
///     anchored to its bottom. The card has three forms:
///       summary  — result count + nearest venue + Near-me.
///                  Tap it (or drag up) and it expands…
///       list     — …to cover part of the map with the
///                  distance-ranked list. Tap the handle (or drag
///                  down) to collapse it back.
///       detail   — a venue is selected: the card becomes that
///                  venue's detail, wherever the tap came from.
///   - Tapping a location — a map dot, a label, or a list row —
///     selects it: the detail opens in the card AND the map snaps
///     to the venue at street zoom. One selection, one home for
///     detail, the camera always ends up looking at the place.
///
/// The map never leaves the hierarchy, so the card's forms all
/// share the camera, the loaded venues, and every other piece of
/// state — no refetch, no geometry negotiation.
struct ContentView: View {
    @StateObject private var store = VenueStore()
    @StateObject private var location = LocationManager()
    @StateObject private var theme = ThemeStore()

    @State private var filter: VenueFilter = .all
    @State private var searchText: String = ""
    @State private var selectedID: String? = nil
    @State private var cardExpanded: Bool = false
    @State private var centerRequest: CenterRequest? = nil
    @State private var centerNonce: Int = 0
    @State private var wantsCenter: Bool = false
    @State private var didLaunchLocate: Bool = false
    @State private var toastMessage: String? = nil
    @State private var toastToken: Int = 0

    @Environment(\.openURL) private var openURL
    @Environment(\.colorScheme) private var systemScheme

    var body: some View {
        // Resolve the theme first: the preference (auto = follow the
        // device) + the live system scheme decide the effective mode,
        // and NEColor.mode must be flipped before anything below
        // reads a color in this render pass.
        let eff = theme.effective(system: systemScheme)
        NEColor.mode = eff
        return VStack(spacing: 0) {
            header
            contentRegion
        }
        .background(NEColor.bg)
        .preferredColorScheme(theme.preference == .auto ? nil : (eff == .day ? .light : .dark))
        .overlay(alignment: .bottom) {
            if let toastMessage = toastMessage {
                Text(toastMessage)
                    .font(.system(size: 13.5, weight: .medium))
                    .foregroundColor(NEColor.ink)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 9)
                    .background(NEColor.panel2)
                    .clipShape(Capsule())
                    .overlay(Capsule().stroke(NEColor.line, lineWidth: 1))
                    .padding(.horizontal, 16)
                    .padding(.bottom, 14)
                    .transition(.opacity)
            }
        }
        .onAppear {
            store.regionSettled(kHomeRegion, filter: filter, search: searchText)
            launchLocate()
        }
        .onChange(of: filter) { newFilter in
            dismissDetail()
            store.reload(filter: newFilter, search: searchText, debounced: false)
        }
        .onChange(of: searchText) { newSearch in
            dismissDetail()
            store.reload(filter: filter, search: newSearch, debounced: true)
        }
        .onChange(of: location.point) { point in
            if wantsCenter, let point = point {
                wantsCenter = false
                requestCenter(point.coordinate, span: nil)
            }
        }
        .onChange(of: location.fixFailed) { failed in
            // A failed one-shot disarms the pending centering
            // (adversarial review, build 10) — otherwise a much
            // later, unrelated fix could yank the map unexpectedly.
            if failed { wantsCenter = false }
        }
        .onChange(of: theme.preference) { _ in
            // Keep the NEColor global in step from an event handler,
            // not only from body (adversarial review, build 10):
            // MapKit callbacks read the global outside SwiftUI's
            // render pass, and body evaluation order is not a
            // contract. The body assignment stays as a belt to
            // this suspenders.
            NEColor.mode = theme.effective(system: systemScheme)
        }
        .onChange(of: systemScheme) { newScheme in
            NEColor.mode = theme.effective(system: newScheme)
        }
        .onChange(of: location.authorization) { status in
            if wantsCenter && (status == .authorizedWhenInUse || status == .authorizedAlways) {
                location.requestOneShotLocation()
            }
        }
    }

    // MARK: - Header (fixed, solid — content never goes under it)

    private var header: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top, spacing: 8) {
                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 0) {
                        Text("neutral eats")
                            .font(.system(size: 29, weight: .bold, design: .serif))
                            .foregroundColor(NEColor.ink)
                        Text(".")
                            .font(.system(size: 29, weight: .bold, design: .serif))
                            .foregroundColor(NEColor.accent)
                    }
                    HStack(spacing: 0) {
                        Text("No ads. ")
                        Text("No bias.").foregroundColor(NEColor.inkDim)
                        Text(" Just food.")
                    }
                    .font(.system(size: 13, weight: .medium))
                    .foregroundColor(NEColor.ink)
                }
                Spacer()
                themeToggleButton
            }

            HStack(spacing: 8) {
                Image(systemName: "magnifyingglass")
                    .foregroundColor(NEColor.inkFaint)
                    .font(.system(size: 14, weight: .medium))
                TextField("", text: $searchText,
                          prompt: Text("Search tacos, sushi, a place name…")
                            .foregroundColor(NEColor.inkFaint))
                    .foregroundColor(NEColor.ink)
                    .submitLabel(.search)
                    .textInputAutocapitalization(.never)
                if !searchText.isEmpty {
                    Button {
                        searchText = ""
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundColor(NEColor.inkFaint)
                    }
                }
            }
            .padding(.horizontal, 11)
            .padding(.vertical, 10)
            .background(NEColor.panel2)
            .clipShape(RoundedRectangle(cornerRadius: 12))
            .overlay(RoundedRectangle(cornerRadius: 12).stroke(NEColor.line, lineWidth: 1))

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(VenueFilter.allCases) { chipFilter in
                        chip(for: chipFilter)
                    }
                }
            }
        }
        .padding(.horizontal, 16)
        .padding(.top, 10)
        .padding(.bottom, 12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(NEColor.panel)
        .overlay(alignment: .bottom) {
            ZStack(alignment: .leading) {
                Rectangle().fill(NEColor.line).frame(height: 1)
                // Thin loading bar along the header's bottom edge.
                if store.isLoading {
                    Rectangle()
                        .fill(NEColor.accent)
                        .frame(height: 2)
                }
            }
        }
    }

    /// Theme switcher, top-right of the header in the spot Croix
    /// marked (2026-10-26). Three states, cycled by tapping: auto
    /// (follow the device — the default, shown as a half-filled
    /// circle), day (sun), night (moon). The icon shows the CURRENT
    /// state; with three stops, "what you'll get next" icons would
    /// be guesswork.
    private var themeToggleButton: some View {
        Button {
            theme.cycle()
        } label: {
            Image(systemName: themeIcon)
                .font(.system(size: 16, weight: .semibold))
                .foregroundColor(NEColor.ink)
                .frame(width: 38, height: 38)
                .background(NEColor.panel2)
                .clipShape(Circle())
                .overlay(Circle().stroke(NEColor.line, lineWidth: 1))
        }
        .accessibilityLabel("Theme: \(theme.preference.rawValue). Tap to change.")
    }

    private var themeIcon: String {
        switch theme.preference {
        case .auto: return "circle.lefthalf.filled"
        case .day: return "sun.max.fill"
        case .night: return "moon.fill"
        }
    }

    private func chip(for chipFilter: VenueFilter) -> some View {
        let active = chipFilter == filter
        return Button {
            filter = chipFilter
        } label: {
            Text(chipFilter.label)
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(active ? NEColor.accentInk : NEColor.inkDim)
                .padding(.horizontal, 13)
                .padding(.vertical, 7)
                .background(active ? NEColor.accent : NEColor.panel2)
                .clipShape(Capsule())
                .overlay(Capsule().stroke(active ? NEColor.accent : NEColor.line, lineWidth: 1))
        }
    }

    // MARK: - Content region (map + the bottom card)

    private var contentRegion: some View {
        GeometryReader { geo in
            mapLayer(regionHeight: geo.size.height)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    // MARK: Map + card

    private func mapLayer(regionHeight: CGFloat) -> some View {
        ZStack(alignment: .bottom) {
            VenueMapView(
                venues: store.venues,
                selectedID: selectedID,
                showsUserLocation: location.isAuthorized,
                isDay: theme.effective(system: systemScheme) == .day,
                centerRequest: centerRequest,
                onRegionSettled: { region in
                    store.regionSettled(region, filter: filter, search: searchText)
                },
                onSelectVenue: { id in
                    selectVenue(id: id)
                },
                onDeselect: {
                    dismissDetail()
                }
            )
            // Full-bleed to the physical screen bottom, under the
            // home indicator — the same treatment the list layer
            // gets. Without this the map stopped at the bottom
            // safe-area boundary and the root background showed
            // through under the card as a dead black band.
            .ignoresSafeArea(edges: .bottom)

            // The card stays in the safe-area-aware layout, floating
            // above the home indicator, with a 38pt bottom padding:
            // MapKit draws its legal attribution at the map's
            // bottom-left corner, Apple's Maps terms require it to
            // stay fully visible, and at 12pt the card half-covered
            // it. Build 8 tried lifting the attribution instead via
            // the map's layout margins; Croix's verdict (2026-10-26)
            // was that he liked this build-7 arrangement better —
            // card high, label in its natural spot — so it stays.
            bottomCard(regionHeight: regionHeight)
                .padding(.horizontal, 12)
                .padding(.bottom, 38)
                .animation(.spring(response: 0.38, dampingFraction: 0.86), value: selectedID)
                .animation(.spring(response: 0.38, dampingFraction: 0.86), value: cardExpanded)
        }
    }

    /// Distances are expressed from YOU when a location fix
    /// exists (Croix, build 14) — "from map center" is surveyor
    /// language, not diner language. The map center stays as the
    /// fallback, and still drives the ranking order, which is
    /// about the spot being browsed.
    private var distanceOrigin: CLLocationCoordinate2D {
        location.point?.coordinate ?? store.center
    }

    private var distanceFromUser: Bool { location.point != nil }

    /// The current selection, resolved against the loaded results.
    /// Drives the card's detail form, the dot highlight, and the
    /// label accent — one selection, every surface.
    private var selectedVenue: Venue? {
        guard let selectedID = selectedID else { return nil }
        return store.venues.first { $0.id == selectedID }
    }

    /// THE bottom card — one object, three forms, morphed by state
    /// (build 13): summary, the expanded list, and the selected
    /// venue's detail. The panel chrome lives here, once; the
    /// forms are plain content stacked under the grab handle.
    @ViewBuilder
    private func bottomCard(regionHeight: CGFloat) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            cardHandle
            if let venue = selectedVenue {
                detailContent(venue)
            } else if cardExpanded {
                listContent
            } else {
                summaryContent
            }
        }
        .frame(height: (cardExpanded && selectedVenue == nil) ? regionHeight * 0.68 : nil)
        .background(NEColor.panel)
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .overlay(RoundedRectangle(cornerRadius: 16).stroke(NEColor.line, lineWidth: 1))
        .shadow(color: Color.black.opacity(0.45), radius: 14, x: 0, y: 4)
    }

    /// The grab handle: tap toggles the card (expand the summary,
    /// collapse the list, dismiss the detail); a vertical drag
    /// does the same by direction. It is the card's one control
    /// surface, so the forms below it stay clean.
    private var cardHandle: some View {
        HStack {
            Spacer()
            Capsule()
                .fill(NEColor.line)
                .frame(width: 38, height: 5)
            Spacer()
        }
        .padding(.top, 8)
        .padding(.bottom, 7)
        .contentShape(Rectangle())
        .onTapGesture {
            if selectedVenue != nil {
                dismissDetail()
            } else {
                cardExpanded.toggle()
            }
        }
        .gesture(
            DragGesture(minimumDistance: 14)
                .onEnded { value in
                    if value.translation.height < -36 {
                        if selectedVenue == nil { cardExpanded = true }
                    } else if value.translation.height > 36 {
                        if selectedVenue != nil {
                            dismissDetail()
                        } else {
                            cardExpanded = false
                        }
                    }
                }
        )
    }

    private var summaryContent: some View {
        HStack(spacing: 10) {
            Button {
                if store.loadFailed {
                    store.retry(filter: filter, search: searchText)
                } else {
                    cardExpanded = true
                }
            } label: {
                VStack(alignment: .leading, spacing: 2) {
                    cardHeadline
                    cardSubline
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)

            Button(action: nearMe) {
                HStack(spacing: 6) {
                    Image(systemName: "location.fill")
                        .font(.system(size: 13))
                    Text("Near me")
                        .font(.system(size: 14, weight: .semibold))
                }
                .foregroundColor(location.isAuthorized ? NEColor.accent : NEColor.ink)
                .padding(.horizontal, 12)
                .padding(.vertical, 9)
                .background(NEColor.panel2)
                .clipShape(Capsule())
                .overlay(Capsule().stroke(NEColor.line, lineWidth: 1))
            }
        }
        .padding(.horizontal, 14)
        .padding(.bottom, 12)
    }

    @ViewBuilder
    private var cardHeadline: some View {
        if store.loadFailed {
            Text("Couldn't load places")
                .font(.system(size: 15.5, weight: .bold))
                .foregroundColor(NEColor.ink)
        } else if store.isLoading && store.venues.isEmpty {
            Text("Finding food near you…")
                .font(.system(size: 15.5, weight: .bold))
                .foregroundColor(NEColor.ink)
        } else {
            let n = store.venues.count
            (Text(displayCount)
                .font(.system(size: 15.5, weight: .bold))
                .foregroundColor(NEColor.accentText)
                + Text(" \(n == 1 ? "place" : "places") in viewport")
                .font(.system(size: 15.5, weight: .bold))
                .foregroundColor(NEColor.ink))
        }
    }

    /// At the server cap the honest count is "500+", not "500"
    /// (Croix, 2026-10-26; the web preview renders it the same way).
    private var displayCount: String {
        let n = store.venues.count
        return n >= APIClient.limit ? "\(APIClient.limit)+" : "\(n)"
    }

    /// The card's second line exists only for the failure state
    /// (Croix, build 15): the "Nearest: …" subtitle is gone — the
    /// headline count is the whole message now.
    @ViewBuilder
    private var cardSubline: some View {
        if store.loadFailed {
            Text("Tap to try again")
                .font(.system(size: 12.5))
                .foregroundColor(NEColor.accentText)
        }
    }

    // MARK: List (the card's expanded form)

    private var listContent: some View {
        Group {
            if store.loadFailed {
                stateBox(
                    title: "The kitchen hit a snag",
                    message: "We couldn't load places just now. Check your connection and try again.",
                    buttonTitle: "Try again",
                    action: { store.retry(filter: filter, search: searchText) }
                )
            } else if store.venues.isEmpty {
                if store.isLoading {
                    VStack {
                        Spacer()
                        ProgressView().tint(NEColor.accent)
                        Spacer()
                    }
                    .frame(maxWidth: .infinity)
                } else {
                    stateBox(
                        title: "Nothing on the table here",
                        message: "No places found in this view. Try zooming out, clearing the search, or picking a different filter.",
                        buttonTitle: "Reset view",
                        action: resetAll
                    )
                }
            } else {
                VStack(spacing: 0) {
                    listHead
                    venueList
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private var listHead: some View {
        VStack(alignment: .leading, spacing: 3) {
            countText
            HStack(spacing: 6) {
                Image(systemName: "checkmark.shield.fill")
                    .font(.system(size: 12))
                    .foregroundColor(NEColor.good)
                Text("Ranked by distance. Nothing is sponsored — ever.")
                    .font(.system(size: 12.5))
                    .foregroundColor(NEColor.inkDim)
            }
            if store.serverCount >= APIClient.limit {
                Text("Showing 500 results — zoom in for more.")
                    .font(.system(size: 12))
                    .foregroundColor(NEColor.accentText)
                    .padding(.top, 1)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 18)
        .padding(.top, 12)
        .padding(.bottom, 10)
        .overlay(alignment: .bottom) {
            Rectangle().fill(NEColor.line).frame(height: 1)
        }
    }

    private var countText: Text {
        if store.isLoading && store.venues.isEmpty {
            return Text("Finding food near you…")
                .font(.system(size: 17, weight: .bold))
                .foregroundColor(NEColor.ink)
        }
        let n = store.venues.count
        if !searchText.isEmpty {
            return (Text(displayCount)
                .font(.system(size: 17, weight: .bold))
                .foregroundColor(NEColor.accentText)
                + Text(" \(n == 1 ? "match" : "matches") for “\(searchText)” in viewport")
                .font(.system(size: 17, weight: .bold))
                .foregroundColor(NEColor.ink))
        }
        return (Text(displayCount)
            .font(.system(size: 17, weight: .bold))
            .foregroundColor(NEColor.accentText)
            + Text(" \(n == 1 ? "place" : "places") in viewport")
            .font(.system(size: 17, weight: .bold))
            .foregroundColor(NEColor.ink))
    }

    private var venueList: some View {
        List {
            ForEach(store.venues) { venue in
                // Tapping a row selects the venue (build 13): the
                // card swaps the list for the venue's detail and
                // the map snaps to it at street zoom. Tapping the
                // selected row again lets it go.
                Button {
                    selectVenue(id: venue.id)
                } label: {
                    venueRow(venue)
                }
                .buttonStyle(.plain)
                .listRowBackground(venue.id == selectedID ? NEColor.panel2 : NEColor.panel)
                .listRowSeparatorTint(NEColor.line)
                .listRowInsets(EdgeInsets(top: 11, leading: 18, bottom: 11, trailing: 18))
            }
        }
        .listStyle(.plain)
        .scrollContentBackground(.hidden)
        .background(Color.clear)
        .animation(.spring(response: 0.38, dampingFraction: 0.86), value: selectedID)
    }

    private func venueRow(_ venue: Venue) -> some View {
        HStack(alignment: .top, spacing: 10) {
            VStack(alignment: .leading, spacing: 2) {
                Text(venue.name ?? "Unnamed")
                    .font(.system(size: 15.5, weight: .semibold))
                    .foregroundColor(NEColor.ink)
                    .lineLimit(1)
                Text(venue.metaLine)
                    .font(.system(size: 13))
                    .foregroundColor(NEColor.inkDim)
                    .lineLimit(1)
                if let address = venue.address {
                    Text(address)
                        .font(.system(size: 12.5))
                        .foregroundColor(NEColor.inkFaint)
                        .lineLimit(1)
                }
            }
            Spacer(minLength: 4)
            VStack(alignment: .trailing, spacing: 3) {
                Text(Venue.formatDistance(venue.distanceMiles(from: distanceOrigin)))
                    .font(.system(size: 13, weight: .bold))
                    .foregroundColor(NEColor.accentText)
                if !venue.ratingPriceLine.isEmpty {
                    ratingPriceText(venue)
                        .font(.system(size: 12.5))
                        .foregroundColor(NEColor.inkDim)
                }
            }
        }
    }

    /// ratingPriceLine with the ★ tinted accent (web parity).
    private func ratingPriceText(_ venue: Venue) -> Text {
        var result: Text? = nil
        if venue.ratingValue != nil {
            result = Text("★").foregroundColor(NEColor.accentText)
                + Text(String(venue.ratingPriceLine.dropFirst(1)))
        }
        return result ?? Text(venue.ratingPriceLine)
    }

    private func stateBox(title: String, message: String, buttonTitle: String, action: @escaping () -> Void) -> some View {
        VStack(spacing: 6) {
            Text(title)
                .font(.system(size: 17, weight: .semibold))
                .foregroundColor(NEColor.ink)
            Text(message)
                .font(.system(size: 14))
                .foregroundColor(NEColor.inkDim)
                .multilineTextAlignment(.center)
            Button(action: action) {
                Text(buttonTitle)
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(NEColor.accentText)
                    .padding(.horizontal, 16)
                    .padding(.vertical, 8)
                    .overlay(Capsule().stroke(NEColor.accentText, lineWidth: 1))
                    .clipShape(Capsule())
            }
            .padding(.top, 6)
            Spacer()
        }
        .padding(.top, 30)
        .padding(.horizontal, 24)
        .frame(maxWidth: .infinity)
    }

    // MARK: - Detail (the card's selected form)

    /// The detail form: the bottom card itself becomes the venue —
    /// name + close in the header row, the detail body underneath.
    /// Same card, same anchor, so the morph reads as one object
    /// changing, not a new layer.
    private func detailContent(_ venue: Venue) -> some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack(alignment: .top, spacing: 8) {
                Text(venue.name ?? "Unnamed")
                    .font(.system(size: 17, weight: .bold))
                    .foregroundColor(NEColor.ink)
                    .lineLimit(2)
                Spacer(minLength: 4)
                Button {
                    dismissDetail()
                } label: {
                    Image(systemName: "xmark")
                        .font(.system(size: 11, weight: .bold))
                        .foregroundColor(NEColor.inkDim)
                        .frame(width: 28, height: 28)
                        .background(NEColor.panel2)
                        .clipShape(Circle())
                }
            }
            detailBody(venue)
        }
        .padding(.horizontal, 14)
        .padding(.bottom, 12)
    }

    /// Everything below the name in the detail form: meta, pills,
    /// cuisine, address, actions, provenance.
    private func detailBody(_ venue: Venue) -> some View {
        VStack(alignment: .leading, spacing: 7) {
            detailMeta(venue)
            if venue.tableService == true {
                Text("Full service")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundColor(NEColor.good)
                    .padding(.horizontal, 9)
                    .padding(.vertical, 4)
                    .background(NEColor.panel2)
                    .clipShape(Capsule())
                    .overlay(Capsule().stroke(NEColor.line, lineWidth: 1))
            }
            if let cuisine = venue.cuisine {
                Text(cuisine)
                    .font(.system(size: 14))
                    .foregroundColor(NEColor.inkDim)
            }
            if let address = venue.address {
                Text(address)
                    .font(.system(size: 14))
                    .foregroundColor(NEColor.inkDim)
            }
            Text("\(Venue.formatDistance(venue.distanceMiles(from: distanceOrigin))) from \(distanceFromUser ? "you" : "map center")")
                .font(.system(size: 13))
                .foregroundColor(NEColor.inkFaint)

            HStack(spacing: 10) {
                callButton(venue)
                websiteButton(venue)
                directionsButton(venue)
            }
            .padding(.top, 8)

            if let sourceLine = venue.sourceLine {
                Text(sourceLine)
                    .font(.system(size: 12))
                    .foregroundColor(NEColor.inkFaint)
                    .padding(.top, 8)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func detailMeta(_ venue: Venue) -> some View {
        var parts: [String] = []
        if !venue.ratingPriceLine.isEmpty { parts.append(venue.ratingPriceLine) }
        // The type appears only when the cuisine doesn't already
        // say it — no "Restaurant" echo over a cuisine that starts
        // with the same word (Croix, 2026-10-26).
        if let t = venue.dedupedTypeLabel { parts.append(t) }
        let joined = parts.joined(separator: " · ")
        return Group {
            if parts.isEmpty {
                EmptyView()
            } else if joined.hasPrefix("★") {
                HStack(spacing: 0) {
                    Text("★").foregroundColor(NEColor.accentText)
                    Text(String(joined.dropFirst(1))).foregroundColor(NEColor.inkDim)
                }
            } else {
                Text(joined).foregroundColor(NEColor.inkDim)
            }
        }
        .font(.system(size: 14))
    }

    private func actionLabel(_ title: String, enabled: Bool, primary: Bool) -> some View {
        Text(title)
            .font(.system(size: 15, weight: .semibold))
            .foregroundColor(
                !enabled ? NEColor.inkFaint : (primary ? NEColor.accentInk : NEColor.ink))
            .frame(maxWidth: .infinity)
            .padding(.vertical, 12)
            .background(!enabled ? NEColor.panel2 : (primary ? NEColor.accent : NEColor.panel2))
            .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    @ViewBuilder
    private func callButton(_ venue: Venue) -> some View {
        if let phone = venue.sanitizedPhone, let url = URL(string: "tel:\(phone)") {
            Button { openURL(url) } label: { actionLabel("Call", enabled: true, primary: true) }
        } else {
            actionLabel("No phone", enabled: false, primary: false)
        }
    }

    @ViewBuilder
    private func websiteButton(_ venue: Venue) -> some View {
        if let url = venue.websiteURL {
            Button { openURL(url) } label: { actionLabel("Website", enabled: true, primary: false) }
        } else {
            actionLabel("No website", enabled: false, primary: false)
        }
    }

    @ViewBuilder
    private func directionsButton(_ venue: Venue) -> some View {
        if let url = venue.directionsURL {
            Button { openURL(url) } label: { actionLabel("Directions", enabled: true, primary: false) }
        } else {
            actionLabel("Directions", enabled: false, primary: false)
        }
    }

    // MARK: - Actions

    /// One selection gesture everywhere: tap a dot, a label, or a
    /// list row to select; tap the same one again to let it go.
    /// Selecting ALSO snaps the map to the venue at street zoom
    /// (build 13, Croix): wherever the tap came from, you end up
    /// looking at the place while its detail opens in the card.
    /// The span matches the label threshold, so the venue's name
    /// is rendered on its dot when the camera lands.
    private func selectVenue(id: String) {
        if selectedID == id {
            selectedID = nil
            return
        }
        selectedID = id
        if let venue = store.venues.first(where: { $0.id == id }),
           let coordinate = venue.coordinate {
            requestCenter(coordinate,
                          span: MKCoordinateSpan(latitudeDelta: 0.005, longitudeDelta: 0.005))
        }
    }

    private func dismissDetail() {
        selectedID = nil
    }

    private func resetAll() {
        searchText = ""
        filter = .all
        dismissDetail()
        cardExpanded = false
        requestCenter(kHomeRegion.center, span: kHomeRegion.span)
    }

    private func requestCenter(_ coordinate: CLLocationCoordinate2D, span: MKCoordinateSpan?) {
        centerNonce += 1
        centerRequest = CenterRequest(coordinate: coordinate, span: span, nonce: centerNonce)
    }

    /// Cold-launch default (Croix, 2026-10-26 — web parity): the app
    /// opens centered on the user. Already-granted permission centers
    /// as soon as the one-shot fix lands; notDetermined gets the system
    /// permission prompt as part of this attempt (iOS asks once, then
    /// remembers the decision); denied/restricted falls back to the
    /// home region quietly — Near-me is where that case gets explained.
    /// Runs once per process: a later .onAppear must never yank
    /// the map back to the user unasked.
    private func launchLocate() {
        guard !didLaunchLocate else { return }
        didLaunchLocate = true
        switch location.authorization {
        case .authorizedWhenInUse, .authorizedAlways:
            wantsCenter = true
            location.requestOneShotLocation()
        case .notDetermined:
            wantsCenter = true
            location.requestPermission()
        default:
            break
        }
    }

    /// Near-me is the manual re-center. Permission is also requested
    /// on cold launch (launchLocate, above); this remains the place a
    /// denied user hears why centering is unavailable.
    private func nearMe() {
        switch location.authorization {
        case .authorizedWhenInUse, .authorizedAlways:
            // Only a FRESH fix counts as "me" (adversarial review,
            // build 10): the launch fix from an hour and a suburb
            // ago is not where the user is now.
            if let point = location.point, let fixedAt = location.pointDate,
               Date().timeIntervalSince(fixedAt) < 90 {
                requestCenter(point.coordinate, span: nil)
            } else {
                wantsCenter = true
                location.requestOneShotLocation()
            }
        case .notDetermined:
            wantsCenter = true
            location.requestPermission()
        case .denied, .restricted:
            showToast("Location is off for neutral eats — turn it on in Settings to use Near me.")
        @unknown default:
            break
        }
    }

    private func showToast(_ message: String) {
        toastToken += 1
        let token = toastToken
        withAnimation { toastMessage = message }
        Task {
            try? await Task.sleep(nanoseconds: 3_200_000_000)
            if toastToken == token {
                withAnimation { toastMessage = nil }
            }
        }
    }
}
