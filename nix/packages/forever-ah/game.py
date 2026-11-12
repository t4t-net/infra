"""static game knowledge th model leans on: professions, wat counts as gathered, vendor-sold mats, races."""

PROFESSIONS = {164: "blacksmithing", 202: "engineering", 197: "tailoring", 165: "leatherworking",
               171: "alchemy", 333: "enchanting", 185: "cooking", 186: "mining"}


# raw mats th site lists 4 gathering, which have no recipes of their own
GATHERED = {
    "mining": [2770, 2840, 2835, 774, 818, 1210, 2771, 3576, 2836, 1206, 1705, 2775, 2842, 2772, 3575, 3859, 2838,
               2776, 3577, 3858, 3860, 7912, 7911, 6037, 10620, 12359, 12365, 11370],
    "herbalism": [2447, 765, 2449, 785, 2450, 2453, 2452, 3355, 3369, 3356, 3357, 3818, 3821, 3358, 3819, 4625,
                  8831, 8836, 8838, 8839, 8845, 8846, 13464, 13463, 13465, 13466, 13467, 13468],
    "skinning": [2934, 2318, 783, 2319, 4232, 4234, 4235, 4304, 8169, 8170, 8171, 4461, 5784, 7286, 8154, 8165],
    "cloth": [2589, 2592, 4306, 4338, 14047, 14256],
}


# reagents trade-supply vendors actually sell; blizz sets purchase_price on everything, so it cant tell us
VENDOR_MATS = {"Weak Flux", "Strong Flux", "Coal", "Fine Thread", "Coarse Thread", "Silken Thread", "Heavy Silken Thread",
               "Rune Thread", "Flask of Oil", "Empty Vial", "Leaded Vial", "Crystal Vial", "Imbued Vial", "Salt",
               "Mild Spices", "Hot Spices", "Refreshing Spring Water", "Ice Cold Milk", "Simple Flour", "Gray Dye",
               "Blue Dye", "Red Dye", "Bleach", "Pink Dye", "Black Dye", "Green Dye", "Purple Dye", "Orange Dye",
               "Yellow Dye", "Simple Wood"}


ALLIANCE_RACES, HORDE_RACES =1 | 4 | 8 | 64, 2 | 16 | 32 | 128  # human dwarf nelf gnome / orc undead tauren troll


# forever's listing lengths nd th deposit each charges, as a % of th vendor sell price per unit, floored at
# 1s per listing. matched 228/228 deposits th addon read (2026-11-11). NOT classic's 12/24/48h
AUCTION_DURATIONS = ((2, 5), (8, 20), (24, 60))  # (hours, % of vendor price)


def deposit(sell_price, quantity, percent):
    """copper it costs 2 list `quantity` of an item tht vendors 4 `sell_price`, at one of AUCTION_DURATIONS"""
    return max(100, sell_price * quantity * percent // 100)
