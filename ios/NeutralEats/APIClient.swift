import Foundation
import MapKit

struct APIClient {
    static let endpoint = "https://neutraleats.com/api/venues.php"
    static let limit = 500   // server hard cap (same as the web preview)

    /// Fetches one bbox page from the production API. Params mirror
    /// web/preview.html's buildUrl(): south/west/north/east + limit,
    /// optional server-side `type`, optional `search`.
    func fetch(region: MKCoordinateRegion, serverType: String?, search: String?) async throws -> (venues: [Venue], count: Int) {
        let center = region.center
        let south = center.latitude - region.span.latitudeDelta / 2.0
        let north = center.latitude + region.span.latitudeDelta / 2.0
        let west = center.longitude - region.span.longitudeDelta / 2.0
        let east = center.longitude + region.span.longitudeDelta / 2.0

        guard var comps = URLComponents(string: APIClient.endpoint) else {
            throw URLError(.badURL)
        }
        var query: [URLQueryItem] = [
            URLQueryItem(name: "south", value: fmt(south)),
            URLQueryItem(name: "west", value: fmt(west)),
            URLQueryItem(name: "north", value: fmt(north)),
            URLQueryItem(name: "east", value: fmt(east)),
            URLQueryItem(name: "limit", value: String(APIClient.limit)),
        ]
        if let serverType = serverType {
            query.append(URLQueryItem(name: "type", value: serverType))
        }
        if let search = search, !search.isEmpty {
            query.append(URLQueryItem(name: "search", value: search))
        }
        comps.queryItems = query
        guard let url = comps.url else { throw URLError(.badURL) }

        var request = URLRequest(url: url)
        request.timeoutInterval = 20
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse,
              (200..<300).contains(http.statusCode) else {
            throw URLError(.badServerResponse)
        }
        let envelope = try JSONDecoder().decode(VenueEnvelope.self, from: data)
        if envelope.success == false { throw URLError(.cannotParseResponse) }
        return (envelope.venues, envelope.count ?? envelope.venues.count)
    }

    private func fmt(_ value: Double) -> String {
        return String(format: "%.6f", value)
    }
}
