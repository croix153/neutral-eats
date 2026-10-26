import SwiftUI
import MapKit

/// Default view: Lake Mary, FL — same as the web preview's HOME.
let kHomeRegion = MKCoordinateRegion(
    center: CLLocationCoordinate2D(latitude: 28.713, longitude: -81.326),
    span: MKCoordinateSpan(latitudeDelta: 0.055, longitudeDelta: 0.055)
)

/// Imperative "center the map here" request; the nonce is what changes.
/// A non-nil span also resets the zoom (Reset view → home span).
struct CenterRequest: Equatable {
    var coordinate: CLLocationCoordinate2D
    var span: MKCoordinateSpan?
    var nonce: Int
    static func == (lhs: CenterRequest, rhs: CenterRequest) -> Bool {
        return lhs.nonce == rhs.nonce
    }
}

/// MKMapView bridge. The basemap follows the app theme (muted
/// standard, interface style forced on the view to match NEColor.mode);
/// venue dots are pre-rendered images so 500 annotations stay cheap.
struct VenueMapView: UIViewRepresentable {
    var venues: [Venue]
    var selectedID: String?
    var showsUserLocation: Bool
    var isDay: Bool
    var centerRequest: CenterRequest?
    var onRegionSettled: (MKCoordinateRegion) -> Void
    var onSelectVenue: (String) -> Void

    func makeCoordinator() -> Coordinator {
        return Coordinator()
    }

    func makeUIView(context: Context) -> MKMapView {
        let mapView = MKMapView()
        mapView.delegate = context.coordinator
        context.coordinator.parent = self
        mapView.overrideUserInterfaceStyle = isDay ? .light : .dark
        mapView.mapType = .mutedStandard
        mapView.pointOfInterestFilter = .excludingAll
        mapView.showsCompass = false
        mapView.showsUserLocation = showsUserLocation
        mapView.setRegion(kHomeRegion, animated: false)
        return mapView
    }

    func updateUIView(_ mapView: MKMapView, context: Context) {
        context.coordinator.parent = self
        mapView.overrideUserInterfaceStyle = isDay ? .light : .dark
        mapView.showsUserLocation = showsUserLocation
        context.coordinator.syncAnnotations(on: mapView, venues: venues, selectedID: selectedID)
        if let request = centerRequest, request.nonce != context.coordinator.lastCenterNonce {
            context.coordinator.lastCenterNonce = request.nonce
            var region = mapView.region
            region.center = request.coordinate
            if let span = request.span { region.span = span }
            mapView.setRegion(region, animated: true)
        }
    }

    final class VenueAnnotation: MKPointAnnotation {
        var venueID: String = ""
    }

    final class Coordinator: NSObject, MKMapViewDelegate {
        var parent: VenueMapView?
        var lastCenterNonce: Int = 0
        private var annotationsByID: [String: VenueAnnotation] = [:]

        func syncAnnotations(on mapView: MKMapView, venues: [Venue], selectedID: String?) {
            var incoming: [String: Venue] = [:]
            for venue in venues where venue.isMappable {
                if incoming[venue.id] == nil { incoming[venue.id] = venue }
            }
            // Remove annotations whose venues left the result set.
            for (id, annotation) in annotationsByID where incoming[id] == nil {
                mapView.removeAnnotation(annotation)
                annotationsByID[id] = nil
            }
            // Add new ones (and keep coordinates fresh).
            for (id, venue) in incoming {
                if let annotation = annotationsByID[id] {
                    annotation.coordinate = venue.coordinate!
                } else {
                    let annotation = VenueAnnotation()
                    annotation.venueID = id
                    annotation.coordinate = venue.coordinate!
                    annotation.title = venue.name
                    annotationsByID[id] = annotation
                    mapView.addAnnotation(annotation)
                }
            }
            // Selection is drawn by swapping the dot image.
            for (id, annotation) in annotationsByID {
                if let view = mapView.view(for: annotation) {
                    view.image = DotImages.image(selected: id == selectedID)
                }
            }
        }

        func mapView(_ mapView: MKMapView, viewFor annotation: MKAnnotation) -> MKAnnotationView? {
            if annotation is MKUserLocation { return nil }
            guard let venueAnnotation = annotation as? VenueAnnotation else { return nil }
            let reuseID = "venue-dot"
            let view = mapView.dequeueReusableAnnotationView(withIdentifier: reuseID)
                ?? MKAnnotationView(annotation: annotation, reuseIdentifier: reuseID)
            view.annotation = annotation
            view.image = DotImages.image(selected: venueAnnotation.venueID == parent?.selectedID)
            view.centerOffset = .zero
            view.canShowCallout = false
            return view
        }

        func mapView(_ mapView: MKMapView, didSelect view: MKAnnotationView) {
            guard let venueAnnotation = view.annotation as? VenueAnnotation else { return }
            mapView.deselectAnnotation(venueAnnotation, animated: false)
            parent?.onSelectVenue(venueAnnotation.venueID)
        }

        func mapView(_ mapView: MKMapView, regionDidChangeAnimated animated: Bool) {
            parent?.onRegionSettled(mapView.region)
        }
    }
}

/// Pre-rendered venue dots, matching the preview in both themes:
/// night — sakura fill #FF4D7E with a #070912 ring; day — deepened
/// fill #D92C57 with a white ring. The selected venue is a larger
/// --good dot with a white ring. Images are cached per theme and
/// rebuilt on the first request after NEColor.mode flips (the
/// coordinator re-assigns every annotation's image on each sync, so
/// a toggle repaints all dots).
enum DotImages {
    private static var cachedMode: NEThemeMode?
    private static var normalImg: UIImage?
    private static var selectedImg: UIImage?

    static func image(selected: Bool) -> UIImage {
        if cachedMode != NEColor.mode {
            cachedMode = NEColor.mode
            if NEColor.mode == .day {
                normalImg = DotImages.make(
                    fill: UIColor(red: 0xD9 / 255.0, green: 0x2C / 255.0, blue: 0x57 / 255.0, alpha: 0.95),
                    diameter: 13, ring: UIColor.white,
                    ringWidth: 1.5)
                selectedImg = DotImages.make(
                    fill: UIColor(red: 0x0B / 255.0, green: 0x7E / 255.0, blue: 0xA4 / 255.0, alpha: 1.0),
                    diameter: 19, ring: UIColor.white, ringWidth: 2)
            } else {
                normalImg = DotImages.make(
                    fill: UIColor(red: 1.0, green: 0x4D / 255.0, blue: 0x7E / 255.0, alpha: 0.95),
                    diameter: 13, ring: UIColor(red: 0x07 / 255.0, green: 0x09 / 255.0, blue: 0x12 / 255.0, alpha: 1.0),
                    ringWidth: 1.5)
                selectedImg = DotImages.make(
                    fill: UIColor(red: 0x38 / 255.0, green: 0xE1 / 255.0, blue: 1.0, alpha: 1.0),
                    diameter: 19, ring: UIColor.white, ringWidth: 2)
            }
        }
        return (selected ? selectedImg : normalImg) ?? UIImage()
    }

    private static func make(fill: UIColor, diameter: CGFloat, ring: UIColor, ringWidth: CGFloat) -> UIImage {
        let format = UIGraphicsImageRendererFormat()
        format.scale = 3
        let size = CGSize(width: diameter, height: diameter)
        let renderer = UIGraphicsImageRenderer(size: size, format: format)
        return renderer.image { _ in
            let rect = CGRect(origin: .zero, size: size).insetBy(dx: ringWidth / 2, dy: ringWidth / 2)
            let path = UIBezierPath(ovalIn: rect)
            path.lineWidth = ringWidth
            fill.setFill()
            ring.setStroke()
            path.fill()
            path.stroke()
        }
    }
}
