

def _build_recommended_actions(places: list[dict]) -> list[dict[str, object]]:
    """Build nearby-search quick actions from categories found near the visitor."""
    actions: list[dict[str, object]] = [
        {
            "icon": "fa-compass",
            "label": {
                "vi": "Top 5 địa điểm gần tôi",
                "en": "Top 5 places near me",
            },
            "question": {
                "vi": "Cho tôi xem top 5 địa điểm gần tôi.",
                "en": "Show me the top 5 places near me.",
            },
        }
    ]
    categories: list[str] = []
    for place in places:
        category = place.get("category")
        if isinstance(category, str):
            category = " ".join(category.split())
            if category and category.casefold() not in {
                existing.casefold() for existing in categories
            }:
                categories.append(category)

    if not categories:
        categories = ["coffee shop", "church"]

    for category in categories:
        normalized = category.casefold()
        if "coffee" in normalized or "cafe" in normalized or "café" in normalized:
            category_vi, category_en, icon = "quán cà phê", "cafes", "fa-coffee"
        elif "church" in normalized or "nhà thờ" in normalized:
            category_vi, category_en, icon = "nhà thờ", "churches", "fa-map-marker"
        elif "restaurant" in normalized or "nhà hàng" in normalized:
            category_vi, category_en, icon = "nhà hàng", "restaurants", "fa-cutlery"
        elif "park" in normalized or "công viên" in normalized:
            category_vi, category_en, icon = "công viên", "parks", "fa-tree"
        else:
            category_vi = category_en = category
            icon = "fa-map-marker"

        actions.append(
            {
                "icon": icon,
                "label": {
                    "vi": f"Top 5 {category_vi} gần tôi",
                    "en": f"Top 5 {category_en} near me",
                },
                "question": {
                    "vi": f"Cho tôi xem top 5 {category_vi} gần tôi.",
                    "en": f"Show me the top 5 {category_en} near me.",
                },
            }
        )
        if len(actions) == 5:
            break
    return actions