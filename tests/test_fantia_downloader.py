import tempfile
import unittest
from pathlib import Path

from bs4 import BeautifulSoup

from fantia_downloader import FantiaDownloader


def product_html(product_id, price, price_text="DL商品", owned=False):
    action = "download" if owned else "add_to_cart"
    return f"""
    <html><head>
      <script type="application/ld+json">
        {{"@type":"Product","name":"Example","image":"https://example.test/thumb.jpg",
          "offers":{{"@type":"Offer","price":{price},"priceCurrency":"JPY"}}}}
      </script>
    </head><body><main>
      <div class="product-price">{price_text} {price}円</div>
      <a href="/products/{product_id}/{action}">action</a>
    </main></body></html>
    """


class ProductSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.downloader = FantiaDownloader("test-session", Path(self.temp_dir.name), 0)

    def tearDown(self):
        self.temp_dir.cleanup()

    def parse(self, html, product_id="123"):
        return self.downloader.product_info_from_soup(
            product_id, BeautifulSoup(html, "html.parser")
        )

    def test_exact_zero_download_product_is_eligible(self):
        info = self.parse(product_html("123", 0))
        self.assertTrue(info["is_free"])
        self.assertTrue(info["is_download"])
        self.assertFalse(info["owned"])

    def test_paid_product_is_never_treated_as_free(self):
        info = self.parse(product_html("123", 1800, "DL商品 プラン加入で0円〜"))
        self.assertFalse(info["is_free"])
        self.assertEqual(info["price"], 1800)

    def test_owned_zero_yen_product_uses_download_endpoint(self):
        info = self.parse(product_html("123", 0, owned=True))
        self.assertTrue(info["owned"])
        self.assertEqual(info["download_url"], "https://fantia.jp/products/123/download")

    def test_nonempty_cart_prevents_automatic_order(self):
        self.downloader.cart = lambda: (BeautifulSoup("<html></html>", "html.parser"), ["999"])
        info = self.parse(product_html("123", 0))
        self.assertFalse(self.downloader.claim_free_product(info))

    def test_zero_yen_checkout_submits_only_target_product(self):
        class Response:
            def __init__(self, text="", url="https://fantia.jp/test"):
                self.text, self.url = text, url

            def raise_for_status(self):
                return None

        cart_states = iter([
            (BeautifulSoup("<html></html>", "html.parser"), []),
            (BeautifulSoup("<main>合計(1点) 0円</main>", "html.parser"), ["123"]),
        ])
        checkout = """
        <form action="/mypage/cart/purchase" method="post">
          <input name="authenticity_token" value="csrf">
          <input name="cart[purchase][1][product_id]" value="123">
          <input name="cart[purchase][1][product_lock_version]" value="1">
          <input name="cart[purchase][1][quantity]" value="1">
          <input name="agree_to_terms_of_service" type="checkbox" value="true">
          <input name="use_coin" value="0">
        </form>
        """
        posts = []
        self.downloader.cart = lambda: next(cart_states)
        self.downloader.get = lambda *args, **kwargs: Response(checkout)
        self.downloader.s.post = lambda url, **kwargs: posts.append((url, kwargs)) or Response()
        owned = self.parse(product_html("123", 0, owned=True))
        self.downloader.product_info = lambda product_id: owned

        result = self.downloader.claim_free_product(self.parse(product_html("123", 0)))

        self.assertTrue(result["owned"])
        self.assertEqual(posts[-1][0], "https://fantia.jp/mypage/cart/purchase")
        self.assertEqual(posts[-1][1]["data"]["cart[purchase][1][product_id]"], "123")
        self.assertEqual(posts[-1][1]["data"]["agree_to_terms_of_service"], "true")


class MediaGroupingTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.downloader = FantiaDownloader("test-session", Path(self.temp_dir.name), 0)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_api_content_without_title_has_no_generated_folder_name(self):
        data = {
            "post": {
                "post_contents": [{
                    "title": "",
                    "post_content_photos": [{
                        "id": 123,
                        "url": {"original": "https://example.test/post_content/file/123/photo.jpg"},
                    }],
                }]
            }
        }

        groups = self.downloader.media_groups(data, BeautifulSoup("<html></html>", "html.parser"))

        self.assertEqual(groups[0][0], "")

    def test_html_content_without_title_has_no_generated_folder_name(self):
        html = """
        <div class="post-content-inner">
          <div class="post-content-body">
            <img src="https://example.test/post_content/file/456/photo.jpg">
          </div>
        </div>
        """

        groups = self.downloader.media_groups({}, BeautifulSoup(html, "html.parser"))

        self.assertEqual(groups[0][0], "")

    def test_titled_content_keeps_its_folder_name(self):
        data = {
            "post": {
                "post_contents": [{
                    "title": "Plan A",
                    "download_uri": "/download/example.zip",
                }]
            }
        }

        groups = self.downloader.media_groups(data, BeautifulSoup("<html></html>", "html.parser"))

        self.assertEqual(groups[0][0], "Plan A")


if __name__ == "__main__":
    unittest.main()
