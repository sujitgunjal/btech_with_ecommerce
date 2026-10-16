"""Create the static product illustrations used by the storefront."""

from pathlib import Path

from shop_api.catalogue_data import PRODUCTS

OUT = Path(__file__).resolve().parents[2] / "frontend" / "public" / "products"
COLORS = {
    "kitchen": "#c4552a",
    "home": "#1f4d40",
    "outdoors": "#3d6b4f",
    "electronics": "#355c7d",
    "stationery": "#8c5a3c",
    "pantry": "#c4892a",
}


def svg(slug: str, category: str, index: int) -> str:
    color = COLORS[category]
    shape = index % 3
    if shape == 0:
        motif = f'<circle cx="400" cy="340" r="150" fill="{color}"/>'
    elif shape == 1:
        motif = f'<rect x="250" y="190" width="300" height="300" rx="36" fill="{color}"/>'
    else:
        motif = f'<polygon points="400,170 560,470 240,470" fill="{color}"/>'
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 800" role="img">
  <rect width="800" height="800" fill="#f6f1e8"/>
  {motif}
  <rect x="220" y="560" width="360" height="18" rx="9" fill="#231c16" opacity="0.18"/>
  <text x="400" y="640" text-anchor="middle" font-family="Georgia, serif" font-size="42" fill="#231c16">{slug.replace("-", " ")}</text>
</svg>
'''


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for index, product in enumerate(PRODUCTS):
        slug = product[1]
        category = product[3]
        (OUT / f"{slug}.svg").write_text(svg(slug, category, index), encoding="utf-8")


if __name__ == "__main__":
    main()
