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
        Task { @MainActor [weak self] in
            self?.point = p
        }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        // One-shot failures are non-fatal: Near-me simply doesn't move.
    }
}
