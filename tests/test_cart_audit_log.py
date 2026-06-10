from backend.app.cart import CartService
from backend.app.models import Product


class TestCartAuditLog:
    def test_add_logs_action(self):
        product = Product(
            product_id="p1",
            title="Test Product",
            brand="BrandA",
            category="cat",
            sub_category="sub",
            price=100.0,
            image_path="img.jpg",
        )
        cart = CartService([product])
        cart.add("s1", "p1", 2)

        log = cart.get_audit_log("s1")
        assert len(log) == 1
        assert log[0]["action"] == "add"
        assert log[0]["product_id"] == "p1"
        assert log[0]["quantity"] == 2
        assert "timestamp" in log[0]

    def test_update_quantity_logs_action(self):
        product = Product(
            product_id="p1",
            title="Test Product",
            brand="BrandA",
            category="cat",
            sub_category="sub",
            price=100.0,
            image_path="img.jpg",
        )
        cart = CartService([product])
        cart.add("s1", "p1", 1)
        cart.update_quantity("s1", "p1", 5)

        log = cart.get_audit_log("s1")
        assert len(log) == 2
        assert log[1]["action"] == "update"
        assert log[1]["quantity"] == 5

    def test_update_quantity_zero_logs_remove(self):
        product = Product(
            product_id="p1",
            title="Test Product",
            brand="BrandA",
            category="cat",
            sub_category="sub",
            price=100.0,
            image_path="img.jpg",
        )
        cart = CartService([product])
        cart.add("s1", "p1", 1)
        cart.update_quantity("s1", "p1", 0)

        log = cart.get_audit_log("s1")
        assert len(log) == 2
        assert log[1]["action"] == "remove"

    def test_remove_logs_action(self):
        product = Product(
            product_id="p1",
            title="Test Product",
            brand="BrandA",
            category="cat",
            sub_category="sub",
            price=100.0,
            image_path="img.jpg",
        )
        cart = CartService([product])
        cart.add("s1", "p1", 1)
        cart.remove("s1", "p1")

        log = cart.get_audit_log("s1")
        assert len(log) == 2
        assert log[1]["action"] == "remove"
        assert log[1]["product_id"] == "p1"

    def test_checkout_logs_action(self):
        product = Product(
            product_id="p1",
            title="Test Product",
            brand="BrandA",
            category="cat",
            sub_category="sub",
            price=100.0,
            image_path="img.jpg",
        )
        cart = CartService([product])
        cart.add("s1", "p1", 1)
        cart.checkout("s1")

        log = cart.get_audit_log("s1")
        assert len(log) >= 2
        assert any(entry["action"] == "checkout" for entry in log)

    def test_clear_logs_action(self):
        product = Product(
            product_id="p1",
            title="Test Product",
            brand="BrandA",
            category="cat",
            sub_category="sub",
            price=100.0,
            image_path="img.jpg",
        )
        cart = CartService([product])
        cart.add("s1", "p1", 1)
        cart.clear("s1")

        log = cart.get_audit_log("s1")
        assert any(entry["action"] == "clear" for entry in log)

    def test_audit_log_keeps_last_100_entries(self):
        product = Product(
            product_id="p1",
            title="Test Product",
            brand="BrandA",
            category="cat",
            sub_category="sub",
            price=100.0,
            image_path="img.jpg",
        )
        cart = CartService([product])
        for i in range(105):
            cart.add("s1", "p1", 1)

        log = cart.get_audit_log("s1")
        assert len(log) == 100

    def test_audit_log_isolated_per_session(self):
        product = Product(
            product_id="p1",
            title="Test Product",
            brand="BrandA",
            category="cat",
            sub_category="sub",
            price=100.0,
            image_path="img.jpg",
        )
        cart = CartService([product])
        cart.add("s1", "p1", 1)
        cart.add("s2", "p1", 2)

        assert len(cart.get_audit_log("s1")) == 1
        assert len(cart.get_audit_log("s2")) == 1
        assert cart.get_audit_log("s1")[0]["quantity"] == 1
        assert cart.get_audit_log("s2")[0]["quantity"] == 2
