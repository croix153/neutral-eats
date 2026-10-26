import SwiftUI
import MapKit
import CoreLocation

/// Main screen: dark map with venue dots, brand header + search +
/// filter chips on top, and a three-stop bottom sheet (collapsed /
/// peek / full) holding the distance-ranked list or the venue detail —
/// the native mirror of web/preview.html.
struct ContentView: View {
    @StateObject private var store = VenueStore()
    @StateObject private var location = LocationManager()

    @State private var filter: VenueFilter = .all
    @State private var searchText: String = ""
    @State private var selectedID: String? = nil
    @State private var detent: SheetDetent = .peek
    @State private var dragDelta: CGFloat = 0
    @State private var centerRequest: CenterRequest? = nil
    @State private var centerNonce: Int = 0
    @State private var wantsCenter: Bool = false
    @State private var toastMessage: String? = nil
    @State private var toastToken: Int = 0

    @Environment(\.openURL) private var openURL

    private var selectedVenue: Venue? {
        guard let selectedID = selectedID else { return nil }
        return store.venues.first { $0.id == selectedID }
    }

    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .bottom) {
                VenueMapView(
                    venues: store.venues,
                    selectedID: selectedID,
                    showsUserLocation: location.isAuthorized,
                    centerRequest: centerRequest,
                    onRegionSettled: { region in
                        store.regionSettled(region, filter: filter, search: searchText)
                    },
                    onSelectVenue: { id in
                        selectVenue(id: id, pan: false)
                    }
                )
                .ignoresSafeArea()

                // Thin loading bar across the very top (web parity).
                if store.isLoading {
                    VStack {
                        Rectangle()
                            .fill(NEColor.accent)
                            .frame(height: 2)
                        Spacer()
                    }
                    .ignoresSafeArea()
                }

                VStack {
                    header
                        .padding(.horizontal, 16)
                        .padding(.top, geo.safeAreaInsets.top + 6)
                    Spacer()
                }

                sheet(geo: geo)

                if let toastMessage = toastMessage {
                    Text(toastMessage)
                        .font(.system(size: 13.5, weight: .medium))
                        .foregroundColor(NEColor.ink)
                        .padding(.horizontal, 14)
                        .padding(.vertical, 9)
                        .background(NEColor.panel2)
                        .clipShape(Capsule())
                        .overlay(Capsule().stroke(NEColor.line, lineWidth: 1))
                        .padding(.bottom, sheetHeight(geo: geo) + 14)
                        .transition(.opacity)
                }
            }
            .background(NEColor.bg)
        }
        .preferredColorScheme(.dark)
        .onAppear {
            store.regionSettled(kHomeRegion, filter: filter, search: searchText)
        }
        .onChange(of: filter) { newFilter in
            closeDetail()
            store.reload(filter: newFilter, search: searchText, debounced: false)
        }
        .onChange(of: searchText) { newSearch in
            closeDetail()
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

    // MARK: - Header

    private var header: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top, spacing: 10) {
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
                .shadow(color: Color.black.opacity(0.65), radius: 4, x: 0, y: 1)

                Spacer()

                Button(action: nearMe) {
                    HStack(spacing: 6) {
                        Image(systemName: "location.fill")
                            .font(.system(size: 13))
                        Text("Near me")
                            .font(.system(size: 14, weight: .semibold))
                    }
                    .foregroundColor(location.isAuthorized ? NEColor.accent : NEColor.ink)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
                    .background(NEColor.panel)
                    .clipShape(Capsule())
                    .overlay(Capsule().stroke(NEColor.line, lineWidth: 1))
                }
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
            .background(NEColor.panel)
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
                .background(active ? NEColor.accent : NEColor.panel)
                .clipShape(Capsule())
                .overlay(Capsule().stroke(active ? NEColor.accent : NEColor.line, lineWidth: 1))
        }
    }

    // MARK: - Bottom sheet

    private enum SheetDetent {
        case collapsed, peek, full
    }

    private func detentHeight(_ detent: SheetDetent, geo: GeometryProxy) -> CGFloat {
        switch detent {
        case .collapsed: return 116
        case .peek: return geo.size.height * 0.46
        case .full: return geo.size.height * 0.82
        }
    }

    private func sheetHeight(geo: GeometryProxy) -> CGFloat {
        let base = detentHeight(detent, geo: geo)
        let proposed = base - dragDelta
        return min(max(proposed, 84), geo.size.height * 0.9)
    }

    private func makeSheetDrag(geo: GeometryProxy) -> some Gesture {
        DragGesture(minimumDistance: 4)
            .onChanged { value in
                dragDelta = value.translation.height
            }
            .onEnded { value in
                // Snap to the nearest stop using the flick's end point.
                let proposed = detentHeight(detent, geo: geo) - value.predictedEndTranslation.height
                let stops: [SheetDetent] = [.collapsed, .peek, .full]
                let nearest = stops.min {
                    abs(detentHeight($0, geo: geo) - proposed) < abs(detentHeight($1, geo: geo) - proposed)
                } ?? .peek
                withAnimation(.spring(response: 0.32, dampingFraction: 0.86)) {
                    detent = nearest
                    dragDelta = 0
                }
            }
    }

    private func sheet(geo: GeometryProxy) -> some View {
        VStack(spacing: 0) {
            // Handle — drag to move between stops, tap to toggle.
            VStack(spacing: 3) {
                Capsule()
                    .fill(NEColor.inkFaint.opacity(0.55))
                    .frame(width: 38, height: 4.5)
                Image(systemName: detent == .collapsed ? "chevron.up" : "chevron.down")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundColor(NEColor.inkFaint)
            }
            .frame(maxWidth: .infinity)
            .padding(.top, 8)
            .padding(.bottom, 5)
            .contentShape(Rectangle())
            .gesture(makeSheetDrag(geo: geo))
            .onTapGesture {
                withAnimation(.spring(response: 0.32, dampingFraction: 0.86)) {
                    detent = detent == .collapsed ? .peek : .collapsed
                }
            }

            if let venue = selectedVenue {
                detailView(venue)
            } else {
                sheetHead
                    .contentShape(Rectangle())
                    .gesture(makeSheetDrag(geo: geo))
                listContent
            }
            Spacer(minLength: 0)
        }
        .frame(height: sheetHeight(geo: geo))
        .frame(maxWidth: .infinity)
        .background(NEColor.panel)
        .clipShape(UnevenRoundedRectangle(topLeadingRadius: 20, topTrailingRadius: 20))
        .shadow(color: Color.black.opacity(0.45), radius: 16, x: 0, y: -4)
    }

    private var sheetHead: some View {
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

    // MARK: - List

    @ViewBuilder
    private var listContent: some View {
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
                    ProgressView().tint(NEColor.accent)
                    Spacer()
                }
                .padding(.top, 26)
            } else {
                stateBox(
                    title: "Nothing on the table here",
                    message: "No places found in this view. Try zooming out, clearing the search, or picking a different filter.",
                    buttonTitle: "Reset view",
                    action: resetAll
                )
            }
        } else {
            List {
                ForEach(store.venues) { venue in
                    Button {
                        selectVenue(id: venue.id, pan: true)
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
            .allowsHitTesting(detent != .collapsed)
        }
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

    // MARK: - Detail

    private func detailView(_ venue: Venue) -> some View {
        VStack(spacing: 0) {
            HStack {
                Button(action: closeDetail) {
                    HStack(spacing: 2) {
                        Image(systemName: "chevron.left")
                            .font(.system(size: 13, weight: .semibold))
                        Text("All results")
                            .font(.system(size: 15, weight: .semibold))
                    }
                    .foregroundColor(NEColor.accent)
                }
                Spacer()
                Button(action: closeDetail) {
                    Image(systemName: "xmark")
                        .font(.system(size: 12, weight: .bold))
                        .foregroundColor(NEColor.inkDim)
                        .frame(width: 30, height: 30)
                        .background(NEColor.panel2)
                        .clipShape(Circle())
                }
            }
            .padding(.horizontal, 18)
            .padding(.bottom, 4)

            ScrollView {
                VStack(alignment: .leading, spacing: 7) {
                    Text(venue.name ?? "Unnamed")
                        .font(.system(size: 22, weight: .bold))
                        .foregroundColor(NEColor.ink)
                    detailMeta(venue)
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

    private func selectVenue(id: String, pan: Bool) {
        selectedID = id
        withAnimation(.spring(response: 0.32, dampingFraction: 0.86)) {
            detent = .full
        }
        if pan, let venue = store.venues.first(where: { $0.id == id }),
           let coordinate = venue.coordinate {
            requestCenter(coordinate, span: nil)
        }
    }

    private func closeDetail() {
        selectedID = nil
    }

    private func resetAll() {
        searchText = ""
        filter = .all
        closeDetail()
        requestCenter(kHomeRegion.center, span: kHomeRegion.span)
    }

    private func requestCenter(_ coordinate: CLLocationCoordinate2D, span: MKCoordinateSpan?) {
        centerNonce += 1
        centerRequest = CenterRequest(coordinate: coordinate, span: span, nonce: centerNonce)
    }

    /// Near-me is the ONLY place location permission is requested —
    /// in context, at the moment he asks to be centered (web parity).
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
