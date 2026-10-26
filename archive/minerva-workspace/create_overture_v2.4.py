#!/usr/bin/env python3

# Read v2.3
with open('/root/.openclaw/workspace/neutraleats2-v2.3-FINAL.html', 'r') as f:
    content = f.read()

print(f"Original file size: {len(content)} bytes")

# 1. Update tagline
tagline_old = '• Powered by OpenStreetMap</div'
tagline_new = '• Powered by Overture Maps + OpenStreetMap</div'
content = content.replace(tagline_old, tagline_new)
print("✓ Updated tagline")

# 2. Update version in footer
version_old = '• v2.2 </footer'
version_new = '• v2.4 Overture Edition </footer'
content = content.replace(version_old, version_new)
print("✓ Updated version footer")

# 3. Add parseOvertureVenues after getGridKey
gp_end = 'return `grid_${gridLat.toFixed(4)}_${gridLng.toFixed(4)}`; } '
gp_end_idx = content.find(gp_end)
if gp_end_idx > 0:
    insert_pos = gp_end_idx + len(gp_end)
    
    overture_parser = '''function parseOvertureVenues(features) {
  return features.map(f => {
    const p = f.properties || {};
    const c = f.geometry?.coordinates || [0, 0];
    const cats = p.categories || [];
    const catStr = cats.join(' ').toLowerCase();
    const isFood = /restaurant|cafe|coffee|bar|pub|food|dining|bakery/.test(catStr);
    if (!isFood) return null;
    let type = 'restaurant';
    if (catStr.includes('cafe') || catStr.includes('coffee') || catStr.includes('bakery')) type = 'cafe';
    if (catStr.includes('bar') || catStr.includes('pub') || catStr.includes('nightclub')) type = 'bar';
    return {
      id: p.id || `ovt${Math.random().toString(36).substr(2, 8)}`,
      name: p.names?.primary || p.name || 'Unnamed Venue',
      lat: parseFloat(c[1]),
      lng: parseFloat(c[0]),
      type: type,
      cuisine: cats[0] || 'Various',
      brand: p.brands?.[0] || p.brand || '',
      stars: null,
      fee: 'unknown'
    };
  }).filter(v => v !== null).slice(0, 100);
}

'''
    
    content = content[:insert_pos] + overture_parser + content[insert_pos:]
    print("✓ Added parseOvertureVenues function")
else:
    print("✗ Could not find getGridKey end")

# 4. Modify fetchVenues - this is the tricky part
# We need to add Overture try block AND change "// IMMEDIATELY show samples while fetching Overpass"

old_fetch = "async function fetchVenues(bounds) { console.log('🦉 fetchVenues called'); // IMMEDIATELY show samples while fetching Overpass venues = [...samples]; renderMarkers(); renderList();"

new_fetch = """async function fetchVenues(bounds) {
  console.log('🦉 fetchVenues called');
  venues = [...samples]; renderMarkers(); renderList();
  const south = bounds.getSouth();
  const west = bounds.getWest();
  const north = bounds.getNorth();
  const east = bounds.getEast();
  const center = bounds.getCenter();
  
  // Try Overture via Fused UDF first
  try {
    console.log('🦉 Trying Overture via Fused...');
    const bbox = `${west.toFixed(4)},${south.toFixed(4)},${east.toFixed(4)},${north.toFixed(4)}`;
    const fusedUrl = `https://www.fused.io/server/v1/realtime-shared/UDF_Overture_Maps_Example/run/file?bbox=${bbox}&overture_type=place&format=geojson`;
    const resp = await fetch(fusedUrl);
    if (resp.ok) {
      const data = await resp.json();
      const ovtVenues = parseOvertureVenues(data.features || []);
      if (ovtVenues.length > 0) {
        venues = ovtVenues;
        renderMarkers(); renderList();
        console.log(`🦉 Overture loaded ${ovtVenues.length} venues`);
        return;
      }
    }
  } catch (e) { console.log('🦉 Overture failed:', e.message); }
  
  // Fallback to"""

if old_fetch in content:
    content = content.replace(old_fetch, new_fetch)
    print("✓ Modified fetchVenues to try Overture first")
else:
    print("✗ Could not find fetchVenues pattern")

# Write the new file
with open('/root/.openclaw/workspace/neutraleats2-v2.4-overture.html', 'w') as f:
    f.write(content)

print(f"\n✅ Wrote neutraleats2-v2.4-overture.html ({len(content)} bytes)")

# Verify
with open('/root/.openclaw/workspace/neutraleats2-v2.4-overture.html', 'r') as f:
    check = f.read()
    checks = [
        ("Overture tagline", "Powered by Overture Maps" in check),
        ("Version v2.4", "v2.4 Overture Edition" in check),
        ("parseOvertureVenues", "parseOvertureVenues" in check),
        ("Overture via Fused", "Try Overture via Fused" in check),
        ("Fallback to", "Fallback to" in check)
    ]
    print("\nVerification:")
    for name, passed in checks:
        print(f"  {'✓' if passed else '✗'} {name}")
