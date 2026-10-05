import pytest
from playwright.sync_api import Page, expect

BASE_URL = "https://www.saucedemo.com"

# Marks every test in this file as "regression"
pytestmark = pytest.mark.regression


def login(page: Page, username: str, password: str):
    page.goto(BASE_URL)
    page.fill("#user-name", username)
    page.fill("#password", password)
    page.click("#login-button")


@pytest.fixture
def logged_in_page(page: Page) -> Page:
    login(page, "standard_user", "secret_sauce")
    return page


def test_login_page_loads(page: Page):
    page.goto(BASE_URL)
    expect(page.locator("#login-button")).to_be_visible()


def test_valid_login(page: Page):
    login(page, "standard_user", "secret_sauce")
    expect(page).to_have_url(f"{BASE_URL}/inventory.html")


def test_invalid_password_shows_error(page: Page):
    login(page, "standard_user", "wrong_password")
    expect(page.locator("[data-test='error']")).to_contain_text("do not match")


def test_locked_out_user_shows_error(page: Page):
    login(page, "locked_out_user", "secret_sauce")
    expect(page.locator("[data-test='error']")).to_contain_text("locked out")


def test_empty_username_shows_error(page: Page):
    page.goto(BASE_URL)
    page.click("#login-button")
    expect(page.locator("[data-test='error']")).to_contain_text("Username is required")


def test_products_are_listed(logged_in_page: Page):
    expect(logged_in_page.locator(".inventory_item")).to_have_count(6)


def test_add_item_to_cart(logged_in_page: Page):
    logged_in_page.click("#add-to-cart-sauce-labs-backpack")
    expect(logged_in_page.locator(".shopping_cart_badge")).to_have_text("1")


def test_remove_item_from_cart(logged_in_page: Page):
    logged_in_page.click("#add-to-cart-sauce-labs-backpack")
    logged_in_page.click("#remove-sauce-labs-backpack")
    expect(logged_in_page.locator(".shopping_cart_badge")).to_have_count(0)


def test_logout(logged_in_page: Page):
    logged_in_page.click("#react-burger-menu-btn")
    logged_in_page.click("#logout_sidebar_link")
    expect(logged_in_page).to_have_url(f"{BASE_URL}/")
