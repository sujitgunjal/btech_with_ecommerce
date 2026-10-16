"""Catalogue and customer seed data."""

CATEGORIES = [
    ("kitchen", "Kitchen", "Tools and tableware for slow cooking."),
    ("home", "Home", "Textiles and objects for the rooms you live in."),
    ("outdoors", "Outdoors", "Pieces that travel well."),
    ("electronics", "Electronics", "Small devices with a quiet presence."),
    ("stationery", "Stationery", "Paper goods for desks and gifts."),
    ("pantry", "Pantry", "Ingredients worth keeping in reach."),
]

# sku, slug, name, category, price_cents, stock, description
PRODUCTS = [
    ("KETTLE-01", "ceramic-pour-over-kettle", "Ceramic Pour-Over Kettle", "kitchen", 4899, 24, "A matte kettle with a narrow spout for a steady pour."),
    ("APRON-02", "linen-apron", "Linen Apron", "kitchen", 3800, 40, "Washed linen apron with a crossed back and deep pocket."),
    ("BOARD-03", "oak-cutting-board", "Oak Cutting Board", "kitchen", 6400, 18, "End-grain oak board finished with food-safe oil."),
    ("MUG-04", "stoneware-mug", "Stoneware Mug", "kitchen", 1800, 60, "A speckled mug that keeps tea hot a little longer."),
    ("THROW-05", "wool-throw", "Wool Throw", "home", 8900, 15, "Heavy wool throw in a warm undyed tone."),
    ("LAMP-06", "brass-desk-lamp", "Brass Desk Lamp", "home", 12400, 0, "An adjustable brass lamp. This finish is currently sold out."),
    ("DUVET-07", "linen-duvet-cover", "Linen Duvet Cover", "home", 15800, 12, "Stonewashed linen duvet cover with coconut-shell buttons."),
    ("VASE-08", "ceramic-table-vase", "Ceramic Table Vase", "home", 3200, 22, "A low vase for branches or a single stem."),
    ("BOTTLE-09", "trail-bottle", "Trail Bottle", "outdoors", 2600, 50, "Insulated bottle that fits a side pocket."),
    ("WEEK-10", "canvas-weekender", "Canvas Weekender", "outdoors", 14200, 9, "Waxed canvas weekender with a leather handle."),
    ("BEANIE-11", "merino-beanie", "Merino Beanie", "outdoors", 2800, 35, "Fine merino beanie that packs flat."),
    ("STOOL-12", "camp-stool", "Folding Camp Stool", "outdoors", 5400, 16, "Ash legs and a canvas seat that folds flat."),
    ("SPEAKER-13", "pocket-speaker", "Pocket Speaker", "electronics", 7600, 20, "A small speaker with a warm, low volume ceiling."),
    ("CLOCK-14", "analog-alarm-clock", "Analog Alarm Clock", "electronics", 4200, 28, "A quiet analog clock with a soft alarm."),
    ("BUDS-15", "studio-earbuds", "Studio Earbuds", "electronics", 9900, 14, "Wired earbuds with a short, tangle-resistant cable."),
    ("NOTE-16", "linen-notebook", "Linen Notebook", "stationery", 1400, 80, "Plain pages in a linen-covered notebook."),
    ("PEN-17", "fountain-pen", "Fountain Pen", "stationery", 3600, 25, "A brass fountain pen with a medium nib."),
    ("WRAP-18", "kraft-gift-wrap", "Kraft Gift Wrap", "stationery", 900, 100, "A set of kraft sheets and cotton tape."),
    ("COFFEE-19", "single-origin-coffee", "Single-Origin Coffee", "pantry", 2200, 45, "Whole beans roasted for filter brewing."),
    ("OIL-20", "olive-oil-tin", "Olive Oil Tin", "pantry", 2800, 30, "Early-harvest olive oil in a resealable tin."),
    ("HONEY-21", "honey-jar", "Wildflower Honey", "pantry", 1600, 36, "A jar of unfiltered wildflower honey."),
    ("TOTE-22", "studio-tote", "Studio Tote", "home", 2400, 250, "A heavy canvas tote used by the load test and by customers."),
]
