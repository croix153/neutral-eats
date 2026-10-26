#!/usr/bin/env python3
"""
Nationwide Coverage Analysis for Neutral Eats
Identifies gaps across US major metros
"""
import paramiko

host = '74.207.224.129'
username = 'minerva'
password = 'REDACTED'

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(host, username=username, password=password, timeout=30)

print("🇺🇸 Nationwide Coverage Analysis")
print("="*70)

# Check total venues
print("\n📊 Overall Stats:")
stdin, stdout, stderr = ssh.exec_command(
    'mysql -u neutraleats_user -pneutraleats_pass neutraleats -e "SELECT COUNT(*) as Total FROM venues;"'
)
print(stdout.read().decode())

# Check by state/region - major metros
regions = [
    ("New York City", 40.71, 40.80, -74.02, -73.92),
    ("Los Angeles", 33.95, 34.15, -118.35, -118.15),
    ("Chicago", 41.82, 41.92, -87.68, -87.58),
    ("Houston", 29.70, 29.80, -95.40, -95.30),
    ("Phoenix", 33.42, 33.52, -112.10, -112.00),
    ("Philadelphia", 39.92, 40.00, -75.20, -75.10),
    ("San Antonio", 29.38, 29.48, -98.55, -98.45),
    ("San Diego", 32.68, 32.78, -117.20, -117.10),
    ("Dallas", 32.75, 32.85, -96.85, -96.75),
    ("San Jose", 37.30, 37.40, -121.95, -121.85),
    ("Austin", 30.25, 30.35, -97.80, -97.70),
    ("Jacksonville FL", 30.30, 30.40, -81.70, -81.60),
    ("Fort Worth", 32.70, 32.80, -97.40, -97.30),
    ("Columbus OH", 39.95, 40.00, -83.05, -82.95),
    ("Charlotte", 35.20, 35.30, -80.90, -80.80),
    ("Indianapolis", 39.75, 39.85, -86.20, -86.10),
    ("San Francisco", 37.75, 37.85, -122.45, -122.35),
    ("Seattle", 47.60, 47.65, -122.35, -122.25),
    ("Denver", 39.70, 39.80, -105.00, -104.90),
    ("Washington DC", 38.90, 39.00, -77.05, -76.95),
    ("Boston", 42.35, 42.40, -71.10, -71.00),
    ("El Paso", 31.75, 31.85, -106.50, -106.40),
    ("Nashville", 36.15, 36.25, -86.80, -86.70),
    ("Detroit", 42.35, 42.40, -83.10, -83.00),
    ("Oklahoma City", 35.45, 35.55, -97.55, -97.45),
    ("Portland", 45.50, 45.55, -122.70, -122.60),
    ("Las Vegas", 36.15, 36.20, -115.25, -115.15),
    ("Louisville", 38.25, 38.30, -85.80, -85.70),
    ("Baltimore", 39.28, 39.30, -76.62, -76.60),
    ("Milwaukee", 43.03, 43.05, -87.92, -87.90),
]

print("\n🗺️  Major Metro Coverage:")
print("-" * 70)
print(f"{'City':<25} {'Venues':>10} {'Status':>15}")
print("-" * 70)

sparse_cities = []
good_cities = []

for name, lat_min, lat_max, lng_min, lng_max in regions:
    cmd = f'''mysql -u neutraleats_user -pneutraleats_pass neutraleats -e "SELECT COUNT(*) FROM venues WHERE lat BETWEEN {lat_min} AND {lat_max} AND lng BETWEEN {lng_min} AND {lng_max};"'''
    stdin, stdout, stderr = ssh.exec_command(cmd)
    result = stdout.read().decode().strip().split('\n')
    count = int(result[-1]) if result[-1].isdigit() else 0
    
    status = "🔴 Sparse" if count < 50 else "🟡 Okay" if count < 200 else "🟢 Good"
    print(f"{name:<25} {count:>10} {status:>15}")
    
    if count < 50:
        sparse_cities.append((name, lat_min, lat_max, lng_min, lng_max, count))
    elif count >= 200:
        good_cities.append((name, count))

print("\n" + "="*70)
print(f"\n✅ Well covered: {len(good_cities)} cities")
print(f"⚠️  Needs attention: {len(sparse_cities)} cities")

if sparse_cities:
    print("\n🔴 Priority cities for enrichment:")
    for city, _, _, _, _, count in sparse_cities[:10]:
        print(f"   - {city}: {count} venues")

ssh.close()
