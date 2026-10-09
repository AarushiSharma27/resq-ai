"""Static seed data for the simulated city of Indore (MP, India).

Coordinates are approximate and the road network is a simplified abstraction
(straight segments between major junctions). Hospitals, stations and resources are
fictional placeholders — they do NOT represent real facilities or real capacity.
"""
from __future__ import annotations

# id, name, lat, lon
INTERSECTIONS: list[tuple[str, str, float, float]] = [
    ("N_RAJWADA", "Rajwada", 22.7187, 75.8553),
    ("N_BADA_GANPATI", "Bada Ganpati", 22.7245, 75.8417),
    ("N_AIRPORT", "Airport Road Junction", 22.7216, 75.8100),
    ("N_MHOW_NAKA", "Mhow Naka", 22.7050, 75.8480),
    ("N_ANNAPURNA", "Annapurna", 22.6955, 75.8425),
    ("N_REGAL", "Regal Square / Railway Station", 22.7196, 75.8700),
    ("N_MALWA_MILL", "Malwa Mill", 22.7280, 75.8650),
    ("N_PARDESHIPURA", "Pardeshipura", 22.7390, 75.8710),
    ("N_PALASIA", "Palasia", 22.7244, 75.8839),
    ("N_GEETA_BHAWAN", "Geeta Bhawan", 22.7186, 75.8847),
    ("N_CHHAVNI", "Chhavni", 22.7090, 75.8740),
    ("N_NAVLAKHA", "Navlakha", 22.7010, 75.8830),
    ("N_BHAWARKUAN", "Bhawarkuan", 22.6926, 75.8672),
    ("N_LIG", "LIG Square", 22.7340, 75.8880),
    ("N_VIJAY", "Vijay Nagar", 22.7533, 75.8937),
    ("N_MEGHDOOT", "Scheme 54 / Meghdoot", 22.7610, 75.8930),
    ("N_MR10", "MR-10 Junction", 22.7650, 75.8720),
    ("N_RADISSON", "Radisson Square", 22.7470, 75.9040),
    ("N_KHAJRANA", "Khajrana Square", 22.7380, 75.9090),
    ("N_BENGALI", "Bengali Square", 22.7240, 75.9090),
    ("N_MUSAKHEDI", "Musakhedi", 22.7000, 75.8990),
]

# road id, source, target, name, speed_kmh
ROADS: list[tuple[str, str, str, str, float]] = [
    ("R01", "N_RAJWADA", "N_BADA_GANPATI", "Jawahar Marg (West)", 22),
    ("R02", "N_RAJWADA", "N_REGAL", "MG Road (Old City)", 22),
    ("R03", "N_RAJWADA", "N_MHOW_NAKA", "Mhow Naka Road", 25),
    ("R04", "N_BADA_GANPATI", "N_AIRPORT", "Airport Road", 40),
    ("R05", "N_BADA_GANPATI", "N_MHOW_NAKA", "Kalani Nagar Link", 30),
    ("R06", "N_MHOW_NAKA", "N_ANNAPURNA", "Annapurna Road", 32),
    ("R07", "N_ANNAPURNA", "N_BHAWARKUAN", "Rajendra Nagar Link", 35),
    ("R08", "N_REGAL", "N_MALWA_MILL", "Patnipura Road", 28),
    ("R09", "N_REGAL", "N_PALASIA", "MG Road", 30),
    ("R10", "N_REGAL", "N_CHHAVNI", "Chhavni Road", 28),
    ("R11", "N_MALWA_MILL", "N_PARDESHIPURA", "Pardeshipura Road", 30),
    ("R12", "N_PARDESHIPURA", "N_LIG", "Industrial Area Road", 32),
    ("R13", "N_PARDESHIPURA", "N_MR10", "MR-10 South", 45),
    ("R14", "N_PALASIA", "N_LIG", "AB Road (Palasia-LIG)", 38),
    ("R15", "N_PALASIA", "N_GEETA_BHAWAN", "AB Road (Geeta Bhawan)", 35),
    ("R16", "N_GEETA_BHAWAN", "N_NAVLAKHA", "AB Road (Navlakha)", 38),
    ("R17", "N_GEETA_BHAWAN", "N_CHHAVNI", "Jail Road", 28),
    ("R18", "N_CHHAVNI", "N_NAVLAKHA", "Sapna Sangeeta Road", 30),
    ("R19", "N_NAVLAKHA", "N_BHAWARKUAN", "Bhawarkuan Road", 35),
    ("R20", "N_NAVLAKHA", "N_MUSAKHEDI", "Agra-Bombay Link", 35),
    ("R21", "N_BHAWARKUAN", "N_MUSAKHEDI", "Ring Road (South)", 50),
    ("R22", "N_MUSAKHEDI", "N_BENGALI", "Ring Road (East)", 50),
    ("R23", "N_BENGALI", "N_KHAJRANA", "Ring Road (Khajrana)", 50),
    ("R24", "N_KHAJRANA", "N_RADISSON", "Ring Road (Radisson)", 50),
    ("R25", "N_RADISSON", "N_VIJAY", "AB Road (Vijay Nagar East)", 40),
    ("R26", "N_LIG", "N_VIJAY", "AB Road (LIG-Vijay Nagar)", 40),
    ("R27", "N_VIJAY", "N_MEGHDOOT", "Scheme 54 Road", 35),
    ("R28", "N_MEGHDOOT", "N_MR10", "MR-10 North", 45),
    ("R29", "N_MEGHDOOT", "N_RADISSON", "Meghdoot Link", 35),
    ("R30", "N_PALASIA", "N_BENGALI", "Old Palasia - Bengali Road", 30),
    ("R31", "N_LIG", "N_KHAJRANA", "Khajrana Road", 32),
    ("R32", "N_BADA_GANPATI", "N_MALWA_MILL", "Jawahar Marg (North)", 25),
]

# code, name, lat, lon, specializations, (er_total, er_occupied, icu_total, icu_occupied)
HOSPITALS: list[tuple[str, str, float, float, list[str], tuple[int, int, int, int]]] = [
    ("HOSP-A", "Hospital A - City General", 22.7140, 75.8800, ["trauma", "general", "burns"], (60, 49, 16, 13)),
    ("HOSP-B", "Hospital B - Vijay Nagar Multispecialty", 22.7515, 75.9010, ["trauma", "cardiac", "burns", "pediatric"], (58, 27, 18, 8)),
    ("HOSP-C", "Hospital C - Bhawarkuan Medical", 22.6950, 75.8700, ["general", "orthopedic"], (40, 22, 8, 5)),
    ("HOSP-D", "Hospital D - Ring Road Trauma Centre", 22.7310, 75.9060, ["trauma", "neuro", "orthopedic"], (45, 30, 12, 9)),
    ("HOSP-E", "Hospital E - Western Civil Hospital", 22.7215, 75.8460, ["general", "pediatric", "toxicology"], (50, 30, 10, 4)),
]

# station id, name, lat, lon, kind
STATIONS: list[tuple[str, str, float, float, str]] = [
    ("S_FIRE_CENTRAL", "Fire Station Central", 22.7215, 75.8640, "FIRE_TRUCK"),
    ("S_FIRE_EAST", "Fire Station East", 22.7470, 75.8985, "FIRE_TRUCK"),
    ("S_FIRE_SOUTH", "Fire Station South", 22.6975, 75.8620, "FIRE_TRUCK"),
    ("S_POLICE_HQ", "Police Control Room", 22.7228, 75.8795, "POLICE"),
    ("S_POLICE_WEST", "Police Station West", 22.7160, 75.8515, "POLICE"),
    ("S_POLICE_NORTH", "Police Station North", 22.7625, 75.8770, "POLICE"),
    ("S_EMS_CENTRAL", "EMS Depot Central", 22.7150, 75.8760, "AMBULANCE"),
    ("S_EMS_NORTH", "EMS Depot North", 22.7565, 75.8895, "AMBULANCE"),
    ("S_EMS_WEST", "EMS Depot West", 22.7100, 75.8455, "AMBULANCE"),
    ("S_EMS_SOUTH", "EMS Depot South", 22.6945, 75.8755, "AMBULANCE"),
    ("S_RESCUE", "SDRF Rescue Base", 22.7345, 75.8615, "RESCUE"),
]

# How many units of each kind at each station
FLEET: dict[str, int] = {
    "S_FIRE_CENTRAL": 4, "S_FIRE_EAST": 3, "S_FIRE_SOUTH": 3,
    "S_POLICE_HQ": 6, "S_POLICE_WEST": 4, "S_POLICE_NORTH": 4,
    "S_EMS_CENTRAL": 6, "S_EMS_NORTH": 5, "S_EMS_WEST": 5, "S_EMS_SOUTH": 4,
    "S_RESCUE": 4,
}

CODE_PREFIX = {"AMBULANCE": "A", "FIRE_TRUCK": "F", "POLICE": "P", "RESCUE": "R"}
EQUIPMENT = {
    "AMBULANCE": ["defibrillator", "oxygen", "stretcher", "trauma kit"],
    "FIRE_TRUCK": ["water tank 4000L", "aerial ladder", "breathing apparatus", "foam"],
    "POLICE": ["radio", "barricades", "first aid"],
    "RESCUE": ["hydraulic cutter", "boat", "ropes", "thermal camera"],
}
CAPACITY = {"AMBULANCE": 2, "FIRE_TRUCK": 6, "POLICE": 4, "RESCUE": 8}

# Location gazetteer used by the compiler's semantic analyzer to resolve names.
# key (normalized upper snake) -> (display name, lat, lon, location_type)
GAZETTEER: dict[str, tuple[str, float, float, str]] = {
    "SCHOOL_A": ("School A (Vijay Nagar)", 22.7508, 75.8962, "SCHOOL"),
    "SCHOOL_B": ("School B (Palasia)", 22.7262, 75.8858, "SCHOOL"),
    "SCHOOL_ZONE_12": ("School Zone 12", 22.7508, 75.8962, "SCHOOL"),
    "VIJAY_NAGAR": ("Vijay Nagar", 22.7533, 75.8937, "COMMERCIAL"),
    "RAJWADA": ("Rajwada", 22.7187, 75.8553, "HERITAGE_MARKET"),
    "PALASIA": ("Palasia", 22.7244, 75.8839, "COMMERCIAL"),
    "BHAWARKUAN": ("Bhawarkuan", 22.6926, 75.8672, "RESIDENTIAL"),
    "BADA_GANPATI": ("Bada Ganpati", 22.7245, 75.8417, "RESIDENTIAL"),
    "MHOW_NAKA": ("Mhow Naka", 22.7050, 75.8480, "RESIDENTIAL"),
    "ANNAPURNA": ("Annapurna", 22.6955, 75.8425, "RESIDENTIAL"),
    "REGAL_SQUARE": ("Regal Square", 22.7196, 75.8700, "COMMERCIAL"),
    "RAILWAY_STATION": ("Indore Railway Station", 22.7174, 75.8688, "TRANSIT"),
    "MALWA_MILL": ("Malwa Mill", 22.7280, 75.8650, "INDUSTRIAL"),
    "PARDESHIPURA": ("Pardeshipura", 22.7390, 75.8710, "INDUSTRIAL"),
    "GEETA_BHAWAN": ("Geeta Bhawan", 22.7186, 75.8847, "COMMERCIAL"),
    "CHHAVNI": ("Chhavni", 22.7090, 75.8740, "RESIDENTIAL"),
    "NAVLAKHA": ("Navlakha", 22.7010, 75.8830, "RESIDENTIAL"),
    "LIG_SQUARE": ("LIG Square", 22.7340, 75.8880, "RESIDENTIAL"),
    "SCHEME_54": ("Scheme 54", 22.7610, 75.8930, "RESIDENTIAL"),
    "MEGHDOOT": ("Meghdoot Garden", 22.7610, 75.8930, "PUBLIC_SPACE"),
    "MR_10": ("MR-10", 22.7650, 75.8720, "HIGHWAY"),
    "RADISSON_SQUARE": ("Radisson Square", 22.7470, 75.9040, "COMMERCIAL"),
    "KHAJRANA": ("Khajrana", 22.7380, 75.9090, "RESIDENTIAL"),
    "BENGALI_SQUARE": ("Bengali Square", 22.7240, 75.9090, "RESIDENTIAL"),
    "MUSAKHEDI": ("Musakhedi", 22.7000, 75.8990, "RESIDENTIAL"),
    "AIRPORT": ("Devi Ahilya Bai Holkar Airport", 22.7216, 75.8011, "TRANSIT"),
    "RING_ROAD": ("Ring Road", 22.7240, 75.9090, "HIGHWAY"),
    "AB_ROAD": ("AB Road", 22.7340, 75.8880, "HIGHWAY"),
    "SARAFA_BAZAAR": ("Sarafa Bazaar", 22.7178, 75.8545, "HERITAGE_MARKET"),
    "CHEMICAL_PLANT": ("Pologround Chemical Unit", 22.7415, 75.8660, "INDUSTRIAL"),
    "INDORE": ("Indore (city centre)", 22.7196, 75.8577, "CITY"),
}

# alias -> gazetteer key (lower-case multiword phrases recognised by the lexer)
LOCATION_ALIASES: dict[str, str] = {
    "school a": "SCHOOL_A", "school b": "SCHOOL_B", "school zone 12": "SCHOOL_ZONE_12",
    "vijay nagar": "VIJAY_NAGAR", "vijaynagar": "VIJAY_NAGAR", "rajwada": "RAJWADA",
    "palasia": "PALASIA", "bhawarkuan": "BHAWARKUAN", "bada ganpati": "BADA_GANPATI",
    "mhow naka": "MHOW_NAKA", "annapurna": "ANNAPURNA", "regal square": "REGAL_SQUARE",
    "regal": "REGAL_SQUARE", "railway station": "RAILWAY_STATION", "malwa mill": "MALWA_MILL",
    "pardeshipura": "PARDESHIPURA", "geeta bhawan": "GEETA_BHAWAN", "chhavni": "CHHAVNI",
    "navlakha": "NAVLAKHA", "lig square": "LIG_SQUARE", "lig": "LIG_SQUARE",
    "scheme 54": "SCHEME_54", "meghdoot": "MEGHDOOT", "mr-10": "MR_10", "mr 10": "MR_10",
    "mr10": "MR_10", "radisson square": "RADISSON_SQUARE", "radisson": "RADISSON_SQUARE",
    "khajrana": "KHAJRANA", "bengali square": "BENGALI_SQUARE", "musakhedi": "MUSAKHEDI",
    "airport": "AIRPORT", "ring road": "RING_ROAD", "ab road": "AB_ROAD",
    "sarafa bazaar": "SARAFA_BAZAAR", "sarafa": "SARAFA_BAZAAR",
    "chemical plant": "CHEMICAL_PLANT", "indore": "INDORE",
}

HOSPITAL_ALIASES: dict[str, str] = {
    "hospital a": "HOSP-A", "hospital b": "HOSP-B", "hospital c": "HOSP-C",
    "hospital d": "HOSP-D", "hospital e": "HOSP-E",
}
