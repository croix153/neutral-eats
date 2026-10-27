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
    var onDeselect: () -> Void

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
        // Tapping genuinely empty map deselects (Croix, build 15).
        // The recognizer never cancels touches, so MapKit's own
        // tap handling (annotation selection, double-tap zoom) is
        // untouched; the coordinator decides whether the tap hit
        // an annotation before treating it as an empty tap.
        let tap = UITapGestureRecognizer(
            target: context.coordinator,
            action: #selector(Coordinator.handleMapTap(_:)))
        tap.cancelsTouchesInView = false
        mapView.addGestureRecognizer(tap)
        return mapView
    }

    func updateUIView(_ mapView: MKMapView, context: Context) {
        context.coordinator.parent = self
        mapView.overrideUserInterfaceStyle = isDay ? .light : .dark
        mapView.showsUserLocation = showsUserLocation
        // Annotation mutations are NEVER made synchronously from
        // here (build 14 hardening): SwiftUI can call updateUIView
        // in the middle of MapKit's own selection/layout passes —
        // a tap that selects a venue and requests a snap fires this
        // method while MapKit is still working through the tap —
        // and the build 11/12/13 crashes all live in that
        // re-entrancy family. The sync is deferred one tick and
        // coalesced; see Coordinator.scheduleSync.
        context.coordinator.scheduleSync(on: mapView)
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
        /// Previous sync's clustering state. When it flips (the
        /// street-zoom threshold was crossed either way), every
        /// venue annotation is rebuilt so each view is born via
        /// viewFor with the right clusteringIdentifier — flipping
        /// the identifier on live, possibly clustered views is
        /// where MapKit's clustering bookkeeping can corrupt
        /// (build 12 crash hardening; Croix hit a crash drilling
        /// into a cluster and zooming, 2026-10-26).
        private var lastClusteringActive: Bool?
        /// Previous sync's selection, for the re-dress-by-re-add
        /// pass in syncAnnotations (build 15 — see dress()).
        private var lastSelectedID: String?
        private var syncScheduled = false

        /// Empty-map taps deselect (Croix, build 15). A tap that
        /// lands on any annotation view — dot, label, cluster, the
        /// user marker — belongs to the selection machinery and is
        /// ignored here; only a tap on genuinely empty map clears
        /// the selection.
        @objc func handleMapTap(_ recognizer: UITapGestureRecognizer) {
            guard let mapView = recognizer.view as? MKMapView else { return }
            let point = recognizer.location(in: mapView)
            for annotation in mapView.annotations {
                if let view = mapView.view(for: annotation),
                   view.frame.contains(point) {
                    return
                }
            }
            parent?.onDeselect()
        }

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
            // Clustering-mode flip: rebuild every venue annotation
            // (see lastClusteringActive). Re-adding fires viewFor,
            // which dresses each fresh view with the identifier and
            // image for the new mode — no live-view mutation of
            // clustering state mid-pass.
            if lastClusteringActive != nil
                && lastClusteringActive != clusteringActive
                && !annotationsByID.isEmpty {
                for (_, annotation) in annotationsByID {
                    mapView.removeAnnotation(annotation)
                }
                annotationsByID = [:]
            }
            lastClusteringActive = clusteringActive
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
            // A selection change re-dresses two venues (the old
            // and the new selection) — by removing and re-adding
            // their annotations, never by mutating live views (see
            // dress() for the crash that rule comes from). The
            // re-add also pulls a newly selected venue OUT of any
            // cluster it was sitting in: its fresh view is born
            // unclustered, so the selection is always visible on
            // the map (Croix, build 15 — "no indicator that a
            // restaurant within is selected").
            if selectedID != lastSelectedID {
                for id in [lastSelectedID, selectedID] {
                    guard let id = id,
                          let annotation = annotationsByID[id],
                          mapView.view(for: annotation) != nil
                    else { continue }
                    mapView.removeAnnotation(annotation)
                    mapView.addAnnotation(annotation)
                }
                lastSelectedID = selectedID
            }
            // Live views get IMAGE updates only (theme repaints,
            // the selected dot's bigger image). Identity check
            // first: for a venue that is currently clustered,
            // view(for:) can hand back the CLUSTER's view —
            // painting that view as a dot corrupts the cluster's
            // bookkeeping (build 12 crash hardening).
            for (id, annotation) in annotationsByID {
                if let view = mapView.view(for: annotation),
                   view.annotation === annotation {
                    refreshImage(view, venueID: id, selectedID: selectedID)
                }
            }
            // Cluster bubbles and the user dot are dressed ONLY
            // in viewFor, and MapKit never re-asks for those views
            // when the theme flips — so a toggle repainted every
            // venue dot but left the number bubbles (and the dot)
            // wearing the old theme until the viewport moved and
            // clustering re-ran (Croix, build 13). Re-dress them
            // here, IMAGE ONLY: assigning an image is cosmetic —
            // no displayPriority, no clusteringIdentifier, none of
            // the bookkeeping the build 12 hardening keeps out of
            // live passes — under the same identity check the
            // venue loop above uses.
            for annotation in mapView.annotations {
                if let cluster = annotation as? MKClusterAnnotation,
                   let view = mapView.view(for: cluster),
                   view.annotation === cluster {
                    view.image = ClusterImages.image(count: cluster.memberAnnotations.count)
                }
            }
            if mapView.showsUserLocation,
               let userView = mapView.view(for: mapView.userLocation),
               userView.annotation === mapView.userLocation {
                userView.image = UserMarkerImages.image()
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
        ///
        /// FULL DRESS — viewFor ONLY (build 15). displayPriority
        /// and clusteringIdentifier are set here and nowhere else:
        /// build 13's crash log shows MapKit aborting inside its
        /// own clustering bookkeeping
        /// (_existingClusterViewsForClusterID:, nil key) during an
        /// animated region change, in a pass where a live view's
        /// clusteringIdentifier no longer matched the group MapKit
        /// had filed it under. Identifiers are birth state now.
        /// When a venue's dress must change, syncAnnotations
        /// re-adds its annotation and MapKit calls viewFor again.
        func dress(_ view: MKAnnotationView, venueID: String, selectedID: String?) {
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

        /// IMAGE-ONLY refresh for views already on the map: theme
        /// repaints and the selected dot's bigger image. Never
        /// touches displayPriority or clusteringIdentifier — see
        /// dress() for why those are birth-only.
        func refreshImage(_ view: MKAnnotationView, venueID: String, selectedID: String?) {
            let selected = venueID == selectedID
            if labeledIDs.contains(venueID), let venue = venuesByID[venueID] {
                let rendered = LabelImages.image(venue: venue, selected: selected)
                view.image = rendered.image
                view.centerOffset = CGPoint(x: 0, y: rendered.centerOffsetY)
            } else {
                view.image = DotImages.image(selected: selected)
                view.centerOffset = .zero
            }
        }

        func mapView(_ mapView: MKMapView, viewFor annotation: MKAnnotation) -> MKAnnotationView? {
            if annotation is MKUserLocation {
                // You-are-here is a plain dot in the location
                // color (build 15), replacing the stock blue dot —
                // a custom view for the user annotation is the
                // supported way to do it.
                let reuseID = "user-dot"
                let view = mapView.dequeueReusableAnnotationView(withIdentifier: reuseID)
                    ?? MKAnnotationView(annotation: annotation, reuseIdentifier: reuseID)
                view.annotation = annotation
                view.canShowCallout = false
                view.displayPriority = .required
                view.clusteringIdentifier = nil
                view.image = UserMarkerImages.image()
                return view
            }
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
            dress(view, venueID: venueAnnotation.venueID, selectedID: parent?.selectedID)
            return view
        }

        func mapView(_ mapView: MKMapView, didSelect view: MKAnnotationView) {
            // Tapping a cluster zooms into its members — the
            // standard "this bubble is N places, come closer" move.
            // The zoom is deferred one runloop tick and expressed
            // as a clamped region (build 12 crash hardening):
            // calling setRegion/setVisibleMapRect synchronously
            // inside didSelect, with an unclamped member rect,
            // re-enters MapKit's selection + clustering machinery
            // mid-callback.
            if let cluster = view.annotation as? MKClusterAnnotation {
                mapView.deselectAnnotation(cluster, animated: false)
                let members = cluster.memberAnnotations
                let center = cluster.coordinate
                DispatchQueue.main.async {
                    var rect = MKMapRect.null
                    for member in members {
                        let point = MKMapPoint(member.coordinate)
                        rect = rect.union(MKMapRect(x: point.x, y: point.y,
                                                    width: 0, height: 0))
                    }
                    if rect.isNull || rect.size.width == 0 && rect.size.height == 0 {
                        let region = MKCoordinateRegion(
                            center: center,
                            span: MKCoordinateSpan(latitudeDelta: 0.01,
                                                   longitudeDelta: 0.01))
                        mapView.setRegion(region, animated: true)
                    } else {
                        var region = MKCoordinateRegion(rect)
                        region.span = MKCoordinateSpan(
                            latitudeDelta: min(max(region.span.latitudeDelta * 1.35, 0.004), 0.25),
                            longitudeDelta: min(max(region.span.longitudeDelta * 1.35, 0.004), 0.25))
                        mapView.setRegion(region, animated: true)
                    }
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
            scheduleSync(on: mapView)
        }

        /// THE way annotation mutations are requested (build 14):
        /// deferred one runloop tick and coalesced, reading the
        /// parent's inputs at fire time. Every entry point —
        /// updateUIView, regionDidChangeAnimated — goes through
        /// here, so syncAnnotations only ever runs on a clean tick,
        /// never inside a MapKit callback or a SwiftUI update that
        /// MapKit triggered mid-pass. Builds 11, 12 and 13 each
        /// crashed in a synchronous-sync path (region changes,
        /// cluster drills, and build 13's tap-to-snap selection,
        /// which reaches the sync via updateUIView while MapKit is
        /// still processing the tap); this removes the whole class
        /// rather than the third instance of it.
        func scheduleSync(on mapView: MKMapView) {
            guard !syncScheduled else { return }
            syncScheduled = true
            DispatchQueue.main.async { [weak self, weak mapView] in
                guard let self = self, let mapView = mapView else { return }
                self.syncScheduled = false
                if let parent = self.parent {
                    self.syncAnnotations(on: mapView, venues: parent.venues,
                                         selectedID: parent.selectedID)
                }
            }
        }
    }
}

/// Pre-rendered venue dots, matching the preview in both themes:
/// night — sakura fill #FF4D7E with a #070912 ring; day — shu-iro
/// vermillion #EB471F with a white ring (Creams Tokyo day realign,
/// build 12). The selected venue is a larger --good dot with a
/// white ring (day: ai-iro indigo #165E83). Images are cached per
/// theme and rebuilt on the first request after NEColor.mode
/// flips (the coordinator re-assigns every annotation's image on
/// each sync, so a toggle repaints all dots).
enum DotImages {
    private static var cachedMode: NEThemeMode?
    private static var normalImg: UIImage?
    private static var selectedImg: UIImage?

    static func image(selected: Bool) -> UIImage {
        if cachedMode != NEColor.mode {
            cachedMode = NEColor.mode
            if NEColor.mode == .day {
                normalImg = DotImages.make(
                    fill: UIColor(red: 0xEB / 255.0, green: 0x47 / 255.0, blue: 0x1F / 255.0, alpha: 0.95),
                    diameter: 13, ring: UIColor.white,
                    ringWidth: 1.5)
                selectedImg = DotImages.make(
                    fill: UIColor(red: 0x16 / 255.0, green: 0x5E / 255.0, blue: 0x83 / 255.0, alpha: 1.0),
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
            ? UIColor(red: 0xEB / 255.0, green: 0x47 / 255.0, blue: 0x1F / 255.0, alpha: 0.95)
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
/// see the Coordinator's dress() note for why labels are
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
            .font: UIFont.systemFont(ofSize: 12, weight: .semibold),
            .foregroundColor: selected
                ? hex(day ? 0xC6360F : 0xFF4D7E)
                : hex(day ? 0x2B2B2B : 0xEEF1FF),
            .strokeColor: day ? UIColor.white : hex(0x070912),
            .strokeWidth: -5,
        ]
        let textSize = (name as NSString).size(withAttributes: attributes)
        let dot = DotImages.image(selected: selected)
        let gap: CGFloat = 3
        // Pixel-snap the layout (build 17): the measured text
        // width is fractional, so centering used to put the glyph
        // origin at a fractional x — glyphs straddled pixels and
        // the labels looked artifact-y no matter the scale (Croix,
        // on build 16). Ceil the text box and round the origin so
        // text rasterizes on the pixel grid; the halo also goes a
        // touch heavier (-5 vs -3.5) so its edge reads even.
        let textW = ceil(textSize.width)
        let width = max(textW + 8, dot.size.width)
        let textHeight = ceil(textSize.height)
        let height = textHeight + gap + dot.size.height
        let format = UIGraphicsImageRendererFormat()
        format.scale = 3
        format.opaque = false
        let image = UIGraphicsImageRenderer(size: CGSize(width: width, height: height),
                                            format: format).image { _ in
            (name as NSString).draw(
                at: CGPoint(x: ((width - textW) / 2).rounded(), y: 0),
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

/// You-are-here marker (build 15): just a dot — but in the
/// theme's location color (--good: ai-iro indigo by day, neon
/// cyan by night), so it can never be confused with a venue dot
/// (vermillion by day, pink by night). Bigger than a venue dot
/// with a heavier white ring. The shape experiments are over:
/// gold star, theme star, arrow — Croix's call was "just a dot
/// but in a different color to differentiate it." NO halo, NO
/// glow. Cached per theme mode like the dot images.
enum UserMarkerImages {
    private static var cachedMode: NEThemeMode?
    private static var cachedImg: UIImage?

    static func image() -> UIImage {
        if cachedMode != NEColor.mode || cachedImg == nil {
            cachedMode = NEColor.mode
            let tint: UIColor = NEColor.mode == .day
                ? UIColor(red: 0x16 / 255.0, green: 0x5E / 255.0, blue: 0x83 / 255.0, alpha: 1.0)
                : UIColor(red: 0x38 / 255.0, green: 0xE1 / 255.0, blue: 1.0, alpha: 1.0)
            cachedImg = make(tint: tint)
        }
        return cachedImg ?? UIImage()
    }

    private static func make(tint: UIColor) -> UIImage {
        let canvas: CGFloat = 21
        let format = UIGraphicsImageRendererFormat()
        format.scale = 3
        format.opaque = false
        let size = CGSize(width: canvas, height: canvas)
        return UIGraphicsImageRenderer(size: size, format: format).image { _ in
            let rect = CGRect(origin: .zero, size: size).insetBy(dx: 1.25, dy: 1.25)
            let path = UIBezierPath(ovalIn: rect)
            tint.setFill()
            path.fill()
            UIColor.white.setStroke()
            path.lineWidth = 2.5
            path.stroke()
        }
    }
}
