def test_browse_search_filter_and_detail(client):
    categories = client.get("/categories")
    assert categories.status_code == 200
    assert any(row["slug"] == "kitchen" for row in categories.json())

    page = client.get("/products", params={"q": "linen", "category": "home", "in_stock": True})
    assert page.status_code == 200
    names = [item["name"] for item in page.json()["items"]]
    assert "Linen Duvet Cover" in names
    assert "Linen Apron" not in names

    sold_out = client.get("/products", params={"in_stock": False})
    assert any(item["slug"] == "brass-desk-lamp" for item in sold_out.json()["items"])

    detail = client.get("/products/stoneware-mug")
    assert detail.status_code == 200
    assert detail.json()["price_cents"] == 1800
    assert client.get("/products/missing").status_code == 404
