"""
SIETHub - single-file regression suite (Playwright + pytest + HTML report)

Routes covered: /dashboard /leaderboard /students /career /calendar (+ login, logout, route protection, nav smoke)

SETUP
    pip install pytest pytest-playwright pytest-html playwright
    playwright install chromium

CREDENTIALS
    URL, username and password are set in the CONFIG block just below the imports - edit them there.
    (Optional) environment variables BASE_URL / SIET_USERNAME / SIET_PASSWORD override the values in the file.

RUN  (recommended - builds the HTML report with failure screenshots)
    python test_siethub_regression.py                 # whole suite
    python test_siethub_regression.py -m smoke        # any normal pytest args are passed through
    python test_siethub_regression.py -m dashboard --headed --slowmo 300

    Plain `pytest test_siethub_regression.py --html=report.html --self-contained-html` also works,
    but failure screenshots are only embedded when started with `python test_siethub_regression.py`.

REPORT:  reports/siethub_regression_report.html   (single self-contained file)
"""
import base64
import calendar as cal
import os
import re
import sys
from datetime import date

import pytest
from playwright.sync_api import Page, expect

# ----------------------------------------------------------------------------
# CONFIG  - edit here. The trycloudflare URL changes whenever the tunnel restarts.
# ----------------------------------------------------------------------------
DEFAULT_BASE_URL = "https://dear-halo-molecules-burlington.trycloudflare.com"
DEFAULT_USERNAME = "714023104103"
DEFAULT_PASSWORD = "Siet@2727"

try:  # slow tunnel + big lists -> be a bit patient
    expect.set_options(timeout=15_000)
except AttributeError:
    pass


# ============================================================================
# HELPERS
# ============================================================================
def to_int(text: str):
    """First integer in a string ('Matched For You\n4617' -> 4617, '−20' -> -20)."""
    m = re.search(r"-?\d[\d,]*", text.replace("\u2212", "-"))
    return int(m.group().replace(",", "")) if m else None


def lines(text: str):
    return [ln.strip() for ln in re.split(r"\n+", text.strip()) if ln.strip()]


def month_shift(d: date, n: int) -> date:
    y, m = divmod(d.year * 12 + d.month - 1 + n, 12)
    return date(y, m + 1, 1)


def profile_links(page):
    """Every /profile/<id> link that is NOT in the top navigation bar."""
    return page.locator("xpath=//a[starts-with(@href,'/profile/')][not(ancestor::nav)]")


# ============================================================================
# FIXTURES  (base url, credentials, one-time login, auth page, error watcher)
# ============================================================================
@pytest.fixture(scope="session")
def base_url():
    return os.environ.get("BASE_URL", DEFAULT_BASE_URL).rstrip("/")


@pytest.fixture(scope="session")
def credentials():
    return (os.environ.get("SIET_USERNAME", DEFAULT_USERNAME),
            os.environ.get("SIET_PASSWORD", DEFAULT_PASSWORD))


def ui_login(page, username, password):
    page.goto("/login")
    page.get_by_role("textbox", name="Registration No / Email").fill(username)
    page.get_by_role("textbox", name="Password").fill(password)
    page.get_by_role("button", name="Sign In").click()
    page.wait_for_url(re.compile(r"/dashboard"))


@pytest.fixture(scope="session")
def storage_state_path(browser, browser_context_args, credentials, tmp_path_factory):
    """Log in once through the UI and reuse the session for every authenticated test."""
    ctx = browser.new_context(**browser_context_args)
    page = ctx.new_page()
    ui_login(page, *credentials)
    path = tmp_path_factory.mktemp("auth") / "state.json"
    ctx.storage_state(path=str(path))
    ctx.close()
    return str(path)


@pytest.fixture
def page_errors():
    return {"pageerrors": [], "http5xx": []}


@pytest.fixture
def auth_page(browser, browser_context_args, storage_state_path, page_errors):
    ctx = browser.new_context(**browser_context_args, storage_state=storage_state_path)
    page = ctx.new_page()
    page.on("pageerror", lambda e: page_errors["pageerrors"].append(str(e)))
    page.on("response", lambda r: page_errors["http5xx"].append(f"{r.status} {r.url}") if r.status >= 500 else None)
    yield page
    ctx.close()


@pytest.fixture
def go(auth_page, credentials):
    """go('/students') -> logged-in page on that route (re-logs in if the session was lost)."""
    def _go(path):
        auth_page.goto(path)
        auth_page.wait_for_load_state("domcontentloaded")
        if "/login" in auth_page.url and path != "/login":
            ui_login(auth_page, *credentials)
            auth_page.goto(path)
        return auth_page
    return _go



# ============================================================================
# AUTH: landing, login, logout, route protection
# ============================================================================
PROTECTED = ["/dashboard", "/leaderboard", "/students", "/career", "/calendar"]


@pytest.mark.regression
@pytest.mark.auth
@pytest.mark.smoke
def test_landing_page_content(page: Page):
    page.goto("/")
    expect(page.get_by_role("heading", name="Empower Your Academic Edge.", level=1)).to_be_visible()
    expect(page.get_by_role("link", name="Launch Portal")).to_have_attribute("href", "/login")
    expect(page.get_by_role("link", name="View Leaderboard")).to_have_attribute("href", "/leaderboard")


@pytest.mark.regression
@pytest.mark.auth
@pytest.mark.smoke
def test_login_page_elements(page: Page):
    page.goto("/login")
    expect(page.get_by_role("heading", name="Welcome back")).to_be_visible()
    expect(page.get_by_role("textbox", name="Registration No / Email")).to_be_visible()
    expect(page.get_by_role("textbox", name="Password")).to_be_visible()
    expect(page.get_by_role("button", name="Sign In")).to_be_enabled()
    expect(page.get_by_role("button", name="Forgot Password?")).to_be_visible()


@pytest.mark.regression
@pytest.mark.auth
def test_valid_login_lands_on_dashboard(page: Page, credentials):
    ui_login(page, *credentials)
    expect(page).to_have_url(re.compile(r"/dashboard$"))
    expect(page.locator(f"a[href='/profile/{credentials[0]}']")).to_be_visible()


@pytest.mark.regression
@pytest.mark.auth
def test_wrong_password_stays_on_login(page: Page, credentials):
    page.goto("/login")
    page.get_by_role("textbox", name="Registration No / Email").fill(credentials[0])
    page.get_by_role("textbox", name="Password").fill("definitely-wrong-password")
    page.get_by_role("button", name="Sign In").click()
    page.wait_for_timeout(2000)
    expect(page).to_have_url(re.compile(r"/login$"))
    expect(page.get_by_role("button", name="Sign In")).to_be_visible()


@pytest.mark.regression
@pytest.mark.auth
@pytest.mark.xfail(reason="Exploration: no error text was visible 2.5s after a failed login", strict=False)
def test_wrong_password_shows_error_message(page: Page, credentials):
    page.goto("/login")
    page.get_by_role("textbox", name="Registration No / Email").fill(credentials[0])
    page.get_by_role("textbox", name="Password").fill("definitely-wrong-password")
    page.get_by_role("button", name="Sign In").click()
    expect(page.get_by_text(re.compile(r"invalid|incorrect|wrong|failed|error", re.I))).to_be_visible(timeout=5000)


@pytest.mark.regression
@pytest.mark.auth
def test_empty_form_does_not_log_in(page: Page):
    page.goto("/login")
    page.get_by_role("button", name="Sign In").click()
    page.wait_for_timeout(1500)
    expect(page).to_have_url(re.compile(r"/login$"))


@pytest.mark.regression
@pytest.mark.auth
@pytest.mark.parametrize("route", PROTECTED)
def test_protected_routes_redirect_to_login_when_logged_out(page: Page, route):
    page.goto(route)
    expect(page).to_have_url(re.compile(r"/login$"))


@pytest.mark.regression
@pytest.mark.auth
def test_logout_ends_session(page: Page, credentials):
    ui_login(page, *credentials)
    page.get_by_role("button", name="Logout").click()
    expect(page).not_to_have_url(re.compile(r"/dashboard"))
    page.goto("/dashboard")
    expect(page).to_have_url(re.compile(r"/login$"))


# ============================================================================
# DASHBOARD  /dashboard
# ============================================================================
# tooltip text -> (short label, maximum points).  Tooltip text is unique on the page,
# so it is a stable anchor for each score tile.
SCORE_TILES = {
    "Learning Management": ("LMS", 25),
    "Academic": ("Acad", 10),
    "Coding Platforms": ("Coding", 15),
    "Projects": ("Proj", 10),
    "Achievement": ("Achs", 5),
    "Certifications": ("Certs", 5),
    "Hackathons / Comps": ("Hacks", 5),
    "Internships": ("Ints", 10),
    "Communications": ("Comms", 15),
}
PLATFORM_TABS = ["LeetCode", "GeeksforGeeks", "Codeforces", "HackerRank", "HackerEarth"]


def tile(page, tooltip):
    return page.get_by_text(tooltip, exact=True).locator("xpath=..")


@pytest.fixture
def dash(go):
    page = go("/dashboard")
    expect(page.get_by_text("SIETScore", exact=True)).to_be_visible()
    return page


@pytest.mark.regression
@pytest.mark.dashboard
@pytest.mark.smoke
def test_dashboard_loads_with_navigation(dash):
    expect(dash).to_have_url(re.compile(r"/dashboard$"))
    expect(dash).to_have_title("SIETHub")
    expect(dash.get_by_role("navigation")).to_be_visible()


@pytest.mark.regression
@pytest.mark.dashboard
def test_header_shows_logged_in_student(dash, credentials):
    link = dash.locator(f"a[href='/profile/{credentials[0]}']")
    expect(link).to_be_visible()
    expect(link).to_contain_text("student")
    expect(dash.get_by_role("button", name="Logout")).to_be_visible()


@pytest.mark.regression
@pytest.mark.dashboard
@pytest.mark.parametrize("tooltip,spec", SCORE_TILES.items())
def test_score_tile_shows_label_and_max(dash, tooltip, spec):
    label, maximum = spec
    t = tile(dash, tooltip)
    expect(t).to_contain_text(label)
    expect(t).to_contain_text(f"/{maximum}")


@pytest.mark.regression
@pytest.mark.dashboard
def test_total_score_out_of_100_with_tier_badge(dash):
    expect(dash.get_by_text("/100", exact=True)).to_be_visible()
    expect(dash.get_by_text(re.compile(r"Bronze|Silver|Gold|Platinum|Diamond", re.I)).first).to_be_visible()


@pytest.mark.regression
@pytest.mark.dashboard
def test_total_score_equals_sum_of_tiles_minus_penalty(dash):
    """Data-integrity check: total = sum(component scores) + penalty ('-' counts as 0), floored at 0."""
    total = to_int(dash.get_by_text("/100", exact=True).locator("xpath=..").text_content())
    parts = 0
    for tooltip in SCORE_TILES:
        txt = tile(dash, tooltip).text_content().replace("\u2212", "-").strip()
        m = re.match(r"^(-?\d+)\s*/", txt)
        parts += int(m.group(1)) if m else 0
    penalty = to_int(dash.get_by_text("Penalty", exact=True).locator("xpath=..").text_content()) or 0
    assert total == max(0, parts + penalty), f"total={total}, components={parts}, penalty={penalty}"


@pytest.mark.regression
@pytest.mark.dashboard
def test_overview_widgets(dash):
    for text in ["Overview", "Day Streak", "Current Level", "Rank", "Badges", "Dept", "Batch"]:
        expect(dash.get_by_text(text, exact=True).first).to_be_visible()


@pytest.mark.regression
@pytest.mark.dashboard
def test_streak_card_links_to_stats(dash):
    expect(dash.get_by_role("link", name=re.compile("Day Streak"))).to_have_attribute("href", "/stats")
    expect(dash.get_by_role("link", name="View Detailed Stats")).to_have_attribute("href", "/stats")


@pytest.mark.regression
@pytest.mark.dashboard
def test_recent_activity_section(dash):
    expect(dash.get_by_text("Recent Activity", exact=True)).to_be_visible()
    expect(dash.get_by_role("button", name="View All")).to_be_visible()


@pytest.mark.regression
@pytest.mark.dashboard
def test_current_user_highlighted_in_mini_leaderboard(dash):
    expect(dash.get_by_text("(You)")).to_be_visible()


@pytest.mark.regression
@pytest.mark.dashboard
def test_top3_podium_links_to_profiles(dash):
    links = profile_links(dash)
    assert links.count() >= 3
    for i in range(3):
        expect(links.nth(i)).to_have_attribute("href", re.compile(r"^/profile/\w+"))


@pytest.mark.regression
@pytest.mark.dashboard
def test_platform_tabs_present_and_leetcode_selected_by_default(dash):
    for name in PLATFORM_TABS:
        expect(dash.get_by_role("tab", name=name)).to_be_visible()
    expect(dash.get_by_role("tab", name="LeetCode")).to_have_attribute("aria-selected", "true")
    expect(dash.get_by_role("button", name="Sync Now")).to_be_visible()


@pytest.mark.regression
@pytest.mark.dashboard
@pytest.mark.parametrize("name", PLATFORM_TABS)
def test_platform_tab_can_be_selected(dash, name):
    tab = dash.get_by_role("tab", name=name)
    tab.click()
    expect(tab).to_have_attribute("aria-selected", "true")


@pytest.mark.regression
@pytest.mark.dashboard
def test_submission_heatmap_has_cells(dash):
    expect(dash.get_by_role("heading", name="Submission Activity")).to_be_visible()
    cells = dash.locator("[title$='submissions'], [aria-label$='submissions']")
    assert cells.count() >= 28, "heatmap should render at least a month of day cells"


@pytest.mark.regression
@pytest.mark.dashboard
def test_academics_and_expertise_sections(dash):
    expect(dash.get_by_role("heading", name="Academics & LMS")).to_be_visible()
    expect(dash.get_by_text("CGPA", exact=True)).to_be_visible()
    expect(dash.get_by_text("Overall LMS", exact=True)).to_be_visible()
    expect(dash.get_by_role("heading", name="Technical Expertise")).to_be_visible()


# ============================================================================
# LEADERBOARD  /leaderboard
# ============================================================================
def stat_value(page, label, which="first"):
    lbl = page.get_by_text(label, exact=True)
    lbl = lbl.first if which == "first" else lbl.last
    return lbl.locator("xpath=preceding-sibling::*[1]")


def table_rows(page):
    return profile_links(page).filter(has_text=re.compile(r"^\s*#\d+"))


def parse_row(row):
    ls = lines(row.inner_text())
    return int(ls[0].lstrip("#")), int(ls[-1]), ls[-3]  # rank, score, dept


def parse_podium(link):
    ls = lines(link.inner_text())
    return {"name": ls[-3], "dept": ls[-2], "score": int(ls[-1])}


@pytest.fixture
def lb(go):
    page = go("/leaderboard")
    expect(page.get_by_role("heading", name="Leaderboard", level=1)).to_be_visible()
    expect(page.get_by_text(re.compile(r"Page 1 of \d+"))).to_be_visible()
    return page


@pytest.mark.regression
@pytest.mark.leaderboard
@pytest.mark.smoke
def test_leaderboard_loads(lb):
    expect(lb).to_have_url(re.compile(r"/leaderboard$"))
    expect(lb.get_by_text("Ranked by SIETScore", exact=False)).to_be_visible()


@pytest.mark.regression
@pytest.mark.leaderboard
def test_summary_cards(lb):
    for label in ["Achievements", "Top SIETScore", "Top Scorer"]:
        expect(lb.get_by_text(label, exact=True).first).to_be_visible()
    assert to_int(stat_value(lb, "Students", "last").inner_text()) > 0
    assert to_int(stat_value(lb, "Top SIETScore").inner_text()) > 0


@pytest.mark.regression
@pytest.mark.leaderboard
def test_toolbar_buttons(lb):
    expect(lb.get_by_role("button", name="Filters")).to_be_enabled()
    expect(lb.get_by_role("button", name="Refresh")).to_be_enabled()


@pytest.mark.regression
@pytest.mark.leaderboard
def test_refresh_keeps_table(lb):
    lb.get_by_role("button", name="Refresh").click()
    expect(table_rows(lb).first).to_be_visible()


@pytest.mark.regression
@pytest.mark.leaderboard
def test_podium_has_three_profile_links(lb):
    links = profile_links(lb)
    for i in range(3):
        expect(links.nth(i)).to_have_attribute("href", re.compile(r"^/profile/\w+"))


@pytest.mark.regression
@pytest.mark.leaderboard
def test_top_scorer_card_matches_podium_winner(lb):
    podium = [parse_podium(profile_links(lb).nth(i)) for i in range(3)]
    best = max(podium, key=lambda p: p["score"])
    assert to_int(stat_value(lb, "Top SIETScore").inner_text()) == best["score"]
    top_name = stat_value(lb, "Top Scorer").inner_text().strip()
    assert top_name.upper().startswith(best["name"].upper()), (top_name, best)


@pytest.mark.regression
@pytest.mark.leaderboard
def test_table_headers(lb):
    for h in ["Rank", "Student", "Dept", "Achievements", "SIETScore"]:
        expect(lb.get_by_text(h, exact=True).first).to_be_visible()


@pytest.mark.regression
@pytest.mark.leaderboard
def test_table_sorted_by_score_desc_with_consecutive_ranks(lb):
    rows = [parse_row(r) for r in table_rows(lb).all()]
    assert len(rows) > 5
    ranks = [r[0] for r in rows]
    scores = [r[1] for r in rows]
    assert ranks == list(range(ranks[0], ranks[0] + len(ranks))), "ranks must be consecutive"
    assert scores == sorted(scores, reverse=True), "scores must be non-increasing"


@pytest.mark.regression
@pytest.mark.leaderboard
def test_podium_scores_not_below_table_scores(lb):
    podium_min = min(parse_podium(profile_links(lb).nth(i))["score"] for i in range(3))
    first_table_score = parse_row(table_rows(lb).first)[1]
    assert podium_min >= first_table_score


@pytest.mark.regression
@pytest.mark.leaderboard
def test_leaderboard_pagination_next_and_prev(lb):
    rows = [parse_row(r) for r in table_rows(lb).all()]
    last_rank = rows[-1][0]
    expect(lb.get_by_role("button", name="Prev")).to_be_disabled()
    lb.get_by_role("button", name="Next").click()
    expect(lb.get_by_text(re.compile(r"Page 2 of \d+"))).to_be_visible()
    expect(table_rows(lb).first).to_contain_text(f"#{last_rank + 1}")
    lb.get_by_role("button", name="Prev").click()
    expect(lb.get_by_text(re.compile(r"Page 1 of \d+"))).to_be_visible()


@pytest.mark.regression
@pytest.mark.leaderboard
def test_row_click_opens_profile(lb):
    table_rows(lb).first.click()
    expect(lb).to_have_url(re.compile(r"/profile/\w+"))


@pytest.mark.regression
@pytest.mark.leaderboard
def test_dashboard_top3_matches_leaderboard_top3(go):
    page = go("/dashboard")
    expect(page.get_by_text("SIETScore", exact=True)).to_be_visible()
    dash_ids = {profile_links(page).nth(i).get_attribute("href") for i in range(3)}
    page = go("/leaderboard")
    expect(page.get_by_text(re.compile(r"Page 1 of \d+"))).to_be_visible()
    lb_ids = {profile_links(page).nth(i).get_attribute("href") for i in range(3)}
    assert dash_ids == lb_ids


@pytest.mark.regression
@pytest.mark.leaderboard
def test_leaderboard_student_count_matches_students_page(go):
    page = go("/leaderboard")
    expect(page.get_by_text(re.compile(r"Page 1 of \d+"))).to_be_visible()
    lb_total = to_int(stat_value(page, "Students", "last").inner_text())
    page = go("/students")
    txt = page.get_by_text(re.compile(r"^\d+ of \d+ students$", re.I)).inner_text()
    assert lb_total == int(re.search(r"of (\d+)", txt).group(1))


# ============================================================================
# STUDENTS  /students
# ============================================================================
DEPT_CHIPS = ["All", "AGE", "AIDS", "AIML", "BME", "BT", "CIVIL", "COMPUTER SCIENCE", "CSE",
              "CSE_FACULTY", "CYS", "ECE", "EEE", "FT", "IT", "MECH", "VLSI"]
COUNT_RE = re.compile(r"^\d+ of \d+ students$", re.I)


def count_loc(page):
    return page.get_by_text(COUNT_RE)


def counts(page):
    shown, total = map(int, re.findall(r"\d+", count_loc(page).inner_text()))
    return shown, total


@pytest.fixture
def students(go):
    page = go("/students")
    expect(page.get_by_role("heading", name="Students", level=1)).to_be_visible()
    expect(count_loc(page)).to_be_visible()
    expect(profile_links(page).first).to_be_visible()
    return page


@pytest.mark.regression
@pytest.mark.students
@pytest.mark.smoke
def test_students_page_loads(students):
    expect(students).to_have_url(re.compile(r"/students$"))
    shown, total = counts(students)
    assert shown == total and total > 0


@pytest.mark.regression
@pytest.mark.students
@pytest.mark.parametrize("dept", DEPT_CHIPS)
def test_department_chip_visible(students, dept):
    expect(students.get_by_role("button", name=dept, exact=True)).to_be_visible()


@pytest.mark.regression
@pytest.mark.students
def test_students_filter_controls_visible(students):
    expect(students.get_by_placeholder("Search by name, reg no…")).to_be_visible()
    for name in ["All Depts", "All Sections", "All Batches"]:
        expect(students.get_by_role("button", name=name)).to_be_visible()


@pytest.mark.regression
@pytest.mark.students
def test_cards_show_name_dept_regno_and_batch(students):
    card = profile_links(students).first
    expect(card).to_have_attribute("href", re.compile(r"^/profile/\w+"))
    expect(card).to_contain_text(re.compile(r"Batch"))


@pytest.mark.regression
@pytest.mark.students
@pytest.mark.parametrize("dept", ["CSE", "AIDS", "ECE", "IT"])
def test_department_chip_filters_list(students, dept):
    _, total = counts(students)
    initial = count_loc(students).inner_text()
    students.get_by_role("button", name=dept, exact=True).click()
    expect(count_loc(students)).not_to_have_text(initial)
    shown, _ = counts(students)
    assert 0 < shown < total
    for card in profile_links(students).all():
        assert dept in lines(card.inner_text()), f"card not in {dept}: {card.inner_text()!r}"


@pytest.mark.regression
@pytest.mark.students
def test_all_chip_resets_filter(students):
    initial = count_loc(students).inner_text()
    students.get_by_role("button", name="CSE", exact=True).click()
    expect(count_loc(students)).not_to_have_text(initial)
    students.get_by_role("button", name="All", exact=True).click()
    expect(count_loc(students)).to_have_text(initial)


@pytest.mark.regression
@pytest.mark.students
def test_search_by_name(students):
    initial = count_loc(students).inner_text()
    students.get_by_placeholder("Search by name, reg no…").fill("AADHI")
    expect(count_loc(students)).not_to_have_text(initial)
    cards = profile_links(students)
    assert cards.count() > 0
    for card in cards.all():
        assert "aadhi" in card.inner_text().lower()


@pytest.mark.regression
@pytest.mark.students
def test_search_by_registration_number(students, credentials):
    students.get_by_placeholder("Search by name, reg no…").fill(credentials[0])
    expect(profile_links(students)).to_have_count(1)
    expect(profile_links(students).first).to_have_attribute("href", f"/profile/{credentials[0]}")


@pytest.mark.regression
@pytest.mark.students
def test_search_with_no_match_shows_zero(students):
    students.get_by_placeholder("Search by name, reg no…").fill("zzzzqqqq-no-such-student")
    expect(count_loc(students)).to_have_text(re.compile(r"^0 of \d+ students$", re.I))
    expect(profile_links(students)).to_have_count(0)


@pytest.mark.regression
@pytest.mark.students
def test_students_pagination_next_prev(students):
    first_href = profile_links(students).first.get_attribute("href")
    expect(students.get_by_role("button", name="Prev")).to_be_disabled()
    expect(students.get_by_text(re.compile(r"Page 1 of \d+"))).to_be_visible()
    students.get_by_role("button", name="Next").click()
    expect(students.get_by_text(re.compile(r"Page 2 of \d+"))).to_be_visible()
    expect(profile_links(students).first).not_to_have_attribute("href", first_href)
    expect(students.get_by_role("button", name="Prev")).to_be_enabled()
    students.get_by_role("button", name="Prev").click()
    expect(profile_links(students).first).to_have_attribute("href", first_href)


@pytest.mark.regression
@pytest.mark.students
def test_card_click_opens_profile(students):
    href = profile_links(students).first.get_attribute("href")
    profile_links(students).first.click()
    expect(students).to_have_url(re.compile(re.escape(href) + "$"))


# ============================================================================
# CAREER  /career
# ============================================================================
SEARCH = "Search jobs, companies..."
LOCATION = "Filter by location..."


def total_loc(page):
    return page.get_by_text(re.compile(r"^\(\s*[\d,]+\s+postings\s*\)$", re.I))


def total(page):
    return to_int(total_loc(page).inner_text())


def tab(page, name):
    return page.get_by_role("button", name=re.compile(f"^{name}"))


@pytest.fixture
def career(go):
    page = go("/career")
    expect(page.get_by_role("heading", level=3).first).to_be_visible()
    expect(total_loc(page)).to_be_visible()
    return page


@pytest.mark.regression
@pytest.mark.career
@pytest.mark.smoke
def test_career_loads(career):
    expect(career).to_have_url(re.compile(r"/career$"))
    expect(career.get_by_text("Filter Postings")).to_be_visible()


@pytest.mark.regression
@pytest.mark.career
def test_career_filter_controls_visible(career):
    expect(career.get_by_placeholder(SEARCH)).to_be_visible()
    expect(career.get_by_placeholder(LOCATION)).to_be_visible()
    expect(career.get_by_role("button", name="All Domains")).to_be_visible()
    expect(career.get_by_role("button", name="All Job Types")).to_be_visible()


@pytest.mark.regression
@pytest.mark.career
def test_tabs_show_counts_and_default_to_matched(career):
    matched = to_int(tab(career, "Matched For You").inner_text())
    all_posts = to_int(tab(career, "All Postings").inner_text())
    assert matched > 0 and all_posts >= matched
    assert total(career) == matched


@pytest.mark.regression
@pytest.mark.career
def test_all_postings_tab_total_matches_badge(career):
    all_posts = to_int(tab(career, "All Postings").inner_text())
    tab(career, "All Postings").click()
    expect(total_loc(career)).to_contain_text(f"{all_posts}")


@pytest.mark.regression
@pytest.mark.career
def test_each_card_has_title_details_and_apply(career):
    titles = career.get_by_role("heading", level=3).count()
    assert titles > 0
    assert career.get_by_role("button", name="Read Details").count() == titles
    assert career.get_by_role("link", name="Apply Now").count() == titles


@pytest.mark.regression
@pytest.mark.career
def test_apply_links_are_external_https(career):
    for link in career.get_by_role("link", name="Apply Now").all():
        assert (link.get_attribute("href") or "").startswith("https://")


@pytest.mark.regression
@pytest.mark.career
def test_match_percentages_valid_and_sorted_desc_in_matched_tab(career):
    vals = [to_int(t) for t in career.get_by_text(re.compile(r"^\d+% Match$")).all_inner_texts()]
    assert vals, "no match percentages rendered"
    assert all(0 <= v <= 100 for v in vals)
    assert vals == sorted(vals, reverse=True)


@pytest.mark.regression
@pytest.mark.career
def test_keyword_search_narrows_results(career):
    before = total(career)
    career.get_by_placeholder(SEARCH).fill("MERN")
    expect(total_loc(career)).not_to_have_text(re.compile(rf"\({before}\s"))
    after = total(career)
    assert 0 < after < before


@pytest.mark.regression
@pytest.mark.career
def test_location_filter_narrows_results(career):
    before = total(career)
    career.get_by_placeholder(LOCATION).fill("Bengaluru")
    expect(total_loc(career)).not_to_have_text(re.compile(rf"\({before}\s"))
    assert total(career) < before


@pytest.mark.regression
@pytest.mark.career
def test_career_pagination_next_prev(career):
    first_title = career.get_by_role("heading", level=3).first.inner_text()
    expect(career.get_by_role("button", name="Prev")).to_be_disabled()
    expect(career.get_by_text(re.compile(r"Page 1 of \d+"))).to_be_visible()
    career.get_by_role("button", name="Next").click()
    expect(career.get_by_text(re.compile(r"Page 2 of \d+"))).to_be_visible()
    expect(career.get_by_role("button", name="Prev")).to_be_enabled()


@pytest.mark.regression
@pytest.mark.career
@pytest.mark.xfail(reason="Known data issue found in exploration: the same LinkedIn job is listed several times on page 1",
                   strict=False)
def test_no_duplicate_postings_on_first_page(career):
    ids = []
    for link in career.get_by_role("link", name="Apply Now").all():
        m = re.search(r"-(\d{8,})\?", link.get_attribute("href") or "")
        ids.append(m.group(1) if m else link.get_attribute("href"))
    dupes = {i for i in ids if ids.count(i) > 1}
    assert not dupes, f"duplicate job ids on page 1: {sorted(dupes)}"


# ============================================================================
# CALENDAR  /calendar
# ============================================================================
LEGEND = ["Holiday/Sunday", "Event", "Holiday", "Exam", "Internal Assessment", "Announcement"]


def month_heading(page, d: date):
    return page.get_by_role("heading", level=2, name=d.strftime("%B %Y"))


def prev_btn(page):
    return page.get_by_role("heading", level=2).locator("xpath=preceding-sibling::button[1]")


def next_btn(page):
    return page.get_by_role("heading", level=2).locator("xpath=following-sibling::button[1]")


@pytest.fixture
def calendar_page(go):
    page = go("/calendar")
    expect(page.get_by_role("heading", name="Academic Calendar", level=1)).to_be_visible()
    return page


@pytest.mark.regression
@pytest.mark.calendar
@pytest.mark.smoke
def test_calendar_loads(calendar_page):
    expect(calendar_page).to_have_url(re.compile(r"/calendar$"))
    expect(calendar_page.get_by_text("SIET Hub")).to_be_visible()


@pytest.mark.regression
@pytest.mark.calendar
def test_opens_on_current_month(calendar_page):
    expect(month_heading(calendar_page, date.today())).to_be_visible()


@pytest.mark.regression
@pytest.mark.calendar
@pytest.mark.parametrize("day", ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"])
def test_weekday_header(calendar_page, day):
    expect(calendar_page.get_by_text(day, exact=True)).to_be_visible()


@pytest.mark.regression
@pytest.mark.calendar
def test_grid_contains_first_and_last_day_of_month(calendar_page):
    last = cal.monthrange(date.today().year, date.today().month)[1]
    expect(calendar_page.get_by_text("1", exact=True).first).to_be_visible()
    expect(calendar_page.get_by_text(str(last), exact=True)).to_be_visible()


@pytest.mark.regression
@pytest.mark.calendar
@pytest.mark.parametrize("label", LEGEND)
def test_legend_item_visible(calendar_page, label):
    expect(calendar_page.get_by_text(label, exact=True)).to_be_visible()


@pytest.mark.regression
@pytest.mark.calendar
def test_next_and_previous_month(calendar_page):
    today = date.today()
    next_btn(calendar_page).click()
    expect(month_heading(calendar_page, month_shift(today, 1))).to_be_visible()
    prev_btn(calendar_page).click()
    expect(month_heading(calendar_page, today)).to_be_visible()
    prev_btn(calendar_page).click()
    expect(month_heading(calendar_page, month_shift(today, -1))).to_be_visible()


@pytest.mark.regression
@pytest.mark.calendar
def test_today_button_returns_to_current_month(calendar_page):
    next_btn(calendar_page).click()
    next_btn(calendar_page).click()
    calendar_page.get_by_role("button", name="Today").click()
    expect(month_heading(calendar_page, date.today())).to_be_visible()


@pytest.mark.regression
@pytest.mark.calendar
def test_year_rollover(calendar_page):
    for _ in range(12):
        next_btn(calendar_page).click()
    expect(month_heading(calendar_page, month_shift(date.today(), 12))).to_be_visible()


# ============================================================================
# NAVIGATION & SMOKE (all routes)
# ============================================================================
ROUTES = ["/dashboard", "/leaderboard", "/students", "/career", "/calendar"]
NAV = [("Dashboard", "/dashboard"), ("Leaderboard", "/leaderboard"), ("Students", "/students"),
       ("Career", "/career"), ("My Class", "/my-class"), ("My Batch", "/my-batch"), ("Calendar", "/calendar")]


@pytest.mark.regression
@pytest.mark.smoke
@pytest.mark.parametrize("route", ROUTES)
def test_route_renders_for_logged_in_user(go, route):
    page = go(route)
    expect(page).to_have_url(re.compile(re.escape(route) + "$"))
    expect(page).to_have_title("SIETHub")
    expect(page.get_by_role("navigation")).to_be_visible()


@pytest.mark.regression
@pytest.mark.smoke
@pytest.mark.parametrize("route", ROUTES)
def test_route_has_no_js_errors_or_server_errors(go, page_errors, route):
    page = go(route)
    page.wait_for_load_state("load")
    page.wait_for_timeout(2000)  # grace window for late XHR/render errors
    assert page_errors["pageerrors"] == [], page_errors["pageerrors"]
    assert page_errors["http5xx"] == [], page_errors["http5xx"]


@pytest.mark.regression
@pytest.mark.smoke
@pytest.mark.parametrize("label,path", NAV)
def test_nav_link_navigates(go, label, path):
    page = go("/dashboard")
    page.get_by_role("navigation").get_by_role("link", name=label, exact=True).click()
    expect(page).to_have_url(re.compile(re.escape(path) + "$"))


@pytest.mark.regression
@pytest.mark.smoke
def test_lms_link_points_to_external_lms(go):
    page = go("/dashboard")
    link = page.get_by_role("navigation").get_by_role("link", name="LMS", exact=True)
    expect(link).to_have_attribute("href", re.compile(r"^https?://.+/LMS/"))


@pytest.mark.regression
@pytest.mark.smoke
def test_logo_returns_to_landing_page(go):
    page = go("/students")
    page.get_by_role("link", name=re.compile("SIET HUB")).click()
    expect(page).to_have_url(re.compile(r"/$"))


# ============================================================================
# REPORT PLUGIN  (title, metadata, failure screenshots) + entry point
# ============================================================================
class _ReportPlugin:
    def pytest_configure(self, config):
        for m in ("smoke", "regression", "auth", "dashboard", "leaderboard", "students", "career", "calendar"):
            config.addinivalue_line("markers", f"{m}: SIETHub {m} tests")
        try:
            from pytest_metadata.plugin import metadata_key
            config.stash[metadata_key]["Base URL"] = os.environ.get("BASE_URL", DEFAULT_BASE_URL)
            config.stash[metadata_key]["Routes"] = "/dashboard /leaderboard /students /career /calendar"
        except Exception:
            pass

    def pytest_html_report_title(self, report):
        report.title = "SIETHub - Regression Test Report"

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_makereport(self, item, call):
        outcome = yield
        report = outcome.get_result()
        if report.when != "call" or not report.failed:
            return
        page = item.funcargs.get("auth_page") or item.funcargs.get("page")
        if page is None:
            return
        try:
            import pytest_html
            shot = base64.b64encode(page.screenshot(full_page=True)).decode()
            extras = getattr(report, "extras", [])
            extras.append(pytest_html.extras.png(shot, "Failure screenshot"))
            extras.append(pytest_html.extras.url(page.url, "Page URL at failure"))
            report.extras = extras
        except Exception:
            pass


if __name__ == "__main__":
    os.makedirs("reports", exist_ok=True)
    args = [__file__, "-ra", "--html=reports/siethub_regression_report.html", "--self-contained-html"] + sys.argv[1:]
    sys.exit(pytest.main(args, plugins=[_ReportPlugin()]))
