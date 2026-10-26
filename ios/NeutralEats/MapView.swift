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

/// MKMapView bridge. The dark basemap comes from MapKit's own dark
/// rendering (muted standard, dark interface style forced on the view);
/// venue dots are pre-rendered images so 500 annotations stay cheap.
struct VenueMapView: UIViewRepresentable {
    var venues: [Venue]
    var selectedID: String?
    var showsUserLocation: Bool
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
        mapView.overrideUserInterfaceStyle = .dark
        mapView.mapType = .mutedStandard
        mapView.pointOfInterestFilter = .excludingAll
        mapView.showsCompass = false
        mapView.showsUserLocation = showsUserLocation
        mapView.setRegion(kHomeRegion, animated: false)
        return mapView
    }

    func updateUIView(_ mapView: MKMapView, context: Context) {
        context.coordinator.parent = self
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

/// Pre-rendered venue dots, matching the preview: pink with a dark
/// ring; the selected venue is a larger cyan dot with a white ring.
enum DotImages {
    private static let normal = DotImages.make(
        fill: UIColor(red: 1.0, green: 0x4D / 255.0, blue: 0x7E / 255.0, alpha: 0.95),
        diameter: 13, ring: UIColor(red: 0x07 / 255.0, green: 0x09 / 255.0, blue: 0x12 / 255.0, alpha: 1.0),
        ringWidth: 1.5)
    private static let selected = DotImages.make(
        fill: UIColor(red: 0x38 / 255.0, green: 0xE1 / 255.0, blue: 1.0, alpha: 1.0),
        diameter: 19, ring: UIColor.white, ringWidth: 2)

    static func image(selected: Bool) -> UIImage {
        return selected ? DotImages.selected : DotImages.normal
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
