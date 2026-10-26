import Foundation
import MapKit
import CoreLocation

/// Owns the venue list and the fetch lifecycle, mirroring the web
/// preview: fetches are keyed to the visible map region (debounced
/// 350 ms like the web's moveend handler), in-flight requests are
/// cancelled when superseded, and the displayed order is ALWAYS
/// distance from the map center — never the API's source-priority
/// order. Neutrality is the product.
@MainActor
final class VenueStore: ObservableObject {
    @Published private(set) var venues: [Venue] = []
    @Published private(set) var serverCount: Int = 0
    @Published private(set) var isLoading: Bool = false
    @Published private(set) var loadFailed: Bool = false

    /// Map center the distances are ranked from (published so rows and
    /// the detail view re-render their distances as it settles).
    @Published private(set) var center: CLLocationCoordinate2D =
        CLLocationCoordinate2D(latitude: 28.713, longitude: -81.326)

    private let client = APIClient()
    private var region: MKCoordinateRegion?
    private var fetchTask: Task<Void, Never>?
    private var debounceTask: Task<Void, Never>?
    private var fetchSeq: Int = 0

    /// The map settled on a new region: re-sort what we have from the
    /// new center immediately (honest distances while panning, like
    /// the web's move handler), then fetch the new bbox, debounced.
    func regionSettled(_ newRegion: MKCoordinateRegion, filter: VenueFilter, search: String) {
        region = newRegion
        center = newRegion.center
        resort()
        scheduleLoad(filter: filter, search: search, delayNanoseconds: 350_000_000)
    }

    /// Filter changed: refetch right away. Search changed: refetch
    /// debounced so typing doesn't hammer the API.
    func reload(filter: VenueFilter, search: String, debounced: Bool) {
        scheduleLoad(filter: filter, search: search,
                     delayNanoseconds: debounced ? 350_000_000 : 0)
    }

    func retry(filter: VenueFilter, search: String) {
        scheduleLoad(filter: filter, search: search, delayNanoseconds: 0)
    }

    private func scheduleLoad(filter: VenueFilter, search: String, delayNanoseconds: UInt64) {
        debounceTask?.cancel()
        debounceTask = Task { [weak self] in
            if delayNanoseconds > 0 {
                try? await Task.sleep(nanoseconds: delayNanoseconds)
            }
            guard !Task.isCancelled else { return }
            self?.load(filter: filter, search: search)
        }
    }

    private func load(filter: VenueFilter, search: String) {
        guard let region = region else { return }
        fetchTask?.cancel()
        fetchSeq += 1
        let seq = fetchSeq
        isLoading = true
        let clientType = filter.clientType
        let centerSnapshot = region.center
        fetchTask = Task { [weak self] in
            guard let self = self else { return }
            do {
                let result = try await self.client.fetch(
                    region: region, serverType: filter.serverType,
                    search: search.isEmpty ? nil : search)
                guard !Task.isCancelled, seq == self.fetchSeq else { return }
                var list = result.venues.filter { $0.isMappable }
                if let clientType = clientType {
                    list = list.filter { $0.type == clientType }
                }
                list.sort {
                    $0.distanceMiles(from: centerSnapshot) < $1.distanceMiles(from: centerSnapshot)
                }
                self.venues = list
                self.serverCount = result.count
                self.loadFailed = false
                self.isLoading = false
            } catch {
                if (error as? URLError)?.code == .cancelled || error is CancellationError {
                    return
                }
                guard !Task.isCancelled, seq == self.fetchSeq else { return }
                self.venues = []
                self.serverCount = 0
                self.loadFailed = true
                self.isLoading = false
            }
        }
    }

    private func resort() {
        let c = center
        venues.sort { $0.distanceMiles(from: c) < $1.distanceMiles(from: c) }
    }
}
