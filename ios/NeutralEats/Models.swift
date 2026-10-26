import Foundation
import CoreLocation

// MARK: - API envelope

struct VenueEnvelope: Decodable {
    let success: Bool?
    let venues: [Venue]
    let count: Int?
}

// MARK: - Venue

/// One venue from /api/venues.php. The API is not perfectly typed —
/// legacy rows carry type "0", numbers occasionally arrive as strings,
/// priceLevel is sometimes a number, sometimes a "$" string, often
/// null — so decoding is deliberately flexible, mirroring the guards
/// in web/preview.html.
struct Venue: Decodable, Identifiable {
    let id: String
    let name: String?
    let lat: Double?
    let lng: Double?
    let type: String?
    let cuisine: String?
    let rating: Double?
    let priceLevel: Int?
    let reviewCount: Int?
    let tableService: Bool?
    let address: String?
    let phone: String?
    let website: String?
    let source: String?

    var coordinate: CLLocationCoordinate2D? {
        guard let lat = lat, let lng = lng else { return nil }
        return CLLocationCoordinate2D(latitude: lat, longitude: lng)
    }
    var isMappable: Bool { return coordinate != nil }

    enum CodingKeys: String, CodingKey {
        case id, name, lat, lng, type, cuisine, rating, priceLevel
        case reviewCount, tableService
        case address, phone, website, source
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = Venue.flexString(c, .id) ?? ""
        name = Venue.flexString(c, .name)
        lat = Venue.flexDouble(c, .lat)
        lng = Venue.flexDouble(c, .lng)
        type = Venue.flexString(c, .type)
        cuisine = Venue.flexString(c, .cuisine)
        rating = Venue.flexDouble(c, .rating)
        priceLevel = Venue.flexPrice(c, .priceLevel)
        reviewCount = Venue.flexCount(c, .reviewCount)
        tableService = Venue.flexBool(c, .tableService)
        address = Venue.flexString(c, .address)
        phone = Venue.flexString(c, .phone)
        website = Venue.flexString(c, .website)
        source = Venue.flexString(c, .source)
    }

    private static func flexString(_ c: KeyedDecodingContainer<CodingKeys>, _ k: CodingKeys) -> String? {
        if let s = try? c.decode(String.self, forKey: k) { return s }
        if let n = try? c.decode(Double.self, forKey: k) { return String(format: "%g", n) }
        return nil
    }

    private static func flexDouble(_ c: KeyedDecodingContainer<CodingKeys>, _ k: CodingKeys) -> Double? {
        if let d = try? c.decode(Double.self, forKey: k) { return d }
        if let s = try? c.decode(String.self, forKey: k) { return Double(s) }
        return nil
    }

    private static func flexCount(_ c: KeyedDecodingContainer<CodingKeys>, _ k: CodingKeys) -> Int? {
        if let n = try? c.decode(Int.self, forKey: k) { return n }
        if let d = try? c.decode(Double.self, forKey: k) { return Int(d) }
        if let s = try? c.decode(String.self, forKey: k) { return Int(s) }
        return nil
    }

    private static func flexBool(_ c: KeyedDecodingContainer<CodingKeys>, _ k: CodingKeys) -> Bool? {
        if let b = try? c.decode(Bool.self, forKey: k) { return b }
        if let n = try? c.decode(Int.self, forKey: k) { return n != 0 }
        if let s = try? c.decode(String.self, forKey: k) { return s == "1" || s.lowercased() == "true" }
        return nil
    }

    private static func flexPrice(_ c: KeyedDecodingContainer<CodingKeys>, _ k: CodingKeys) -> Int? {
        if let n = try? c.decode(Int.self, forKey: k) { return n }
        if let d = try? c.decode(Double.self, forKey: k) { return Int(d) }
        if let s = try? c.decode(String.self, forKey: k), !s.isEmpty,
           s.allSatisfy({ $0 == "$" }) { return s.count }
        return nil
    }

    // MARK: Presentation (mirrors web/preview.html helpers)

    private static let typeLabels: [String: String] = [
        "restaurant": "Restaurant", "cafe": "Café", "bar": "Bar",
        "pub": "Pub", "fast_food": "Fast Food", "bakery": "Bakery",
    ]
    private static let sourceLabels: [String: String] = [
        "yelp": "Yelp", "overture": "Overture",
        "osm": "OpenStreetMap", "foursquare": "Foursquare",
    ]

    /// Legacy rows carry type "0"/unknown — fall back to the first
    /// cuisine term so the row still says something true.
    var typeLabel: String {
        if let t = type, let label = Venue.typeLabels[t] { return label }
        if let cuisine = cuisine,
           let first = cuisine.split(separator: ",").first {
            return String(first).trimmingCharacters(in: .whitespaces)
        }
        return "Food & Drink"
    }

    var metaLine: String {
        var parts: [String] = []
        let t = typeLabel
        if !t.isEmpty { parts.append(t) }
        if let cuisine = cuisine, cuisine != t {
            var c = cuisine
            if c.count > 44 {
                c = String(c.prefix(44)).trimmingCharacters(in: .whitespaces) + "…"
            }
            if !parts.contains(c) { parts.append(c) }
        }
        return parts.joined(separator: " · ")
    }

    var ratingValue: Double? {
        guard let rating = rating, rating > 0 else { return nil }
        return rating
    }

    var priceString: String {
        guard let p = priceLevel, p > 0 else { return "" }
        return String(repeating: "$", count: min(p, 4))
    }

    /// "★ 4.5 (123) · $$" — pieces omitted when the data isn't there
    /// (review count arrives with Yelp enrichment; web parity).
    var ratingPriceLine: String {
        var parts: [String] = []
        if let r = ratingValue {
            var star = "★ " + String(format: "%.1f", r)
            if let count = reviewCount, count > 0 { star += " (\(count))" }
            parts.append(star)
        }
        if !priceString.isEmpty { parts.append(priceString) }
        return parts.joined(separator: " · ")
    }

    var sourceLine: String? {
        guard let source = source, !source.isEmpty else { return nil }
        let names = source.split(separator: "+").map { raw -> String in
            let s = String(raw).trimmingCharacters(in: .whitespaces).lowercased()
            return Venue.sourceLabels[s] ?? s.capitalized
        }
        return "Listed via " + names.joined(separator: " + ") +
            " data. neutral eats takes no placement fees — this order is pure distance."
    }

    var sanitizedPhone: String? {
        guard let phone = phone else { return nil }
        let t = phone.filter { $0 == "+" || $0.isNumber }
        return t.isEmpty ? nil : t
    }

    var websiteURL: URL? {
        guard var w = website?.trimmingCharacters(in: .whitespaces), !w.isEmpty else { return nil }
        let lower = w.lowercased()
        if !lower.hasPrefix("http://") && !lower.hasPrefix("https://") {
            w = "https://" + w
        }
        guard let u = URL(string: w), let scheme = u.scheme?.lowercased(),
              scheme == "http" || scheme == "https" else { return nil }
        return u
    }

    var directionsURL: URL? {
        guard let coord = coordinate else { return nil }
        let place = ((name ?? "") + " " + (address ?? ""))
            .addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? ""
        return URL(string: "https://www.google.com/maps/dir/?api=1&destination=" +
            "\(coord.latitude),\(coord.longitude)&destination_place_name=\(place)")
    }

    // MARK: Distance

    func distanceMiles(from center: CLLocationCoordinate2D) -> Double {
        guard let coord = coordinate else { return Double.greatestFiniteMagnitude }
        return Venue.haversineMi(lat1: center.latitude, lng1: center.longitude,
                                 lat2: coord.latitude, lng2: coord.longitude)
    }

    static func haversineMi(lat1: Double, lng1: Double, lat2: Double, lng2: Double) -> Double {
        let r = 3958.8
        let dLat = (lat2 - lat1) * Double.pi / 180.0
        let dLng = (lng2 - lng1) * Double.pi / 180.0
        let a = sin(dLat / 2) * sin(dLat / 2) +
            cos(lat1 * Double.pi / 180.0) * cos(lat2 * Double.pi / 180.0) *
            sin(dLng / 2) * sin(dLng / 2)
        return r * 2 * atan2(sqrt(a), sqrt(1 - a))
    }

    static func formatDistance(_ miles: Double) -> String {
        if !miles.isFinite { return "" }
        if miles < 0.1 {
            let feet = max(10.0, (miles * 5280.0 / 10.0).rounded() * 10.0)
            return "\(Int(feet)) ft"
        }
        return String(format: "%.1f mi", miles)
    }
}

// MARK: - Filter chips

/// Mirrors the preview: restaurant/cafe/bar filter server-side via the
/// API's `type` param; fast_food/bakery are not accepted by the API, so
/// they fetch the unfiltered set and filter client-side on venue.type.
enum VenueFilter: String, CaseIterable, Identifiable {
    case all, restaurant, cafe, bar, fastFood, bakery

    var id: String { return rawValue }

    var label: String {
        switch self {
        case .all: return "All"
        case .restaurant: return "Restaurants"
        case .cafe: return "Cafés"
        case .bar: return "Bars"
        case .fastFood: return "Fast Food"
        case .bakery: return "Bakeries"
        }
    }

    var serverType: String? {
        switch self {
        case .restaurant: return "restaurant"
        case .cafe: return "cafe"
        case .bar: return "bar"
        default: return nil
        }
    }

    var clientType: String? {
        switch self {
        case .fastFood: return "fast_food"
        case .bakery: return "bakery"
        default: return nil
        }
    }
}
