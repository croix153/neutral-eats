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
        private var venuesByID: [String: Venue] = [:]
        private var labeledIDs: Set<String> = []
        /// Clustering is active whenever labels are not (build 11):
        /// at wider spans, dots that would collide join a cluster
        /// bubble instead of being silently hidden by MapKit's
        /// collision system — Croix's "dots don't show unless you
        /// zoom in" report. At street zoom labels take over and
        /// every dot stands alone.
        private var clusteringActive: Bool = true

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
            venuesByID = incoming
            // Labels are decided BEFORE any view work: viewFor (fired
            // by addAnnotation below) reads labeledIDs to dress new
            // annotations correctly on their first appearance.
            labeledIDs = Coordinator.computeLabeledIDs(
                region: mapView.region, venues: Array(incoming.values))
            clusteringActive = labeledIDs.isEmpty
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
            // Existing views get the current dress: selection swaps
            // the dot image; the label set swaps in/out the combined
            // dot+name image.
            for (id, annotation) in annotationsByID {
                if let view = mapView.view(for: annotation) {
                    applyAppearance(view, venueID: id, selectedID: selectedID)
                }
            }
        }

        /// Street-zoom labels: the nearest venues to the map center,
        /// capped, named only. Empty set whenever the span is wider
        /// than street level — labels simply don't exist there.
        static func computeLabeledIDs(region: MKCoordinateRegion, venues: [Venue]) -> Set<String> {
            guard region.span.latitudeDelta <= labelMaxSpan else { return [] }
            let center = CLLocation(latitude: region.center.latitude,
                                    longitude: region.center.longitude)
            let named = venues.filter { !($0.name ?? "").isEmpty }
            let nearest = named.sorted { a, b in
                let da = CLLocation(latitude: a.lat!, longitude: a.lng!).distance(from: center)
                let db = CLLocation(latitude: b.lat!, longitude: b.lng!).distance(from: center)
                return da < db
            }.prefix(labelCap)
            return Set(nearest.map { $0.id })
        }

        /// One annotation, one image — labels are RENDERED INTO the
        /// annotation image (build 10). Build 9 shipped labels as a
        /// second annotation carrying a UILabel subview, and on
        /// device they never appeared: a view with no image of its
        /// own is at the mercy of MapKit's collision and layout
        /// handling for annotation views. A single combined image
        /// has no second view to lose — if the dot renders, the
        /// label renders, because they're the same pixels. Labeled
        /// views get .required display priority so the collision
        /// system never hides one (the web lets labels overlap too);
        /// plain dots keep the default.
        func applyAppearance(_ view: MKAnnotationView, venueID: String, selectedID: String?) {
            let selected = venueID == selectedID
            if labeledIDs.contains(venueID), let venue = venuesByID[venueID] {
                let rendered = LabelImages.image(venue: venue, selected: selected)
                view.image = rendered.image
                view.centerOffset = CGPoint(x: 0, y: rendered.centerOffsetY)
                view.displayPriority = .required
                view.clusteringIdentifier = nil
            } else {
                view.image = DotImages.image(selected: selected)
                view.centerOffset = .zero
                // The selected dot must never be collision-hidden
                // or clustered away — it marks the open detail.
                view.displayPriority = selected ? .required : .defaultHigh
                view.clusteringIdentifier =
                    (!selected && clusteringActive) ? "venueDot" : nil
            }
        }

        func mapView(_ mapView: MKMapView, viewFor annotation: MKAnnotation) -> MKAnnotationView? {
            if annotation is MKUserLocation { return nil }
            if let cluster = annotation as? MKClusterAnnotation {
                let reuseID = "venue-cluster"
                let view = mapView.dequeueReusableAnnotationView(withIdentifier: reuseID)
                    ?? MKAnnotationView(annotation: annotation, reuseIdentifier: reuseID)
                view.annotation = annotation
                view.canShowCallout = false
                view.collisionMode = .circle
                view.displayPriority = .defaultHigh
                view.image = ClusterImages.image(count: cluster.memberAnnotations.count)
                return view
            }
            guard let venueAnnotation = annotation as? VenueAnnotation else { return nil }
            let reuseID = "venue-dot"
            let view = mapView.dequeueReusableAnnotationView(withIdentifier: reuseID)
                ?? MKAnnotationView(annotation: annotation, reuseIdentifier: reuseID)
            view.annotation = annotation
            view.canShowCallout = false
            view.collisionMode = .circle
            applyAppearance(view, venueID: venueAnnotation.venueID, selectedID: parent?.selectedID)
            return view
        }

        func mapView(_ mapView: MKMapView, didSelect view: MKAnnotationView) {
            // Tapping a cluster zooms into its members — the
            // standard "this bubble is N places, come closer" move.
            if let cluster = view.annotation as? MKClusterAnnotation {
                mapView.deselectAnnotation(cluster, animated: false)
                var rect = MKMapRect.null
                for member in cluster.memberAnnotations {
                    let point = MKMapPoint(member.coordinate)
                    rect = rect.union(MKMapRect(x: point.x, y: point.y, width: 0, height: 0))
                }
                let padding = UIEdgeInsets(top: 70, left: 44, bottom: 130, right: 44)
                if rect.isNull || rect.size.width == 0 || rect.size.height == 0 {
                    let region = MKCoordinateRegion(
                        center: cluster.coordinate,
                        span: MKCoordinateSpan(latitudeDelta: 0.01, longitudeDelta: 0.01))
                    mapView.setRegion(region, animated: true)
                } else {
                    let grown = rect.insetBy(dx: -rect.size.width * 0.3,
                                             dy: -rect.size.height * 0.3)
                    mapView.setVisibleMapRect(grown, edgePadding: padding, animated: true)
                }
                return
            }
            guard let venueAnnotation = view.annotation as? VenueAnnotation else { return }
            mapView.deselectAnnotation(venueAnnotation, animated: false)
            parent?.onSelectVenue(venueAnnotation.venueID)
        }

        func mapView(_ mapView: MKMapView, regionDidChangeAnimated animated: Bool) {
            parent?.onRegionSettled(mapView.region)
            // Zoom settles change the label set even when SwiftUI
            // doesn't re-render (the venue fetch is debounced and
            // may keep the same results) — re-sync against the
            // parent's current inputs so labels track the span.
            if let parent = parent {
                syncAnnotations(on: mapView, venues: parent.venues, selectedID: parent.selectedID)
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

/// Cluster bubbles (build 11): a filled accent disc carrying the
/// member count, in the dot palette for both themes. Diameter
/// steps up with magnitude; images cached per (count, mode).
enum ClusterImages {
    private static var cache: [String: UIImage] = [:]

    static func image(count: Int) -> UIImage {
        let key = "\(count)|\(NEColor.mode == .day ? "day" : "night")"
        if let cached = cache[key] { return cached }
        let diameter: CGFloat = count < 10 ? 30 : (count < 100 ? 36 : 42)
        let fill: UIColor = NEColor.mode == .day
            ? UIColor(red: 0xD9 / 255.0, green: 0x2C / 255.0, blue: 0x57 / 255.0, alpha: 0.95)
            : UIColor(red: 1.0, green: 0x4D / 255.0, blue: 0x7E / 255.0, alpha: 0.92)
        let format = UIGraphicsImageRendererFormat()
        format.scale = 3
        let size = CGSize(width: diameter, height: diameter)
        let img = UIGraphicsImageRenderer(size: size, format: format).image { _ in
            let rect = CGRect(origin: .zero, size: size)
                .insetBy(dx: 1.5, dy: 1.5)
            fill.setFill()
            UIBezierPath(ovalIn: rect).fill()
            UIColor.white.setStroke()
            let ring = UIBezierPath(ovalIn: rect)
            ring.lineWidth = 2
            ring.stroke()
            let text = count > 999 ? "999+" : "\(count)"
            let fontSize: CGFloat = count < 10 ? 13 : (count < 100 ? 13 : 12)
            let attrs: [NSAttributedString.Key: Any] = [
                .font: UIFont.systemFont(ofSize: fontSize, weight: .bold),
                .foregroundColor: UIColor.white,
            ]
            let textSize = (text as NSString).size(withAttributes: attrs)
            (text as NSString).draw(
                at: CGPoint(x: (diameter - textSize.width) / 2,
                            y: (diameter - textSize.height) / 2),
                withAttributes: attrs)
        }
        cache[key] = img
        return img
    }
}

/// Combined dot + name images for street-zoom labels (build 10 —
/// see the Coordinator's applyAppearance note for why labels are
/// pixels now, not views). Text wears a halo in the opposite theme
/// color, mirroring the web's label styling; the selected venue's
/// name is accent-colored. Cached per venue/selection/theme; the
/// cache clears on a theme flip and self-caps.
enum LabelImages {
    private struct Key: Hashable {
        var id: String
        var selected: Bool
        var mode: NEThemeMode
    }

    private static var cache: [Key: (image: UIImage, centerOffsetY: CGFloat)] = [:]
    private static var cachedMode: NEThemeMode?

    static func image(venue: Venue, selected: Bool) -> (image: UIImage, centerOffsetY: CGFloat) {
        if cachedMode != NEColor.mode {
            cachedMode = NEColor.mode
            cache = [:]
        }
        let key = Key(id: venue.id, selected: selected, mode: NEColor.mode)
        if let hit = cache[key] { return hit }
        let rendered = render(venue: venue, selected: selected)
        if cache.count > 240 { cache = [:] }
        cache[key] = rendered
        return rendered
    }

    private static func hex(_ value: UInt32) -> UIColor {
        UIColor(red: CGFloat((value >> 16) & 0xFF) / 255.0,
                green: CGFloat((value >> 8) & 0xFF) / 255.0,
                blue: CGFloat(value & 0xFF) / 255.0,
                alpha: 1.0)
    }

    private static func render(venue: Venue, selected: Bool) -> (image: UIImage, centerOffsetY: CGFloat) {
        let name = venue.name ?? "Unnamed"
        let day = NEColor.mode == .day
        let attributes: [NSAttributedString.Key: Any] = [
            .font: UIFont.systemFont(ofSize: 11, weight: .semibold),
            .foregroundColor: selected
                ? hex(day ? 0xD92C57 : 0xFF4D7E)
                : hex(day ? 0x161C33 : 0xEEF1FF),
            .strokeColor: day ? UIColor.white : hex(0x070912),
            .strokeWidth: -3.5,
        ]
        let textSize = (name as NSString).size(withAttributes: attributes)
        let dot = DotImages.image(selected: selected)
        let gap: CGFloat = 3
        let width = max(ceil(textSize.width) + 6, dot.size.width)
        let textHeight = ceil(textSize.height)
        let height = textHeight + gap + dot.size.height
        let format = UIGraphicsImageRendererFormat()
        format.scale = 3
        format.opaque = false
        let image = UIGraphicsImageRenderer(size: CGSize(width: width, height: height),
                                            format: format).image { _ in
            (name as NSString).draw(
                at: CGPoint(x: (width - textSize.width) / 2, y: 0),
                withAttributes: attributes)
            dot.draw(at: CGPoint(x: (width - dot.size.width) / 2, y: textHeight + gap))
        }
        // The view's center lands on the coordinate; the dot sits
        // below the image's middle, so shift the view up by the
        // difference to put the DOT — not the label block — on the
        // venue's exact spot.
        let dotCenterY = textHeight + gap + dot.size.height / 2
        return (image, height / 2 - dotCenterY)
    }
}
