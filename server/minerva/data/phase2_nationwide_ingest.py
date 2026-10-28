#!/usr/bin/env python3
"""
Neutral Eats Phase 2 - Nationwide Expansion
Ingest venues for ALL remaining 40 US states not covered in Phase 1
Target: 40,000-60,000 additional venues (100,000+ total nationwide)

Phase 1 covered: California, Texas, New York, Illinois, Pennsylvania, Ohio, Georgia, North Carolina, Michigan, New Jersey
Phase 2 covers: Alabama, Alaska, Arizona, Arkansas, Colorado, Connecticut, Delaware, Florida (gaps), Hawaii, Idaho, Indiana, Iowa, Kansas, Kentucky, Louisiana, Maine, Maryland, Massachusetts, Minnesota, Mississippi, Missouri, Montana, Nebraska, Nevada, New Hampshire, New Mexico, North Dakota, Oklahoma, Oregon, Rhode Island, South Carolina, South Dakota, Tennessee, Utah, Vermont, Virginia, Washington, West Virginia, Wisconsin, Wyoming
"""

import sqlite3
import requests
import time
import json
from datetime import datetime
from typing import List, Dict, Tuple
import logging
import sys

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('phase2_nationwide_ingest.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

DB_PATH = '/var/www/html/minerva/data/neutraleats.db'

# Progress tracking
PROGRESS_INTERVAL = 10000
last_progress_report = 0

# ============================================
# MAJOR METROS FOR ALL 40 PHASE 2 STATES
# ============================================

# Alabama
ALABAMA = [
    ('Birmingham, AL', 33.5207, -86.8025),
    ('Montgomery, AL', 32.3792, -86.3077),
    ('Huntsville, AL', 34.7304, -86.5861),
    ('Mobile, AL', 30.6954, -88.0399),
    ('Tuscaloosa, AL', 33.2098, -87.5692),
    ('Auburn, AL', 32.6099, -85.4808),
    ('Hoover, AL', 33.4054, -86.8114),
    ('Dothan, AL', 31.2232, -85.3905),
    ('Decatur, AL', 34.6059, -86.9833),
    ('Madison, AL', 34.6993, -86.7483),
]

# Alaska
ALASKA = [
    ('Anchorage, AK', 61.2181, -149.9003),
    ('Fairbanks, AK', 64.8378, -147.7164),
    ('Juneau, AK', 58.3019, -134.4197),
    ('Wasilla, AK', 61.5814, -149.4394),
    ('Sitka, AK', 57.0531, -135.3303),
]

# Arizona
ARIZONA = [
    ('Phoenix, AZ', 33.4484, -112.0740),
    ('Tucson, AZ', 32.2226, -110.9747),
    ('Mesa, AZ', 33.4152, -111.8315),
    ('Scottsdale, AZ', 33.4942, -111.9261),
    ('Chandler, AZ', 33.3062, -111.8413),
    ('Glendale, AZ', 33.5387, -112.1860),
    ('Tempe, AZ', 33.4255, -111.9400),
    ('Gilbert, AZ', 33.3528, -111.7890),
    ('Peoria, AZ', 33.5806, -112.2374),
    ('Surprise, AZ', 33.6292, -112.3680),
    ('Sedona, AZ', 34.8697, -111.7610),
    ('Flagstaff, AZ', 35.1983, -111.6513),
]

# Arkansas
ARKANSAS = [
    ('Little Rock, AR', 34.7465, -92.2896),
    ('Fayetteville, AR', 36.0626, -94.1574),
    ('Fort Smith, AR', 35.3859, -94.3985),
    ('Springdale, AR', 36.1867, -94.1288),
    ('Jonesboro, AR', 35.8423, -90.7043),
    ('Rogers, AR', 36.3320, -94.1185),
    ('Conway, AR', 35.0887, -92.4421),
    ('Bentonville, AR', 36.3729, -94.2088),
    ('North Little Rock, AR', 34.7695, -92.2671),
    ('Hot Springs, AR', 34.5037, -93.0552),
]

# Colorado
COLORADO = [
    ('Denver, CO', 39.7392, -104.9903),
    ('Colorado Springs, CO', 38.8339, -104.8214),
    ('Aurora, CO', 39.7294, -104.8319),
    ('Fort Collins, CO', 40.5853, -105.0844),
    ('Lakewood, CO', 39.7047, -105.0814),
    ('Thornton, CO', 39.8680, -104.9719),
    ('Arvada, CO', 39.8028, -105.0875),
    ('Westminster, CO', 39.8367, -105.0372),
    ('Pueblo, CO', 38.2544, -104.6091),
    ('Centennial, CO', 39.5807, -104.8772),
    ('Boulder, CO', 40.0150, -105.2705),
    ('Greeley, CO', 40.4233, -104.7081),
    ('Aspen, CO', 39.1911, -106.8175),
    ('Vail, CO', 39.6403, -106.3742),
]

# Connecticut
CONNECTICUT = [
    ('Bridgeport, CT', 41.1865, -73.1952),
    ('New Haven, CT', 41.3083, -72.9279),
    ('Stamford, CT', 41.0534, -73.5387),
    ('Hartford, CT', 41.7658, -72.6734),
    ('Waterbury, CT', 41.5582, -73.0515),
    ('Norwalk, CT', 41.1177, -73.4082),
    ('Danbury, CT', 41.3948, -73.4540),
    ('New Britain, CT', 41.6612, -72.7795),
    ('Greenwich, CT', 41.0262, -73.6282),
    ('Fairfield, CT', 41.1408, -73.2613),
]

# Delaware
DELAWARE = [
    ('Wilmington, DE', 39.7391, -75.5398),
    ('Dover, DE', 39.1582, -75.5244),
    ('Newark, DE', 39.6837, -75.7497),
    ('Middletown, DE', 39.4496, -75.7163),
    ('Rehoboth Beach, DE', 38.7209, -75.0760),
]

# Florida (gaps - additional cities)
FLORIDA_GAPS = [
    ('Tallahassee, FL', 30.4383, -84.2807),
    ('Gainesville, FL', 29.6516, -82.3248),
    ('Ocala, FL', 29.1872, -82.1401),
    ('Panama City, FL', 30.1588, -85.6602),
    ('Destin, FL', 30.3935, -86.4958),
    ('Titusville, FL', 28.6122, -80.8076),
    ('Sebring, FL', 27.4956, -81.4409),
    ('Palatka, FL', 29.6486, -81.6376),
    ('Lake City, FL', 30.1897, -82.6393),
]

# Hawaii
HAWAII = [
    ('Honolulu, HI', 21.3099, -157.8581),
    ('Hilo, HI', 19.7297, -155.0870),
    ('Kailua, HI', 21.4022, -157.7394),
    ('Kahului, HI', 20.8893, -156.4729),
    ('Kaneohe, HI', 21.4184, -157.8036),
    ('Mililani, HI', 21.4513, -158.0153),
    ('Pearl City, HI', 21.3972, -157.9652),
    ('Waipahu, HI', 21.3867, -158.0092),
    ('Kihei, HI', 20.7634, -156.4487),
    ('Lahaina, HI', 20.8783, -156.6825),
    ('Kona, HI', 19.6398, -155.9969),
]

# Idaho
IDAHO = [
    ('Boise, ID', 43.6150, -116.2023),
    ('Meridian, ID', 43.6121, -116.3915),
    ('Nampa, ID', 43.5407, -116.5635),
    ('Idaho Falls, ID', 43.4666, -112.0341),
    ('Pocatello, ID', 42.8713, -112.4455),
    ('Caldwell, ID', 43.6629, -116.6874),
    ('Coeur dAlene, ID', 47.6777, -116.7805),
    ('Twin Falls, ID', 42.5630, -114.4609),
    ('Lewiston, ID', 46.4004, -117.0012),
    ('Post Falls, ID', 47.7180, -116.9516),
    ('Sun Valley, ID', 43.6771, -114.3420),
]

# Indiana
INDIANA = [
    ('Indianapolis, IN', 39.7684, -86.1581),
    ('Fort Wayne, IN', 41.0793, -85.1394),
    ('Evansville, IN', 37.9716, -87.5711),
    ('South Bend, IN', 41.6764, -86.2520),
    ('Carmel, IN', 39.9784, -86.1180),
    ('Fishers, IN', 39.9567, -86.0134),
    ('Bloomington, IN', 39.1653, -86.5264),
    ('Hammond, IN', 41.5834, -87.5000),
    ('Gary, IN', 41.5934, -87.3369),
    ('Lafayette, IN', 40.4167, -86.8753),
    ('Muncie, IN', 40.1934, -85.3864),
    ('Noblesville, IN', 40.0456, -86.0086),
    ('Terre Haute, IN', 39.4667, -87.4139),
    ('West Lafayette, IN', 40.4259, -86.9081),
    ('South Bend, IN', 41.6764, -86.2520),
]

# Iowa
IOWA = [
    ('Des Moines, IA', 41.5868, -93.6250),
    ('Cedar Rapids, IA', 41.9779, -91.6656),
    ('Davenport, IA', 41.5236, -90.5776),
    ('Sioux City, IA', 42.4963, -96.4049),
    ('Iowa City, IA', 41.6611, -91.5302),
    ('Waterloo, IA', 42.4928, -92.3426),
    ('Ames, IA', 42.0308, -93.6319),
    ('West Des Moines, IA', 41.5772, -93.7113),
    ('Council Bluffs, IA', 41.2619, -95.8608),
    ('Dubuque, IA', 42.5006, -90.6646),
]

# Kansas
KANSAS = [
    ('Wichita, KS', 37.6872, -97.3301),
    ('Overland Park, KS', 38.9822, -94.6708),
    ('Kansas City, KS', 39.1142, -94.6275),
    ('Olathe, KS', 38.8814, -94.8191),
    ('Topeka, KS', 39.0473, -95.6752),
    ('Lawrence, KS', 38.9717, -95.2353),
    ('Shawnee, KS', 39.0228, -94.7152),
    ('Manhattan, KS', 39.1836, -96.5717),
    ('Lenexa, KS', 38.9536, -94.7336),
    ('Salina, KS', 38.8403, -97.6114),
]

# Kentucky
KENTUCKY = [
    ('Louisville, KY', 38.2527, -85.7585),
    ('Lexington, KY', 38.0406, -84.5037),
    ('Bowling Green, KY', 36.9685, -86.4808),
    ('Owensboro, KY', 37.7719, -87.1112),
    ('Covington, KY', 39.0837, -84.5086),
    ('Richmond, KY', 37.7479, -84.2947),
    ('Georgetown, KY', 38.2098, -84.5588),
    ('Florence, KY', 38.9989, -84.6266),
    ('Hopkinsville, KY', 36.8656, -87.4886),
    ('Nicholasville, KY', 37.8806, -84.5730),
]

# Louisiana
LOUISIANA = [
    ('New Orleans, LA', 29.9511, -90.0715),
    ('Baton Rouge, LA', 30.4515, -91.1871),
    ('Shreveport, LA', 32.5252, -93.7502),
    ('Lafayette, LA', 30.2241, -92.0198),
    ('Lake Charles, LA', 30.2266, -93.2174),
    ('Kenner, LA', 29.9941, -90.2417),
    ('Bossier City, LA', 32.5160, -93.7321),
    ('Monroe, LA', 32.5093, -92.1193),
    ('Alexandria, LA', 31.3113, -92.4451),
    ('Houma, LA', 29.5958, -90.7195),
    ('Slidell, LA', 30.2752, -89.7812),
]

# Maine
MAINE = [
    ('Portland, ME', 43.6591, -70.2568),
    ('Lewiston, ME', 44.1004, -70.2148),
    ('Bangor, ME', 44.8016, -68.7712),
    ('South Portland, ME', 43.6415, -70.2409),
    ('Auburn, ME', 44.0978, -70.2312),
    ('Biddeford, ME', 43.4926, -70.4534),
    ('Scarborough, ME', 43.5781, -70.3259),
    ('Brunswick, ME', 43.9140, -69.9679),
    ('Saco, ME', 43.5009, -70.4428),
    ('Augusta, ME', 44.3106, -69.7795),
    ('Bar Harbor, ME', 44.3876, -68.2039),
]

# Maryland
MARYLAND = [
    ('Baltimore, MD', 39.2904, -76.6122),
    ('Frederick, MD', 39.4143, -77.4105),
    ('Rockville, MD', 39.0839, -77.1531),
    ('Gaithersburg, MD', 39.1434, -77.2014),
    ('Bowie, MD', 39.0068, -76.7791),
    ('Hagerstown, MD', 39.6418, -77.7200),
    ('Annapolis, MD', 38.9784, -76.4922),
    ('College Park, MD', 38.9897, -76.9378),
    ('Salisbury, MD', 38.3607, -75.5994),
    ('Laurel, MD', 39.0993, -76.8483),
    ('Bethesda, MD', 38.9847, -77.0947),
    ('Silver Spring, MD', 38.9907, -77.0261),
    ('Towson, MD', 39.4015, -76.6019),
    ('Columbia, MD', 39.2037, -76.8610),
    ('Ocean City, MD', 38.3365, -75.0849),
]

# Massachusetts
MASSACHUSETTS = [
    ('Boston, MA', 42.3601, -71.0589),
    ('Worcester, MA', 42.2626, -71.8023),
    ('Springfield, MA', 42.1015, -72.5898),
    ('Cambridge, MA', 42.3736, -71.1097),
    ('Lowell, MA', 42.6334, -71.3162),
    ('Brockton, MA', 42.0834, -71.0184),
    ('Quincy, MA', 42.2529, -71.0023),
    ('Lynn, MA', 42.4668, -70.9495),
    ('New Bedford, MA', 41.6362, -70.9342),
    ('Fall River, MA', 41.7015, -71.1550),
    ('Somerville, MA', 42.3876, -71.0995),
    ('Lawrence, MA', 42.7070, -71.1631),
    ('Newton, MA', 42.3370, -71.2092),
    ('Framingham, MA', 42.2793, -71.4162),
    ('Waltham, MA', 42.3765, -71.2356),
    ('Plymouth, MA', 41.9584, -70.6673),
    ('Salem, MA', 42.5195, -70.8967),
]

# Minnesota
MINNESOTA = [
    ('Minneapolis, MN', 44.9778, -93.2650),
    ('Saint Paul, MN', 44.9537, -93.0900),
    ('Rochester, MN', 44.0121, -92.4802),
    ('Duluth, MN', 46.7867, -92.1005),
    ('Bloomington, MN', 44.8408, -93.2983),
    ('Brooklyn Park, MN', 45.0941, -93.3564),
    ('Plymouth, MN', 45.0105, -93.4555),
    ('St. Cloud, MN', 45.5579, -94.1632),
    ('Eagan, MN', 44.8041, -93.1669),
    ('Woodbury, MN', 44.9239, -92.9594),
    ('Maple Grove, MN', 45.0725, -93.4558),
    ('Eden Prairie, MN', 44.8547, -93.4708),
    ('Minnetonka, MN', 44.9213, -93.4683),
    ('St. Louis Park, MN', 44.9594, -93.3702),
    ('Mankato, MN', 44.1636, -93.9994),
]

# Mississippi
MISSISSIPPI = [
    ('Jackson, MS', 32.2988, -90.1848),
    ('Gulfport, MS', 30.3674, -89.0928),
    ('Southaven, MS', 34.9890, -90.0126),
    ('Hattiesburg, MS', 31.3271, -89.2903),
    ('Biloxi, MS', 30.3960, -88.8853),
    ('Meridian, MS', 32.3643, -88.7037),
    ('Tupelo, MS', 34.2576, -88.7034),
    ('Greenville, MS', 33.4101, -91.0618),
    ('Olive Branch, MS', 34.9618, -89.8295),
    ('Horn Lake, MS', 34.9554, -90.0340),
    ('Oxford, MS', 34.3665, -89.5192),
    ('Natchez, MS', 31.5604, -91.4032),
]

# Missouri
MISSOURI = [
    ('Kansas City, MO', 39.0997, -94.5786),
    ('St. Louis, MO', 38.6270, -90.1994),
    ('Springfield, MO', 37.2089, -93.2923),
    ('Columbia, MO', 38.9517, -92.3341),
    ('Independence, MO', 39.0911, -94.4155),
    ('Lee Summit, MO', 38.9108, -94.3822),
    ("O'Fallon, MO", 38.8106, -90.6998),
    ('St. Joseph, MO', 39.7675, -94.8466),
    ('St. Charles, MO', 38.7881, -90.4974),
    ('St. Peters, MO', 38.8003, -90.6265),
    ('Blue Springs, MO', 39.0169, -94.2816),
    ('Joplin, MO', 37.0842, -94.5133),
    ('Florissant, MO', 38.7892, -90.3226),
    ('Chesterfield, MO', 38.6631, -90.5771),
    ('Jefferson City, MO', 38.5767, -92.1735),
    ('Branson, MO', 36.6437, -93.2185),
]

# Montana
MONTANA = [
    ('Billings, MT', 45.7833, -108.5007),
    ('Missoula, MT', 46.8721, -113.9940),
    ('Great Falls, MT', 47.5052, -111.3008),
    ('Bozeman, MT', 45.6760, -111.0429),
    ('Butte, MT', 46.0038, -112.5378),
    ('Helena, MT', 46.5891, -112.0391),
    ('Kalispell, MT', 48.1920, -114.3168),
    ('Havre, MT', 48.5500, -109.6841),
    ('Whitefish, MT', 48.4111, -114.3376),
    ('Livingston, MT', 45.6624, -110.5610),
    ('Big Sky, MT', 45.2617, -111.3080),
]

# Nebraska
NEBRASKA = [
    ('Omaha, NE', 41.2565, -95.9345),
    ('Lincoln, NE', 40.8136, -96.7026),
    ('Bellevue, NE', 41.1544, -95.9146),
    ('Grand Island, NE', 40.9264, -98.3420),
    ('Kearney, NE', 40.6993, -99.0817),
    ('Fremont, NE', 41.4334, -96.4981),
    ('Hastings, NE', 40.5863, -98.3899),
    ('Norfolk, NE', 42.0323, -97.4170),
    ('North Platte, NE', 41.1239, -100.7654),
    ('Columbus, NE', 41.4297, -97.3684),
]

# Nevada
NEVADA = [
    ('Las Vegas, NV', 36.1699, -115.1398),
    ('Henderson, NV', 36.0395, -114.9817),
    ('Reno, NV', 39.5296, -119.8138),
    ('North Las Vegas, NV', 36.1989, -115.1175),
    ('Enterprise, NV', 36.0250, -115.2419),
    ('Spring Valley, NV', 36.1080, -115.2450),
    ('Sunrise Manor, NV', 36.2111, -115.0731),
    ('Paradise, NV', 36.0972, -115.1467),
    ('Sparks, NV', 39.5349, -119.7527),
    ('Carson City, NV', 39.1638, -119.7674),
    ('Elko, NV', 40.8324, -115.7631),
    ('Lake Tahoe, NV', 39.0968, -120.0324),
]

# New Hampshire
NEW_HAMPSHIRE = [
    ('Manchester, NH', 42.9956, -71.4548),
    ('Nashua, NH', 42.7654, -71.4676),
    ('Concord, NH', 43.2081, -71.5376),
    ('Derry, NH', 42.8806, -71.3273),
    ('Dover, NH', 43.1979, -70.8737),
    ('Rochester, NH', 43.3045, -70.9756),
    ('Salem, NH', 42.7886, -71.2009),
    ('Merrimack, NH', 42.8651, -71.4939),
    ('Londonderry, NH', 42.8651, -71.3739),
    ('Keene, NH', 42.9337, -72.2781),
    ('Portsmouth, NH', 43.0718, -70.7626),
    ('Hanover, NH', 43.7022, -72.2896),
    ('North Conway, NH', 44.0537, -71.1287),
]

# New Mexico
NEW_MEXICO = [
    ('Albuquerque, NM', 35.0844, -106.6504),
    ('Las Cruces, NM', 32.3199, -106.7637),
    ('Rio Rancho, NM', 35.2334, -106.6645),
    ('Santa Fe, NM', 35.6870, -105.9378),
    ('Roswell, NM', 33.3943, -104.5230),
    ('Farmington, NM', 36.7281, -108.2187),
    ('Clovis, NM', 34.4048, -103.2052),
    ('Hobbs, NM', 32.7026, -103.1360),
    ('Alamogordo, NM', 32.8995, -105.9603),
    ('Carlsbad, NM', 32.4207, -104.2283),
    ('Taos, NM', 36.4072, -105.5730),
]

# North Dakota
NORTH_DAKOTA = [
    ('Fargo, ND', 46.8772, -96.7898),
    ('Bismarck, ND', 46.8083, -100.7837),
    ('Grand Forks, ND', 47.9253, -97.0329),
    ('Minot, ND', 48.2325, -101.2963),
    ('West Fargo, ND', 46.8769, -96.9004),
    ('Williston, ND', 48.1470, -103.6180),
    ('Dickinson, ND', 46.8792, -102.7896),
    ('Mandan, ND', 46.8267, -100.8896),
    ('Jamestown, ND', 46.9105, -98.7084),
]

# Oklahoma
OKLAHOMA = [
    ('Oklahoma City, OK', 35.4676, -97.5164),
    ('Tulsa, OK', 36.1540, -95.9928),
    ('Norman, OK', 35.2226, -97.4395),
    ('Broken Arrow, OK', 36.0609, -95.7975),
    ('Lawton, OK', 34.6036, -98.3959),
    ('Edmond, OK', 35.6528, -97.4781),
    ('Moore, OK', 35.3395, -97.4867),
    ('Midwest City, OK', 35.4495, -97.3967),
    ('Enid, OK', 36.3956, -97.8784),
    ('Stillwater, OK', 36.1156, -97.0584),
    ('Muskogee, OK', 35.7479, -95.3697),
]

# Oregon
OREGON = [
    ('Portland, OR', 45.5152, -122.6784),
    ('Salem, OR', 44.9429, -123.0351),
    ('Eugene, OR', 44.0521, -123.0868),
    ('Gresham, OR', 45.5054, -122.4345),
    ('Hillsboro, OR', 45.5229, -122.9898),
    ('Beaverton, OR', 45.4871, -122.8037),
    ('Bend, OR', 44.0582, -121.3153),
    ('Medford, OR', 42.3265, -122.8756),
    ('Springfield, OR', 44.0462, -123.0220),
    ('Corvallis, OR', 44.5646, -123.2620),
    ('Albany, OR', 44.6368, -123.1059),
    ('Tigard, OR', 45.4312, -122.7715),
    ('Lake Oswego, OR', 45.4207, -122.6737),
    ('Grants Pass, OR', 42.4390, -123.3284),
    ('Ashland, OR', 42.1946, -122.7095),
    ('Cannon Beach, OR', 45.8918, -123.9615),
]

# Rhode Island
RHODE_ISLAND = [
    ('Providence, RI', 41.8240, -71.4128),
    ('Warwick, RI', 41.7001, -71.4162),
    ('Cranston, RI', 41.7798, -71.4373),
    ('Pawtucket, RI', 41.8787, -71.3826),
    ('East Providence, RI', 41.8137, -71.3701),
    ('Woonsocket, RI', 42.0029, -71.5148),
    ('Cumberland, RI', 41.9668, -71.4328),
    ('Coventry, RI', 41.7001, -71.6828),
    ('North Providence, RI', 41.8501, -71.4665),
    ('South Kingstown, RI', 41.4478, -71.4495),
    ('Newport, RI', 41.4901, -71.3128),
]

# South Carolina
SOUTH_CAROLINA = [
    ('Charleston, SC', 32.7765, -79.9311),
    ('Columbia, SC', 34.0007, -81.0348),
    ('North Charleston, SC', 32.8546, -79.9748),
    ('Mount Pleasant, SC', 32.7941, -79.8626),
    ('Rock Hill, SC', 34.9249, -81.0251),
    ('Greenville, SC', 34.8526, -82.3940),
    ('Summerville, SC', 33.0185, -80.1756),
    ('Sumter, SC', 33.9204, -80.3415),
    ('Goose Creek, SC', 32.9810, -80.0326),
    ('Hilton Head Island, SC', 32.2163, -80.7526),
    ('Florence, SC', 34.1954, -79.7626),
    ('Spartanburg, SC', 34.9496, -81.9320),
    ('Myrtle Beach, SC', 33.6891, -78.8867),
    ('Aiken, SC', 33.5604, -81.7196),
    ('Greer, SC', 34.9387, -82.2271),
    ('Beaufort, SC', 32.4316, -80.6698),
]

# South Dakota
SOUTH_DAKOTA = [
    ('Sioux Falls, SD', 43.5473, -96.7283),
    ('Rapid City, SD', 44.0805, -103.2310),
    ('Aberdeen, SD', 45.4647, -98.4865),
    ('Brookings, SD', 44.3114, -96.7984),
    ('Watertown, SD', 44.8994, -97.1151),
    ('Mitchell, SD', 43.7094, -98.0298),
    ('Yankton, SD', 42.8711, -97.3973),
    ('Pierre, SD', 44.3683, -100.3510),
    ('Huron, SD', 44.3633, -98.2140),
    ('Spearfish, SD', 44.4908, -103.8594),
    ('Deadwood, SD', 44.3767, -103.7296),
]

# Tennessee
TENNESSEE = [
    ('Nashville, TN', 36.1627, -86.7816),
    ('Memphis, TN', 35.1495, -90.0490),
    ('Knoxville, TN', 35.9606, -83.9207),
    ('Chattanooga, TN', 35.0456, -85.3097),
    ('Clarksville, TN', 36.5298, -87.3595),
    ('Murfreesboro, TN', 35.8456, -86.3903),
    ('Franklin, TN', 35.9251, -86.8689),
    ('Jackson, TN', 35.6145, -88.8139),
    ('Johnson City, TN', 36.3134, -82.3535),
    ('Bartlett, TN', 35.2045, -89.8740),
    ('Hendersonville, TN', 36.3048, -86.6200),
    ('Kingsport, TN', 36.5484, -82.5618),
    ('Collierville, TN', 35.0420, -89.6645),
    ('Cleveland, TN', 35.1595, -84.8766),
    ('Smyrna, TN', 35.9828, -86.5186),
    ('Gatlinburg, TN', 35.7143, -83.5102),
    ('Pigeon Forge, TN', 35.7884, -83.5543),
]

# Utah (Salt Lake City priority)
UTAH = [
    ('Salt Lake City, UT', 40.7608, -111.8910),
    ('West Valley City, UT', 40.6916, -112.0011),
    ('Provo, UT', 40.2338, -111.6585),
    ('West Jordan, UT', 40.6097, -111.9391),
    ('Orem, UT', 40.2969, -111.6946),
    ('Sandy, UT', 40.5650, -111.8389),
    ('Ogden, UT', 41.2230, -111.9738),
    ('St. George, UT', 37.0965, -113.5684),
    ('Layton, UT', 41.0602, -111.9710),
    ('South Jordan, UT', 40.5622, -111.9297),
    ('Lehi, UT', 40.3916, -111.8508),
    ('Millcreek, UT', 40.6869, -111.8755),
    ('Taylorsville, UT', 40.6677, -111.9388),
    ('Logan, UT', 41.7350, -111.8338),
    ('Murray, UT', 40.6669, -111.8880),
    ('Draper, UT', 40.5247, -111.8638),
    ('Bountiful, UT', 40.8894, -111.8808),
    ('Riverton, UT', 40.5219, -111.9391),
    ('Roy, UT', 41.1616, -112.0263),
    ('Cottonwood Heights, UT', 40.6197, -111.8102),
    ('Park City, UT', 40.6461, -111.4980),
    ('Moab, UT', 38.5733, -109.5498),
]

# Vermont
VERMONT = [
    ('Burlington, VT', 44.4759, -73.2121),
    ('South Burlington, VT', 44.4670, -73.1700),
    ('Rutland, VT', 43.6106, -72.9726),
    ('Barre, VT', 44.1970, -72.5020),
    ('Montpelier, VT', 44.2601, -72.5754),
    ('Winooski, VT', 44.4914, -73.1857),
    ('St. Albans, VT', 44.8108, -73.0832),
    ('Middlebury, VT', 44.0153, -73.1673),
    ('Brattleboro, VT', 42.8509, -72.5579),
    ('Bennington, VT', 42.8781, -73.1968),
    ('Stowe, VT', 44.4654, -72.6874),
    ('Killington, VT', 43.6775, -72.7797),
]

# Virginia
VIRGINIA = [
    ('Virginia Beach, VA', 36.8529, -75.9780),
    ('Norfolk, VA', 36.8508, -76.2859),
    ('Chesapeake, VA', 36.7682, -76.2875),
    ('Richmond, VA', 37.5407, -77.4360),
    ('Newport News, VA', 37.0871, -76.4730),
    ('Alexandria, VA', 38.8048, -77.0469),
    ('Hampton, VA', 37.0299, -76.3452),
    ('Roanoke, VA', 37.2710, -79.9414),
    ('Portsmouth, VA', 36.8354, -76.2983),
    ('Suffolk, VA', 36.7282, -76.5836),
    ('Lynchburg, VA', 37.4138, -79.1422),
    ('Harrisonburg, VA', 38.4496, -78.8689),
    ('Charlottesville, VA', 38.0293, -78.4767),
    ('Danville, VA', 36.5860, -79.3950),
    ('Blacksburg, VA', 37.2296, -80.4139),
    ('Manassas, VA', 38.7509, -77.4753),
    ('Fredericksburg, VA', 38.3032, -77.4605),
    ('Winchester, VA', 39.1857, -78.1633),
    ('Williamsburg, VA', 37.2707, -76.7075),
    ('Leesburg, VA', 39.1157, -77.5636),
    ('Reston, VA', 38.9586, -77.3570),
    ('Arlington, VA', 38.8816, -77.0910),
    ('Fairfax, VA', 38.8462, -77.3064),
    ('Tysons, VA', 38.9187, -77.2311),
    ('Chantilly, VA', 38.8943, -77.4311),
    ('McLean, VA', 38.9339, -77.1773),
    ('Vienna, VA', 38.9012, -77.2653),
    ('Falls Church, VA', 38.8823, -77.1711),
    ('Herndon, VA', 38.9696, -77.3861),
    ('Sterling, VA', 39.0026, -77.4286),
]

# Washington
WASHINGTON = [
    ('Seattle, WA', 47.6062, -122.3321),
    ('Spokane, WA', 47.6587, -117.4260),
    ('Tacoma, WA', 47.2529, -122.4443),
    ('Vancouver, WA', 45.6387, -122.6615),
    ('Bellevue, WA', 47.6101, -122.2015),
    ('Kent, WA', 47.3809, -122.2348),
    ('Everett, WA', 47.9787, -122.2021),
    ('Renton, WA', 47.4829, -122.2171),
    ('Yakima, WA', 46.6021, -120.5059),
    ('Federal Way, WA', 47.3223, -122.3126),
    ('Spokane Valley, WA', 47.6733, -117.2394),
    ('Bellingham, WA', 48.7519, -122.4787),
    ('Kennewick, WA', 46.2112, -119.1372),
    ('Auburn, WA', 47.3073, -122.2285),
    ('Pasco, WA', 46.2396, -119.1006),
    ('Marysville, WA', 48.0518, -122.1771),
    ('Lakewood, WA', 47.1718, -122.5180),
    ('Redmond, WA', 47.6740, -122.1215),
    ('Shoreline, WA', 47.7557, -122.3415),
    ('Richland, WA', 46.2857, -119.2845),
    ('Kirkland, WA', 47.6769, -122.2060),
    ('Sammamish, WA', 47.6163, -122.0356),
    ('Olympia, WA', 47.0379, -122.9007),
    ('Bremerton, WA', 47.5673, -122.6329),
    ('Portland East, WA', 45.6272, -122.6727),
    ('Leavenworth, WA', 47.5962, -120.6615),
]

# West Virginia
WEST_VIRGINIA = [
    ('Charleston, WV', 38.3498, -81.6326),
    ('Huntington, WV', 38.4192, -82.4452),
    ('Morgantown, WV', 39.6295, -79.9559),
    ('Parkersburg, WV', 39.2667, -81.5615),
    ('Wheeling, WV', 40.0640, -80.7209),
    ('Weirton, WV', 40.4190, -80.5895),
    ('Fairmont, WV', 39.4851, -80.1426),
    ('Beckley, WV', 37.7782, -81.1882),
    ('Clarksburg, WV', 39.2806, -80.3445),
    ('Martinsburg, WV', 39.4562, -77.9639),
    ('South Charleston, WV', 38.3684, -81.6996),
    ('St. Albans, WV', 38.3856, -81.8363),
    ('Vienna, WV', 39.3265, -81.5496),
    ('Bluefield, WV', 37.2698, -81.2223),
    ('Oak Hill, WV', 37.9729, -81.1487),
]

# Wisconsin
WISCONSIN = [
    ('Milwaukee, WI', 43.0389, -87.9065),
    ('Madison, WI', 43.0731, -89.4012),
    ('Green Bay, WI', 44.5133, -88.0133),
    ('Kenosha, WI', 42.5847, -87.8212),
    ('Racine, WI', 42.7261, -87.7829),
    ('Appleton, WI', 44.2619, -88.4154),
    ('Waukesha, WI', 43.0117, -88.2315),
    ('Eau Claire, WI', 44.8113, -91.4985),
    ('Oshkosh, WI', 44.0170, -88.5426),
    ('Janesville, WI', 42.6828, -89.0187),
    ('West Allis, WI', 43.0167, -88.0070),
    ('La Crosse, WI', 43.8014, -91.2396),
    ('Sheboygan, WI', 43.7508, -87.7145),
    ('Wausau, WI', 44.9591, -89.6301),
    ('Fond du Lac, WI', 43.7730, -88.4471),
    ('New Berlin, WI', 42.9764, -88.1084),
    ('Wauwatosa, WI', 43.0495, -88.0076),
    ('Brookfield, WI', 43.0606, -88.1065),
    ('Greenfield, WI', 42.9614, -88.0126),
    ('Beloit, WI', 42.5083, -89.0318),
    ('Menomonee Falls, WI', 43.1789, -88.1173),
    ('Franklin, WI', 42.8886, -88.0384),
    ('Sun Prairie, WI', 43.1836, -89.2137),
    ('Oak Creek, WI', 42.8859, -87.8631),
    ('Manitowoc, WI', 44.0886, -87.6576),
    ('West Bend, WI', 43.4253, -88.1834),
    ('Mount Pleasant, WI', 42.6974, -87.8559),
    ('Neenah, WI', 44.1858, -88.4626),
    ('Superior, WI', 46.7208, -92.1041),
    ('Stevens Point, WI', 44.5236, -89.5743),
    ('De Pere, WI', 44.4489, -88.0604),
    ('Cudahy, WI', 42.9597, -87.8675),
    ('Wisconsin Dells, WI', 43.6275, -89.7710),
    ('Lake Geneva, WI', 42.5917, -88.4334),
    ('Door County, WI', 45.0697, -87.0541),
]

# Wyoming
WYOMING = [
    ('Cheyenne, WY', 41.1400, -104.8203),
    ('Casper, WY', 42.8501, -106.3252),
    ('Laramie, WY', 41.3114, -105.5911),
    ('Gillette, WY', 44.2911, -105.5022),
    ('Rock Springs, WY', 41.5875, -109.2029),
    ('Sheridan, WY', 44.7972, -106.9562),
    ('Green River, WY', 41.5286, -109.4662),
    ('Evanston, WY', 41.2683, -110.9633),
    ('Riverton, WY', 43.0250, -108.3801),
    ('Jackson, WY', 43.4799, -110.7624),
    ('Cody, WY', 44.5263, -109.0565),
    ('Rawlins, WY', 41.7911, -107.2387),
    ('Lander, WY', 42.8330, -108.7307),
    ('Torrington, WY', 42.0625, -104.1844),
    ('Yellowstone, WY', 44.4280, -110.5885),
]

# Combine all areas
ALL_AREAS = [
    ('ALABAMA', ALABAMA),
    ('ALASKA', ALASKA),
    ('ARIZONA', ARIZONA),
    ('ARKANSAS', ARKANSAS),
    ('COLORADO', COLORADO),
    ('CONNECTICUT', CONNECTICUT),
    ('DELAWARE', DELAWARE),
    ('FLORIDA_GAPS', FLORIDA_GAPS),
    ('HAWAII', HAWAII),
    ('IDAHO', IDAHO),
    ('INDIANA', INDIANA),
    ('IOWA', IOWA),
    ('KANSAS', KANSAS),
    ('KENTUCKY', KENTUCKY),
    ('LOUISIANA', LOUISIANA),
    ('MAINE', MAINE),
    ('MARYLAND', MARYLAND),
    ('MASSACHUSETTS', MASSACHUSETTS),
    ('MINNESOTA', MINNESOTA),
    ('MISSISSIPPI', MISSISSIPPI),
    ('MISSOURI', MISSOURI),
    ('MONTANA', MONTANA),
    ('NEBRASKA', NEBRASKA),
    ('NEVADA', NEVADA),
    ('NEW_HAMPSHIRE', NEW_HAMPSHIRE),
    ('NEW_MEXICO', NEW_MEXICO),
    ('NORTH_DAKOTA', NORTH_DAKOTA),
    ('OKLAHOMA', OKLAHOMA),
    ('OREGON', OREGON),
    ('RHODE_ISLAND', RHODE_ISLAND),
    ('SOUTH_CAROLINA', SOUTH_CAROLINA),
    ('SOUTH_DAKOTA', SOUTH_DAKOTA),
    ('TENNESSEE', TENNESSEE),
    ('UTAH', UTAH),
    ('VERMONT', VERMONT),
    ('VIRGINIA', VIRGINIA),
    ('WASHINGTON', WASHINGTON),
    ('WEST_VIRGINIA', WEST_VIRGINIA),
    ('WISCONSIN', WISCONSIN),
    ('WYOMING', WYOMING),
]


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def fetch_restaurants(lat: float, lng: float, radius: int = 5000) -> List[Dict]:
    """Fetch restaurants from Overpass API with 5km radius (configurable up to 10km)"""
    query = f"""[out:json][timeout:25];(node["amenity"~"restaurant|fast_food|cafe|bar|pub|biergarten"](around:{radius},{lat},{lng});way["amenity"~"restaurant|fast_food|cafe|bar|pub|biergarten"](around:{radius},{lat},{lng}););out center;"""
    
    try:
        resp = requests.post("https://overpass-api.de/api/interpreter", data={'data': query}, timeout=30)
        data = resp.json()
        venues = []
        for el in data.get('elements', []):
            tags = el.get('tags', {})
            name = tags.get('name', '')
            if not name or name.lower() in ['restaurant', 'fast food', 'cafe', 'bar']:
                continue
                
            if el['type'] == 'node':
                venues.append({
                    'id': f"osm_{el['id']}",
                    'name': name,
                    'lat': el.get('lat'),
                    'lng': el.get('lon'),
                    'type': tags.get('amenity', 'restaurant'),
                    'cuisine': tags.get('cuisine', ''),
                    'brand': tags.get('brand', '')
                })
            elif el['type'] == 'way' and 'center' in el:
                venues.append({
                    'id': f"osm_{el['id']}",
                    'name': name,
                    'lat': el['center']['lat'],
                    'lng': el['center']['lon'],
                    'type': tags.get('amenity', 'restaurant'),
                    'cuisine': tags.get('cuisine', ''),
                    'brand': tags.get('brand', '')
                })
        return venues
    except Exception as e:
        logger.error(f"Fetch error: {e}")
        return []


def generate_grid_cell(lat: float, lng: float) -> str:
    # Canonical venues.grid_cell (pipeline/merge_overture.py)
    import math
    return "%.3f,%.3f" % (math.floor(lat / 0.02) * 0.02, math.floor(lng / 0.02) * 0.02)


def save_venues(venues: List[Dict], state_name: str) -> int:
    global last_progress_report
    
    conn = get_db()
    cursor = conn.cursor()
    new_count = 0
    ts = int(time.time())
    
    for v in venues:
        lat, lng = v['lat'], v['lng']
        if not lat or not lng:
            continue
            
        # Basic filtering for obviously bad data
        if abs(lat) > 90 or abs(lng) > 180:
            continue
            
        grid_cell = generate_grid_cell(lat, lng)
        
        cursor.execute("SELECT 1 FROM venues WHERE id=?", (v['id'],))
        if not cursor.fetchone():
            new_count += 1
            cursor.execute("""INSERT INTO venues 
                (id, name, lat, lng, type, cuisine, brand, source, source_id, last_updated, first_seen, grid_cell, check_count) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                (v['id'], v['name'], lat, lng, v['type'], v.get('cuisine', ''), v.get('brand', ''), 
                 'openstreetmap', v['id'], ts, ts, grid_cell))
    
    conn.commit()
    
    # Check if we need to report progress
    cursor.execute("SELECT COUNT(*) FROM venues")
    total_venues = cursor.fetchone()[0]
    conn.close()
    
    # Report progress every 10,000 venues
    progress_milestone = (total_venues // PROGRESS_INTERVAL) * PROGRESS_INTERVAL
    if progress_milestone > last_progress_report:
        last_progress_report = progress_milestone
        logger.info(f"📊 PROGRESS MILESTONE: {total_venues:,} total venues nationwide")
    
    return new_count


def ingest_state(state_name: str, areas: List[Tuple]) -> int:
    logger.info(f"\n{'='*60}")
    logger.info(f"🗺️  PROCESSING {state_name}")
    logger.info(f"{'='*60}")
    
    total_new = 0
    state_venues_found = 0
    
    for i, (city_name, lat, lng) in enumerate(areas):
        try:
            venues = fetch_restaurants(lat, lng, radius=8000)  # 8km radius
            new = save_venues(venues, state_name)
            total_new += new
            state_venues_found += len(venues)
            logger.info(f"  [{i+1}/{len(areas)}] {city_name}: {len(venues)} found, {new} new")
            time.sleep(2)  # Rate limiting
        except Exception as e:
            logger.error(f"  ERROR in {city_name}: {e}")
            time.sleep(5)
    
    logger.info(f"✅ {state_name} complete: {state_venues_found} found, {total_new} new saved")
    return total_new


def main():
    logger.info("="*60)
    logger.info("🚀 NEUTRAL EATS PHASE 2 - NATIONWIDE EXPANSION")
    logger.info("="*60)
    logger.info("Target: 40,000-60,000 additional venues")
    logger.info("States: All 40 remaining US states")
    logger.info("="*60)
    
    conn = get_db()
    start_count = conn.execute("SELECT COUNT(*) FROM venues").fetchone()[0]
    conn.close()
    logger.info(f"📊 Starting venue count: {start_count:,}")
    
    global last_progress_report
    last_progress_report = (start_count // PROGRESS_INTERVAL) * PROGRESS_INTERVAL
    
    grand_total = 0
    state_results = []
    
    for state_name, areas in ALL_AREAS:
        try:
            state_new = ingest_state(state_name, areas)
            grand_total += state_new
            state_results.append((state_name, state_new))
            
            # Brief pause between states
            time.sleep(3)
        except Exception as e:
            logger.error(f"❌ ERROR processing {state_name}: {e}")
            state_results.append((state_name, 0))
    
    # Final summary
    conn = get_db()
    end_count = conn.execute("SELECT COUNT(*) FROM venues").fetchone()[0]
    conn.close()
    
    logger.info("\n" + "="*60)
    logger.info("📊 PHASE 2 COMPLETE - STATE SUMMARY")
    logger.info("="*60)
    for state, count in state_results:
        logger.info(f"  {state}: {count:,} new venues")
    
    logger.info("="*60)
    logger.info(f"📊 FINAL RESULTS")
    logger.info("="*60)
    logger.info(f"Starting count: {start_count:,}")
    logger.info(f"Ending count:   {end_count:,}")
    logger.info(f"Total added:    {end_count - start_count:,}")
    logger.info(f"Target:         100,000+ nationwide")
    logger.info(f"Progress:       {end_count:,} / 100,000 ({(end_count/100000)*100:.1f}%)")
    logger.info("="*60)
    
    return end_count - start_count


if __name__ == '__main__':
    main()
