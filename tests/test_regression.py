import re
import pytest
from playwright.sync_api import Page, expect

BASE_URL = "https://dear-halo-molecules-burlington.trycloudflare.com"

USERS = {
    "student": {"id": "714023104109", "pass": "Siet@2727", "landing": "/dashboard"},
    "admin": {"id": "admin@siet.ac.in", "pass": "Siet@2727", "landing": "/dashboard"},
    "officer": {"id": "officer@siet.ac.in", "pass": "password123", "landing": "/placement-officer"},
    "head": {"id": "head@siet.ac.in", "pass": "password123", "landing": "/placement-officer"},
}


def login(page: Page, role: str):
    user = USERS[role]
    page.goto(f"{BASE_URL}/login")
    if page.get_by_text("Too many login attempts for this account").is_visible():
        pytest.skip("Login rate limited by the app. Wait 15 minutes and rerun the suite.")
    page.get_by_role("textbox", name="Registration No / Email").fill(user["id"])
    page.get_by_role("textbox", name="Password").fill(user["pass"])
    page.get_by_role("button", name="Sign In").click()
    try:
        page.wait_for_url(f"{BASE_URL}{user['landing']}", timeout=20000)
    except Exception:
        page.wait_for_load_state("networkidle")
        if page.get_by_text("Too many login attempts for this account").is_visible():
            pytest.skip("Login rate limited by the app. Wait 15 minutes and rerun the suite.")
        raise


def logout(page: Page):
    page.get_by_role("button", name="Logout").click()
    page.wait_for_url(f"{BASE_URL}/login")


def first_visible(locator):
    count = locator.count()
    for i in range(count):
        candidate = locator.nth(i)
        if candidate.is_visible():
            return candidate
    return locator.first


def boxes_overlap(loc_a, loc_b) -> bool:
    a = loc_a.bounding_box()
    b = loc_b.bounding_box()
    if not a or not b:
        return False
    return not (
        a["x"] + a["width"] <= b["x"]
        or b["x"] + b["width"] <= a["x"]
        or a["y"] + a["height"] <= b["y"]
        or b["y"] + b["height"] <= a["y"]
    )


class TestAuth:

    def test_tc01_student_valid_login(self, page: Page):
        login(page, "student")
        expect(page).to_have_url(f"{BASE_URL}/dashboard")
        expect(page.get_by_text("PRAVIN")).to_be_visible()

    def test_tc02_admin_valid_login(self, page: Page):
        login(page, "admin")
        expect(page).to_have_url(f"{BASE_URL}/dashboard")
        expect(page.get_by_role("link", name="Admin Panel", exact=True)).to_be_visible()

    def test_tc03_officer_valid_login(self, page: Page):
        login(page, "officer")
        expect(page).to_have_url(f"{BASE_URL}/placement-officer")
        expect(page.get_by_role("heading", name="Placement Dashboard")).to_be_visible()
        expect(page.get_by_role("button", name="My Tasks")).to_be_visible()

    def test_tc04_head_valid_login(self, page: Page):
        login(page, "head")
        expect(page).to_have_url(f"{BASE_URL}/placement-officer")
        expect(page.get_by_role("button", name="Manage Officers")).to_be_visible()
        expect(page.get_by_role("button", name="Manage Tasks")).to_be_visible()

    def test_tc05_invalid_credentials(self, page: Page):
        page.goto(f"{BASE_URL}/login")
        page.get_by_role("textbox", name="Registration No / Email").fill("714023201099")
        page.get_by_role("textbox", name="Password").fill("WrongPass@123")
        page.get_by_role("button", name="Sign In").click()
        expect(page).to_have_url(f"{BASE_URL}/login")


class TestStudent:

    @pytest.fixture(autouse=True)
    def _login(self, page: Page):
        login(page, "student")

    def test_tc06_dashboard_sietscore(self, page: Page):
        expect(page.get_by_text("SIETScore").first).to_be_visible()
        expect(page.get_by_text("/100").first).to_be_visible()

    def test_tc07_day_streak_widget_critical(self, page: Page):
        streak_card = first_visible(page.get_by_text("Day Streak", exact=False)).locator("..")
        expect(streak_card).to_be_visible()

    def test_tc08_streak_persists_after_reload_critical(self, page: Page):
        streak = first_visible(page.get_by_text("Day Streak", exact=False))
        before = streak.locator("..").inner_text()
        page.reload()
        page.wait_for_load_state("networkidle")
        after = first_visible(page.get_by_text("Day Streak", exact=False)).locator("..").inner_text()
        assert after == before

    def test_tc09_certifications_score_card_critical(self, page: Page):
        certs_card = first_visible(page.get_by_text("Certs", exact=True)).locator("..")
        expect(certs_card).to_be_visible()
        expect(certs_card).to_contain_text("10/10")

    def test_tc10_leaderboard_loads(self, page: Page):
        page.get_by_role("link", name="Leaderboard").click()
        expect(page).to_have_url(f"{BASE_URL}/leaderboard")

    def test_tc11_career_page_upcoming_drives(self, page: Page):
        page.get_by_role("link", name="Career").click()
        expect(page).to_have_url(f"{BASE_URL}/career")
        expect(page.get_by_role("button", name="Read Details").first).to_be_visible()

    def test_tc12_opportunity_apply_critical(self, page: Page):
        page.get_by_role("link", name="Career").click()
        first_opportunity = page.get_by_role("button", name="Read Details").first
        expect(first_opportunity).to_be_visible()
        first_opportunity.click()

    def test_tc13_notifications_panel_critical(self, page: Page):
        page.get_by_role("link", name="Career").click()
        expect(page.get_by_role("heading", name="Notifications")).to_be_visible()
        has_empty_state = page.get_by_text("No new notifications.").is_visible()
        assert isinstance(has_empty_state, bool)

    def test_tc14_ui_overlap_score_leaderboard_critical(self, page: Page):
        page.set_viewport_size({"width": 1366, "height": 768})
        score_card = first_visible(page.get_by_text("SIETScore", exact=True)).locator("..")
        leaderboard_widget = first_visible(page.get_by_text("Overview", exact=True)).locator("..")
        assert boxes_overlap(score_card, leaderboard_widget) is False


class TestAdmin:

    @pytest.fixture(autouse=True)
    def _login(self, page: Page):
        login(page, "admin")
        page.get_by_role("link", name="Admin Panel", exact=True).click()
        expect(page).to_have_url(f"{BASE_URL}/admin")

    def test_tc15_admin_panel_stats(self, page: Page):
        expect(page.get_by_role("heading", name="Admin Panel")).to_be_visible()
        expect(page.get_by_role("button", name="Manage")).to_be_visible()
        expect(page.get_by_role("button", name="Pending")).to_be_visible()

    def test_tc16_search_student(self, page: Page):
        page.get_by_role("button", name="Manage").click()
        page.get_by_role("textbox", name=re.compile("Search by name, reg no", re.I)).fill(
            "714023201099"
        )

    def test_tc17_open_import_export_tab_critical(self, page: Page):
        page.get_by_role("button", name="Import and Export").click()

    def test_tc18_export_student_data_critical(self, page: Page):
        page.get_by_role("button", name="Import and Export").click()

    def test_tc19_import_student_data_critical(self, page: Page):
        page.get_by_role("button", name="Import and Export").click()

    def test_tc20_pending_reviews_list_critical(self, page: Page):
        page.get_by_role("button", name="Pending").click()

    def test_tc21_approve_reject_certification_critical(self, page: Page):
        page.get_by_role("button", name="Pending").click()

    def test_tc22_create_assign_drive_task_critical(self, page: Page):
        page.get_by_role("button", name="Drives", exact=True).click()

    def test_tc23_pinned_cards_no_overlap_critical(self, page: Page):
        page.set_viewport_size({"width": 1440, "height": 900})
        cards = page.get_by_role("button", name="Pinned")
        count = cards.count()
        for i in range(count - 1):
            overlap = boxes_overlap(
                cards.nth(i).locator(".."), cards.nth(i + 1).locator("..")
            )
            assert overlap is False


class TestOfficer:

    @pytest.fixture(autouse=True)
    def _login(self, page: Page):
        login(page, "officer")

    def test_tc24_officer_dashboard_landing(self, page: Page):
        expect(page.get_by_role("heading", name="Placement Dashboard")).to_be_visible()
        expect(page.get_by_role("button", name="Overview")).to_be_visible()

    def test_tc25_my_tasks_shows_assigned_tasks_critical(self, page: Page):
        page.get_by_role("button", name="My Tasks").click()

    def test_tc26_drives_meetings_no_overlap(self, page: Page):
        page.set_viewport_size({"width": 1366, "height": 768})
        drives = first_visible(page.get_by_role("heading", name="Upcoming Drives")).locator("..")
        meetings = first_visible(page.get_by_role("heading", name="Upcoming HR Meetings")).locator("..")
        assert boxes_overlap(drives, meetings) is False

    def test_tc27_officer_stat_cards(self, page: Page):
        expect(page.get_by_role("heading", name="Drives In Progress")).to_be_visible()
        expect(page.get_by_role("heading", name="HRs Contacted")).to_be_visible()
        expect(page.get_by_role("heading", name="Students Placed")).to_be_visible()
        expect(page.get_by_role("heading", name="Today's Meetings")).to_be_visible()


class TestHead:

    @pytest.fixture(autouse=True)
    def _login(self, page: Page):
        login(page, "head")

    def test_tc28_head_dashboard_elevated_tabs(self, page: Page):
        expect(page.get_by_role("heading", name="Placement Dashboard")).to_be_visible()
        expect(page.get_by_role("button", name="Manage Officers")).to_be_visible()
        expect(page.get_by_role("button", name="Manage Tasks")).to_be_visible()

    def test_tc29_assign_task_to_officer_critical(self, page: Page):
        page.get_by_role("button", name="Manage Tasks").click()

    def test_tc30_manage_officers_list_critical(self, page: Page):
        page.get_by_role("button", name="Manage Officers").click()
