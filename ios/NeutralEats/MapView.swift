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

    /// Name label shown above a venue's dot at street zoom (web
    /// parity: the preview labels venues at zoom ≥ 17). A separate
    /// annotation so it can appear/disappear with zoom without
    /// touching the dot layer.
    final class LabelAnnotation: MKPointAnnotation {
        var venueID: String = ""
    }

    final class Coordinator: NSObject, MKMapViewDelegate {
        var parent: VenueMapView?
        var lastCenterNonce: Int = 0
        private var annotationsByID: [String: VenueAnnotation] = [:]
        private var labelAnnotationsByID: [String: LabelAnnotation] = [:]
        private var labelMode: NEThemeMode?

        /// Street-zoom threshold for name labels, matched to the
        /// web's zoom ≥ 17 (a latitude span of ~0.0085 at this
        /// latitude and screen size), and the label cap — the web
        /// labels at most 120 nearest; 80 keeps the densest downtown
        /// blocks readable on a phone-width map.
        private static let labelMaxSpan: Double = 0.0085
        private static let labelCap: Int = 80

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
            reconcileLabels(on: mapView, venues: venues, selectedID: selectedID)
        }

        /// Labels exist only at street zoom, for the nearest venues
        /// to the map center. Reconciled on every sync and every
        /// region settle; a theme flip rebuilds them (their colors
        /// are baked into the views).
        func reconcileLabels(on mapView: MKMapView, venues: [Venue], selectedID: String?) {
            if labelMode != NEColor.mode {
                labelMode = NEColor.mode
                for (_, annotation) in labelAnnotationsByID {
                    mapView.removeAnnotation(annotation)
                }
                labelAnnotationsByID = [:]
            }
            var targetIDs = Set<String>()
            if mapView.region.span.latitudeDelta <= Coordinator.labelMaxSpan {
                let center = CLLocation(latitude: mapView.region.center.latitude,
                                         longitude: mapView.region.center.longitude)
                let named = venues.filter { $0.isMappable && !($0.name ?? "").isEmpty }
                let nearest = named.sorted { a, b in
                    let da = CLLocation(latitude: a.lat!, longitude: a.lng!).distance(from: center)
                    let db = CLLocation(latitude: b.lat!, longitude: b.lng!).distance(from: center)
                    return da < db
                }.prefix(Coordinator.labelCap)
                for venue in nearest { targetIDs.insert(venue.id) }
            }
            for (id, annotation) in labelAnnotationsByID where !targetIDs.contains(id) {
                mapView.removeAnnotation(annotation)
                labelAnnotationsByID[id] = nil
            }
            for venue in venues where targetIDs.contains(venue.id) && labelAnnotationsByID[venue.id] == nil {
                let annotation = LabelAnnotation()
                annotation.venueID = venue.id
                annotation.coordinate = venue.coordinate!
                annotation.title = venue.name
                labelAnnotationsByID[venue.id] = annotation
                mapView.addAnnotation(annotation)
            }
            // The selected venue's label wears the accent color.
            for (id, annotation) in labelAnnotationsByID {
                if let view = mapView.view(for: annotation),
                   let label = view.subviews.first as? UILabel {
                    label.textColor = Coordinator.labelTextColor(selected: id == selectedID)
                }
            }
        }

        static func labelTextColor(selected: Bool) -> UIColor {
            if NEColor.mode == .day {
                return selected
                    ? UIColor(red: 0xD9 / 255.0, green: 0x2C / 255.0, blue: 0x57 / 255.0, alpha: 1.0)
                    : UIColor(red: 0x16 / 255.0, green: 0x1C / 255.0, blue: 0x33 / 255.0, alpha: 1.0)
            }
            return selected
                ? UIColor(red: 1.0, green: 0x4D / 255.0, blue: 0x7E / 255.0, alpha: 1.0)
                : UIColor(red: 0xEE / 255.0, green: 0xF1 / 255.0, blue: 1.0, alpha: 1.0)
        }

        func mapView(_ mapView: MKMapView, viewFor annotation: MKAnnotation) -> MKAnnotationView? {
            if annotation is MKUserLocation { return nil }
            if let labelAnnotation = annotation as? LabelAnnotation {
                let reuseID = "venue-label"
                let view = mapView.dequeueReusableAnnotationView(withIdentifier: reuseID)
                    ?? MKAnnotationView(annotation: annotation, reuseIdentifier: reuseID)
                view.annotation = annotation
                view.canShowCallout = false
                view.displayPriority = .defaultLow
                for sub in view.subviews { sub.removeFromSuperview() }
                let label = UILabel()
                label.text = labelAnnotation.title
                label.font = .systemFont(ofSize: 11, weight: .semibold)
                label.textColor = Coordinator.labelTextColor(
                    selected: labelAnnotation.venueID == parent?.selectedID)
                label.shadowColor = NEColor.mode == .day ? UIColor.white : UIColor.black
                label.shadowOffset = CGSize(width: 0, height: 1)
                label.sizeToFit()
                view.addSubview(label)
                view.frame = CGRect(origin: .zero,
                                    size: CGSize(width: label.frame.width + 4,
                                                 height: label.frame.height + 2))
                label.center = CGPoint(x: view.frame.width / 2, y: view.frame.height / 2)
                view.centerOffset = CGPoint(x: 0, y: -16)
                return view
            }
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
            let venueID: String?
            if let venueAnnotation = view.annotation as? VenueAnnotation {
                venueID = venueAnnotation.venueID
            } else if let labelAnnotation = view.annotation as? LabelAnnotation {
                venueID = labelAnnotation.venueID
            } else {
                venueID = nil
            }
            guard let venueID = venueID, let annotation = view.annotation else { return }
            mapView.deselectAnnotation(annotation, animated: false)
            parent?.onSelectVenue(venueID)
        }

        func mapView(_ mapView: MKMapView, regionDidChangeAnimated animated: Bool) {
            parent?.onRegionSettled(mapView.region)
            if let parent = parent {
                reconcileLabels(on: mapView, venues: parent.venues, selectedID: parent.selectedID)
            }
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
