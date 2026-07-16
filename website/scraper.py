from playwright.sync_api import sync_playwright
import re


def clean_price(price_text):
    """
    Convert:
        ₹2,499
        ₹2,499.00

    Into:
        2499.0
    """

    if not price_text:
        return None

    price_text = (
        price_text
        .replace("₹", "")
        .replace(",", "")
        .strip()
    )

    match = re.search(r"\d+(\.\d+)?", price_text)

    if match:
        return float(match.group())

    return None


def get_product_details(url):
    """
    Returns

    {
        "title": "...",
        "price": 2499.0,
        "image": "...",
        "rating": "...",
        "availability": "..."
    }
    """

    product = {
        "title": None,
        "price": None,
        "image": None,
        "rating": None,
        "availability": None
    }

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--single-process"
            ]
        )

        context = browser.new_context(
            viewport={
                "width": 1366,
                "height": 768
            },
            locale="en-IN",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/137.0.0.0 Safari/537.36"
            )
        )

        page = context.new_page()

        page.goto(
            url,
            timeout=60000
        )
        

        page.wait_for_timeout(1000)

        # ----------------------------------
        # TITLE
        # ----------------------------------

        title_selectors = [
            "#productTitle",
            "#title"
        ]

        for selector in title_selectors:

            try:

                title = page.locator(selector).first.text_content()

                if title:
                    product["title"] = title.strip()
                    break

            except:
                pass

        # ----------------------------------
        # PRICE
        # ----------------------------------

        price_selectors = [

            ".a-price .a-offscreen",

            ".a-price-whole",

            "#corePrice_feature_div .a-offscreen",

            ".priceToPay .a-offscreen"

        ]

        for selector in price_selectors:

            try:

                text = page.locator(selector).first.text_content()

                price = clean_price(text)

                if price:

                    product["price"] = price

                    break

            except:
                pass

        # ----------------------------------
        # IMAGE
        # ----------------------------------

        image_selectors = [

            "#landingImage",

            "#imgBlkFront",

            "#main-image",

            "#ebooksImgBlkFront"

        ]

        for selector in image_selectors:

            try:

                image = page.locator(selector).first.get_attribute("src")

                if image:

                    product["image"] = image

                    break

            except:
                pass

        # ----------------------------------
        # RATING
        # ----------------------------------

        try:

            rating = page.locator("span.a-icon-alt").first.text_content()

            if rating:

                product["rating"] = rating.strip()

        except:
            pass

        # ----------------------------------
        # AVAILABILITY
        # ----------------------------------

        availability_selectors = [

            "#availability",

            "#availabilityInsideBuyBox_feature_div"

        ]

        for selector in availability_selectors:

            try:

                availability = page.locator(selector).text_content()

                if availability:

                    product["availability"] = availability.strip()

                    break

            except:
                pass

        browser.close()

    return product


# -------------------------------------------------
# Helper Functions
# -------------------------------------------------

def get_amazon_price(url):

    data = get_product_details(url)

    return data["price"]


def get_amazon_image(url):

    data = get_product_details(url)

    return data["image"]


def get_amazon_title(url):

    data = get_product_details(url)

    return data["title"]


# -------------------------------------------------
# Test
# -------------------------------------------------

if __name__ == "__main__":

    url = input("Enter Amazon Product URL:\n")

    product = get_product_details(url)

    print("\n========== PRODUCT DETAILS ==========\n")

    print("Title:")
    print(product["title"])

    print()

    print("Price:")
    print(product["price"])

    print()

    print("Image:")
    print(product["image"])

    print()

    print("Rating:")
    print(product["rating"])

    print()

    print("Availability:")
    print(product["availability"])