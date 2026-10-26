import SwiftUI
import MapKit
import CoreLocation

/// Main screen — two-state layout (redesigned 2026-10-26, replacing
/// the three-stop bottom sheet that collided with the top UI and
/// left a dead band at the bottom):
///
///   - A fixed, solid header stack: wordmark, search, filter chips,
///     and the Map/List switch. Content never slides under it.
///   - Below it, ONE content region with two states. Map state: the
///     map fills the region, with one compact card (result count +
///     nearest venue + Near-me) anchored to the region's bottom.
///     List state: the distance-ranked list fills the entire region,
///     edge to edge, down to the physical screen bottom.
///   - Venue detail is a modal .sheet from both states.
///
/// The map layer stays in the hierarchy underneath the list layer,
/// so switching states preserves the camera, the loaded venues, and
/// every other piece of state — no refetch, no geometry negotiation.
struct ContentView: View {
    @StateObject private var store = VenueStore()
    @StateObject private var location = LocationManager()
    @StateObject private var theme = ThemeStore()

    @State private var filter: VenueFilter = .all
    @State private var searchText: String = ""
    @State private var selectedID: String? = nil
    @State private var detailVenue: Venue? = nil
    @State private var mode: ContentMode = .map
    @State private var centerRequest: CenterRequest? = nil
    @State private var centerNonce: Int = 0
    @State private var wantsCenter: Bool = false
    @State private var didLaunchLocate: Bool = false
    @State private var toastMessage: String? = nil
    @State private var toastToken: Int = 0

    @Environment(\.openURL) private var openURL

    private enum ContentMode {
        case map, list
    }

    var body: some View {
        VStack(spacing: 0) {
            header
            contentRegion
        }
        .background(NEColor.bg)
        .preferredColorScheme(theme.mode == .day ? .light : .dark)
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
        .sheet(item: $detailVenue) { venue in
            detailSheet(venue)
                .presentationDetents([.medium, .large])
                .presentationDragIndicator(.visible)
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

            modePicker
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

    /// Day/night switcher, top-right of the header in the spot Croix
    /// marked (2026-10-26). Like the web's toggle, the icon shows the
    /// theme you'll switch TO: sun at night, moon by day.
    private var themeToggleButton: some View {
        Button {
            theme.toggle()
        } label: {
            Image(systemName: theme.mode == .day ? "moon.fill" : "sun.max.fill")
                .font(.system(size: 16, weight: .semibold))
                .foregroundColor(NEColor.ink)
                .frame(width: 38, height: 38)
                .background(NEColor.panel2)
                .clipShape(Circle())
                .overlay(Circle().stroke(NEColor.line, lineWidth: 1))
        }
        .accessibilityLabel(theme.mode == .day ? "Switch to night theme" : "Switch to day theme")
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

    /// Map/List switch — custom segmented control in the Tokyo
    /// palette (the native control can't take the brand colors).
    private var modePicker: some View {
        HStack(spacing: 4) {
            modeButton(.map, title: "Map", icon: "map")
            modeButton(.list, title: "List", icon: "list.bullet")
        }
        .padding(4)
        .background(NEColor.panel2)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(NEColor.line, lineWidth: 1))
    }

    private func modeButton(_ target: ContentMode, title: String, icon: String) -> some View {
        let active = mode == target
        return Button {
            mode = target
        } label: {
            HStack(spacing: 6) {
                Image(systemName: icon)
                    .font(.system(size: 13, weight: .semibold))
                Text(title)
                    .font(.system(size: 14, weight: .semibold))
            }
            .foregroundColor(active ? NEColor.accentInk : NEColor.inkDim)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 7)
            .background(active ? NEColor.accent : Color.clear)
            .clipShape(RoundedRectangle(cornerRadius: 9))
        }
    }

    // MARK: - Content region (one region, two states)

    private var contentRegion: some View {
        ZStack {
            mapLayer
            if mode == .list {
                listLayer
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    // MARK: Map state

    private var mapLayer: some View {
        ZStack(alignment: .bottom) {
            VenueMapView(
                venues: store.venues,
                selectedID: selectedID,
                showsUserLocation: location.isAuthorized,
                isDay: theme.mode == .day,
                centerRequest: centerRequest,
                onRegionSettled: { region in
                    store.regionSettled(region, filter: filter, search: searchText)
                },
                onSelectVenue: { id in
                    presentDetail(id: id)
                }
            )
            // Full-bleed to the physical screen bottom, under the
            // home indicator — the same treatment the list layer
            // gets. Without this the map stopped at the bottom
            // safe-area boundary and the root background showed
            // through under the card as a dead black band.
            .ignoresSafeArea(edges: .bottom)

            // The card stays in the safe-area-aware layout, floating
            // above the home indicator. Its bottom padding is 38, not
            // 12: MapKit draws its legal attribution at the map's
            // bottom-left corner, and Apple's Maps terms require that
            // attribution to stay fully visible — the 12pt card half-
            // covered it (Croix's screenshot, 2026-10-26). We move
            // OUR card up; the attribution is never hidden or moved.
            mapCard
                .padding(.horizontal, 12)
                .padding(.bottom, 38)
        }
    }

    /// Compact card anchored to the region's bottom edge: result
    /// count + nearest venue (tap → List state), and Near-me.
    private var mapCard: some View {
        HStack(spacing: 10) {
            Button {
                if store.loadFailed {
                    store.retry(filter: filter, search: searchText)
                } else {
                    mode = .list
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
        .padding(.vertical, 11)
        .background(NEColor.panel)
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .overlay(RoundedRectangle(cornerRadius: 16).stroke(NEColor.line, lineWidth: 1))
        .shadow(color: Color.black.opacity(0.45), radius: 14, x: 0, y: 4)
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
            (Text("\(n)")
                .font(.system(size: 15.5, weight: .bold))
                .foregroundColor(NEColor.accent)
                + Text(" \(n == 1 ? "place" : "places") near this spot")
                .font(.system(size: 15.5, weight: .bold))
                .foregroundColor(NEColor.ink))
        }
    }

    @ViewBuilder
    private var cardSubline: some View {
        if store.loadFailed {
            Text("Tap to try again")
                .font(.system(size: 12.5))
                .foregroundColor(NEColor.accent)
        } else if let nearest = store.venues.first {
            let distance = Venue.formatDistance(nearest.distanceMiles(from: store.center))
            (Text("Nearest: ")
                .foregroundColor(NEColor.inkFaint)
                + Text(nearest.name ?? "Unnamed")
                .foregroundColor(NEColor.inkDim)
                + Text(distance.isEmpty ? "" : " · \(distance)")
                .foregroundColor(NEColor.inkDim))
                .font(.system(size: 12.5))
                .lineLimit(1)
        } else if !store.isLoading {
            Text("No places in this view")
                .font(.system(size: 12.5))
                .foregroundColor(NEColor.inkFaint)
        }
    }

    // MARK: List state

    private var listLayer: some View {
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
        .background(NEColor.panel)
        // The list reaches the physical screen bottom (standard
        // list insets keep the last row clear of the home
        // indicator) — no dead band under the content.
        .ignoresSafeArea(edges: .bottom)
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
                    .foregroundColor(NEColor.accent)
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
            return (Text("\(n)")
                .font(.system(size: 17, weight: .bold))
                .foregroundColor(NEColor.accent)
                + Text(" \(n == 1 ? "match" : "matches") for “\(searchText)” nearby")
                .font(.system(size: 17, weight: .bold))
                .foregroundColor(NEColor.ink))
        }
        return (Text("\(n)")
            .font(.system(size: 17, weight: .bold))
            .foregroundColor(NEColor.accent)
            + Text(" \(n == 1 ? "place" : "places") near this spot")
            .font(.system(size: 17, weight: .bold))
            .foregroundColor(NEColor.ink))
    }

    private var venueList: some View {
        List {
            ForEach(store.venues) { venue in
                Button {
                    presentDetail(id: venue.id)
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
                Text(Venue.formatDistance(venue.distanceMiles(from: store.center)))
                    .font(.system(size: 13, weight: .bold))
                    .foregroundColor(NEColor.accent)
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
            result = Text("★").foregroundColor(NEColor.accent)
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
                    .foregroundColor(NEColor.accent)
                    .padding(.horizontal, 16)
                    .padding(.vertical, 8)
                    .overlay(Capsule().stroke(NEColor.accent, lineWidth: 1))
                    .clipShape(Capsule())
            }
            .padding(.top, 6)
            Spacer()
        }
        .padding(.top, 30)
        .padding(.horizontal, 24)
        .frame(maxWidth: .infinity)
    }

    // MARK: - Detail (modal sheet, from both states)

    private func detailSheet(_ venue: Venue) -> some View {
        VStack(spacing: 0) {
            HStack {
                Spacer()
                Button {
                    detailVenue = nil
                } label: {
                    Image(systemName: "xmark")
                        .font(.system(size: 12, weight: .bold))
                        .foregroundColor(NEColor.inkDim)
                        .frame(width: 30, height: 30)
                        .background(NEColor.panel2)
                        .clipShape(Circle())
                }
            }
            .padding(.horizontal, 18)
            .padding(.top, 14)
            .padding(.bottom, 4)

            ScrollView {
                VStack(alignment: .leading, spacing: 7) {
                    Text(venue.name ?? "Unnamed")
                        .font(.system(size: 22, weight: .bold))
                        .foregroundColor(NEColor.ink)
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
                    Text("\(Venue.formatDistance(venue.distanceMiles(from: store.center))) from map center")
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
                .padding(.horizontal, 18)
                .padding(.bottom, 26)
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(NEColor.panel)
    }

    private func detailMeta(_ venue: Venue) -> some View {
        var parts: [String] = []
        if !venue.ratingPriceLine.isEmpty { parts.append(venue.ratingPriceLine) }
        parts.append(venue.typeLabel)
        let joined = parts.joined(separator: " · ")
        return Group {
            if joined.hasPrefix("★") {
                HStack(spacing: 0) {
                    Text("★").foregroundColor(NEColor.accent)
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

    private func presentDetail(id: String) {
        selectedID = id
        detailVenue = store.venues.first { $0.id == id }
    }

    private func dismissDetail() {
        detailVenue = nil
        selectedID = nil
    }

    private func resetAll() {
        searchText = ""
        filter = .all
        dismissDetail()
        mode = .map
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
    /// Runs once per process: a later .onAppear (e.g. after a sheet
    /// dismisses) must never yank the map back.
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
            if let point = location.point {
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
