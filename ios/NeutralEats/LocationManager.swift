import Foundation
import CoreLocation

struct GeoPoint: Equatable {
    var latitude: Double
    var longitude: Double
    var coordinate: CLLocationCoordinate2D {
        return CLLocationCoordinate2D(latitude: latitude, longitude: longitude)
    }
}

/// Thin CoreLocation wrapper. Permission is requested on cold launch
/// (ContentView.launchLocate) and from the Near-me re-center — the
/// same rule as the web preview, which locates on cold load and asks
/// as part of that attempt (Croix, 2026-10-26).
@MainActor
final class LocationManager: NSObject, ObservableObject {
    @Published private(set) var authorization: CLAuthorizationStatus
    @Published private(set) var point: GeoPoint?
    /// When the current point was fixed, and whether the last
    /// one-shot request failed (adversarial review, build 10: a
    /// stale launch fix must not be treated as "where I am now",
    /// and a failed one-shot must be able to disarm the caller's
    /// pending centering request instead of firing much later).
    @Published private(set) var pointDate: Date?
    @Published private(set) var fixFailed: Bool = false

    private let manager = CLLocationManager()

    var isAuthorized: Bool {
        return authorization == .authorizedWhenInUse || authorization == .authorizedAlways
    }

    override init() {
        authorization = manager.authorizationStatus
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyHundredMeters
    }

    func requestPermission() {
        manager.requestWhenInUseAuthorization()
    }

    func requestOneShotLocation() {
        manager.requestLocation()
    }
}

extension LocationManager: CLLocationManagerDelegate {
    nonisolated func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        let status = manager.authorizationStatus
        Task { @MainActor [weak self] in
            self?.authorization = status
        }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let loc = locations.last else { return }
        let p = GeoPoint(latitude: loc.coordinate.latitude, longitude: loc.coordinate.longitude)
        let when = loc.timestamp
        Task { @MainActor [weak self] in
            self?.point = p
            self?.pointDate = when
            self?.fixFailed = false
        }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        // Non-fatal — but recorded, so a caller waiting to center
        // on the fix can stand down instead of staying armed.
        Task { @MainActor [weak self] in
            self?.fixFailed = true
        }
    }
}
