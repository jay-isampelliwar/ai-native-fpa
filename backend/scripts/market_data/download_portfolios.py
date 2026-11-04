"""Download each AMC's latest monthly portfolio files into sql/data/sources/<date>/portfolios/<amc>/."""

import argparse
import io
import re
import uuid
import zipfile
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote, unquote, urljoin

import httpx

from scripts.market_data.common import source_dir

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36"

TIMEOUT_SECONDS = 180

MAX_PARALLEL_AMCS = 4

MONTHS_TO_LOOK_BACK = 3

EXCEL_SUFFIXES = (".xls", ".xlsx")

MONTH_NAMES = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
    )

BLOCKED_AMCS = {
    "hdfc": "bot protection (Akamai 403) on every page",
    "kotak": "captcha page (Radware) on every page",
    "axis": "encrypted request scheme on the portfolio API",
    }


def client() -> httpx.Client:

    """One HTTP client per AMC with a normal browser User-Agent."""

    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=TIMEOUT_SECONDS,
        follow_redirects=True,
        )


def recent_months(run_date: date) -> list[tuple[int, str]]:

    """The last few (year, month name) pairs before run_date, newest first."""

    months = []
    year, month = run_date.year, run_date.month

    for _ in range(MONTHS_TO_LOOK_BACK):
        month -= 1

        if month == 0:
            year, month = year - 1, 12

        months.append((year, MONTH_NAMES[month - 1]))

    return months


def file_name_from(url: str) -> str:

    """A safe local file name taken from the last part of a URL."""

    name = unquote(httpx.URL(url).path.rstrip("/").split("/")[-1])

    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)


def save_excel_or_zip(
    http: httpx.Client,
    url: str,
    folder: Path,
    name: str | None = None,
    keep: Callable[[str], bool] = lambda name: True
    ) -> list[str]:

    """Download one file; unpack Excel files from a zip, or save the Excel file as it is."""

    response = http.get(url)
    response.raise_for_status()

    body = response.content

    if body[:2] == b"PK" and zipfile.is_zipfile(io.BytesIO(body)) and not url.lower().split("?")[0].endswith(".xlsx"):

        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            names = [info.filename for info in archive.infolist() if not info.is_dir()]
            excel_names = [item for item in names if item.lower().endswith(EXCEL_SUFFIXES)]

            if excel_names:
                saved = []

                for item in excel_names:
                    base = Path(item).name

                    if not keep(base):
                        continue

                    (folder / base).write_bytes(archive.read(item))
                    saved.append(base)

                return saved

    target = folder / (name or file_name_from(url))
    target.write_bytes(body)

    return [target.name]


def fetch_sbi(
    http: httpx.Client,
    folder: Path,
    run_date: date,
    limit: int | None
    ) -> list[str]:

    """SBI: list the month's sheets through the CMS call and take the all-schemes workbook."""

    for year, month in recent_months(run_date):
        response = http.post(
            "https://www.sbimf.com/ajaxcall/CMS/GetSchemePortfolioSheets",
            json={"FundId": 0, "PSYear": str(year), "PSMonth": month, "PSFrequency": "Monthly"},
            headers={"Referer": "https://www.sbimf.com/portfolios"},
            )

        links = re.findall(r'href="([^"]*all-schemes-monthly-portfolio[^"]*)"', response.text, flags=re.IGNORECASE)

        if links:
            return save_excel_or_zip(http, urljoin("https://www.sbimf.com/", links[0].replace("&amp;", "&")), folder)

    return []


def fetch_icici(
    http: httpx.Client,
    folder: Path,
    run_date: date,
    limit: int | None
    ) -> list[str]:

    """ICICI Prudential: ask the downloads API for the newest monthly disclosure zip."""

    response = http.post(
        "https://apimf.icicipruamc.com/nms/v1/downloads/files",
        headers={"env": "api", "sourceUrl": "DOWNLOADS", "requestAPIId": str(uuid.uuid4()), "Accept": "*/*"},
        json={
            "categoryId": "26a073d7-08d2-4a95-95fa-f83a4ee51e40",
            "schemeCategory": "",
            "userType": "Investor",
            "fileType": "All",
            "page": "1",
            "size": "20",
            "filter": [],
            "categoryName": "OTHERS",
            },
        )
    response.raise_for_status()

    if "json" not in response.headers.get("content-type", ""):
        raise RuntimeError("got a bot check page instead of data, try again later")

    files = response.json()["success"]["data"]["files"]
    monthly = [item for item in files if "monthly" in item["url"].lower() and item["url"].lower().endswith(".zip")]

    if not monthly:
        return []

    url = "https://www.icicipruamc.com/blob" + quote(monthly[0]["url"])
    saved = save_excel_or_zip(http, url, folder)

    return saved[:limit] if limit else saved


def fetch_nippon(
    http: httpx.Client,
    folder: Path,
    run_date: date,
    limit: int | None
    ) -> list[str]:

    """Nippon India: the first monthly portfolio link on the server-rendered downloads page."""

    page = http.get("https://mf.nipponindiaim.com/investor-service/downloads/factsheet-portfolio-and-other-disclosures")
    links = re.findall(r'href="([^"]*NIMF-MONTHLY-PORTFOLIO-[^"]+\.xlsx?)"', page.text, flags=re.IGNORECASE)

    if not links:
        return []

    return save_excel_or_zip(http, urljoin("https://mf.nipponindiaim.com/", links[0]), folder)


def fetch_absl(
    http: httpx.Client,
    folder: Path,
    run_date: date,
    limit: int | None
    ) -> list[str]:

    """Aditya Birla Sun Life: the newest monthly zip from the accordion API, fetched from the main host."""

    response = http.get(
        "https://mutualfund.adityabirlacapital.com/postlogin/CustomApi/Resources/FactsheetAccordionById",
        params={
            "id": "3ccab227-9de5-4494-b78d-2b4f7c0c054a",
            "ctype": "/sitecore/content/Root/BSL/Library/Lists/FAQ/Customer Types/Individual",
            "month": " ",
            "year": "0",
            },
        )
    response.raise_for_status()

    items = response.json().get("AccordionList", [])

    if not items:
        return []

    path = httpx.URL(items[0]["pdfUrl"]).path

    return save_excel_or_zip(http, "https://mutualfund.adityabirlacapital.com" + path, folder)


def fetch_uti(
    http: httpx.Client,
    folder: Path,
    run_date: date,
    limit: int | None
    ) -> list[str]:

    """UTI: the consolidated zip for the newest month, keeping only the SEBI exposure workbook."""

    for year, month in recent_months(run_date):
        response = http.get(
            "https://www.utimf.com/api/get-consolidate-portfolio-disclosure",
            params={"year": year, "month": month},
            )

        rows = response.json().get("rows", []) if response.status_code == 200 else []

        if rows:
            return save_excel_or_zip(http, rows[0]["doc"], folder, keep=lambda name: name.lower().startswith("sebi exposure"))

    return []


def fetch_mirae(
    http: httpx.Client,
    folder: Path,
    run_date: date,
    limit: int | None
    ) -> list[str]:

    """Mirae Asset: every per-scheme file that shares the newest 'as on' date in the downloads list."""

    response = http.post(
        "https://www.miraeassetmf.co.in/AjaxService/GetDownloadsData",
        json={"request": {"modulename": "portfolio_tab1", "pgno": 1, "pgsize": 150}},
        headers={"Content-Type": "application/json;charset=utf-8"},
        )
    response.raise_for_status()

    items = response.json().get("Data", [])

    if not items:
        return []

    newest = re.search(r"as on (.+?) for", items[0]["Title"])
    stamp = newest.group(1) if newest else ""
    latest = [item for item in items if stamp and f"as on {stamp} for" in item["Title"]][:limit]

    saved = []

    for item in latest:
        saved += save_excel_or_zip(http, urljoin("https://www.miraeassetmf.co.in/", item["URL"]), folder)

    return saved


def fetch_dsp(
    http: httpx.Client,
    folder: Path,
    run_date: date,
    limit: int | None
    ) -> list[str]:

    """DSP: the first zip under 'Month End Portfolio Disclosures' on the static page."""

    page = http.get("https://www.dspim.com/mandatory-disclosures/portfolio-disclosures").text
    start = page.find("Month End Portfolio Disclosures")
    links = re.findall(r'href="([^"]+\.zip)"', page[start:]) if start >= 0 else []

    if not links:
        return []

    return save_excel_or_zip(http, urljoin("https://www.dspim.com/", links[0]), folder)


def fetch_tata(
    http: httpx.Client,
    folder: Path,
    run_date: date,
    limit: int | None
    ) -> list[str]:

    """Tata: the monthly portfolio workbook with the newest date in its file name."""

    page = http.get("https://www.tatamutualfund.com/schemes-related/portfolio").text
    links = set(re.findall(r'(https://www\.tatamutualfund\.com/system/files/[^"\\]*Monthly%20Portfolio%20as%20on[^"\\]*\.xlsx)', page))

    def portfolio_date(link: str) -> date:

        """The date written in a Tata file name, or a very old date when it cannot be read."""

        found = re.search(r"on%20(\d{1,2})[a-z]{2}%20([A-Za-z]+)%20(\d{4})", link)

        try:
            return datetime.strptime(" ".join(found.groups()), "%d %B %Y").date() if found else date.min

        except ValueError:
            return date.min

    if not links:
        return []

    return save_excel_or_zip(http, max(links, key=portfolio_date), folder)


def fetch_bandhan(
    http: httpx.Client,
    folder: Path,
    run_date: date,
    limit: int | None
    ) -> list[str]:

    """Bandhan: one file per scheme from the CMS posts that carry the newest date."""

    response = http.get(
        "https://cmsnew.bandhanmutual.com/wp-json/finance-api/v1/posts/scheme-portfolios/monthly-and-half-yearly",
        params={"posts_per_page": 150},
        )
    response.raise_for_status()

    posts = response.json().get("data", [])
    dated = [(re.search(r"(\d{1,2} [A-Za-z]+ \d{4})\s*$", post.get("title", "")), post) for post in posts]
    dated = [(match.group(1), post) for match, post in dated if match]

    if not dated:
        return []

    newest = max(datetime.strptime(stamp, "%d %B %Y") for stamp, _ in dated)
    newest_text = newest.strftime("%d %B %Y").lstrip("0")

    by_title: dict[str, dict] = {}

    for stamp, post in dated:

        if stamp.lstrip("0") == newest_text and post.get("id", 0) >= by_title.get(post["title"], {}).get("id", 0):
            by_title[post["title"]] = post

    saved = []

    for post in list(by_title.values())[:limit]:
        files = post.get("acf_fields", {}).get("disclosure_files") or []

        if files:
            saved += save_excel_or_zip(http, files[0]["document_link"]["url"], folder)

    return saved


def title_month(title: str) -> tuple[int, int]:

    """The (year, month) named in a title such as 'Scheme Portfolio Details September 2026', else (0, 0)."""

    found = re.search(r"([A-Za-z]{3,9})\s+(\d{4})", title)

    if not found:
        return 0, 0

    for number, name in enumerate(MONTH_NAMES, start=1):

        if name.lower().startswith(found.group(1).lower()[:3]):
            return int(found.group(2)), number

    return 0, 0


def fetch_motilal(
    http: httpx.Client,
    folder: Path,
    run_date: date,
    limit: int | None
    ) -> list[str]:

    """Motilal Oswal: the newest 'Scheme Portfolio Details' workbook from the search API."""

    for year in (run_date.year, run_date.year - 1):
        response = http.get(
            "https://www.motilaloswalmf.com/content/aem-cloud-dept-backend-motilal-oswal/api/search-documents.json",
            params={"year": year, "category": "month end portfolio", "month": "", "type": "mf"},
            )

        results = response.json().get("results", []) if response.status_code == 200 else []
        monthly = [item for item in results if item.get("title", "").lower().startswith("scheme portfolio detail")]

        if monthly:
            newest = max(monthly, key=lambda item: title_month(item.get("title", "")))

            return save_excel_or_zip(http, "https://www.motilaloswalmf.com" + quote(newest["path"]), folder)

    return []


def fetch_hsbc(
    http: httpx.Client,
    folder: Path,
    run_date: date,
    limit: int | None
    ) -> list[str]:

    """HSBC: every per-scheme file in the newest dated portfolio folder of the information library."""

    library = "https://www.assetmanagement.hsbc.co.in/en/mutual-funds/investor-resources/information-library"
    page = http.get(library).text
    links = set(re.findall(r'href="/?(-/media/files/attachments/india/mutual-funds/portfolios/document-(\d{8})/[^"]+)"', page))

    if not links:
        return []

    newest = max(links, key=lambda item: datetime.strptime(item[1], "%d%m%Y"))[1]
    latest = sorted(path for path, stamp in links if stamp == newest)[:limit]

    saved = []

    for path in latest:
        name = path.rstrip("/").split("/")[-1] + ".xlsx"
        saved += save_excel_or_zip(
            http,
            "https://www.assetmanagement.hsbc.co.in/" + path,
            folder,
            name=name,
            )

    return saved


def fetch_ppfas(
    http: httpx.Client,
    folder: Path,
    run_date: date,
    limit: int | None
    ) -> list[str]:

    """PPFAS: every per-scheme report that carries the newest month in its file name."""

    page = http.get("https://amc.ppfas.com/downloads/portfolio-disclosure/").text
    pattern = r'(/downloads/portfolio-disclosure/\d{4}/([A-Z]+)_PPFAS_Monthly_Portfolio_Report_([A-Za-z]+)_(\d{1,2})_(\d{4})\.xlsx?)'
    links = set(re.findall(pattern, page))

    if not links:
        return []

    def report_date(link: tuple) -> date:

        """The date written in a PPFAS file name."""

        return datetime.strptime(f"{link[3]} {link[2]} {link[4]}", "%d %B %Y").date()

    newest = max(report_date(link) for link in links)
    latest = sorted(link[0] for link in links if report_date(link) == newest)[:limit]

    saved = []

    for path in latest:
        saved += save_excel_or_zip(http, "https://amc.ppfas.com" + path, folder)

    return saved


FETCHERS: dict[str, Callable[[httpx.Client, Path, date, int | None], list[str]]] = {
    "sbi": fetch_sbi,
    "icici": fetch_icici,
    "nippon": fetch_nippon,
    "absl": fetch_absl,
    "uti": fetch_uti,
    "mirae": fetch_mirae,
    "dsp": fetch_dsp,
    "tata": fetch_tata,
    "bandhan": fetch_bandhan,
    "motilal": fetch_motilal,
    "hsbc": fetch_hsbc,
    "ppfas": fetch_ppfas,
    }


def run_one(
    amc: str,
    portfolios: Path,
    run_date: date,
    limit: int | None
    ) -> str:

    """Clear one AMC's folder, download its latest files and return a one-line report."""

    folder = portfolios / amc
    folder.mkdir(parents=True, exist_ok=True)

    for old in folder.iterdir():

        if old.suffix.lower() in EXCEL_SUFFIXES:
            old.unlink()

    try:
        with client() as http:
            saved = FETCHERS[amc](http, folder, run_date, limit)

    except Exception as exc:
        return f"FAILED   {amc:<8} {type(exc).__name__}: {exc}"

    if not saved:
        return f"MISSING  {amc:<8} no monthly portfolio found"

    return f"OK       {amc:<8} {len(saved)} file(s), e.g. {saved[0]}"


def main() -> None:

    """Download the chosen AMCs, a few AMCs at a time, each AMC's files one after another."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=date.fromisoformat, default=date.today())
    parser.add_argument("--amc", choices=list(FETCHERS), default=None)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    portfolios = source_dir(args.date) / "portfolios"
    amcs = [args.amc] if args.amc else list(FETCHERS)

    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_AMCS) as pool:
        reports = list(pool.map(lambda amc: run_one(amc, portfolios, args.date, args.limit), amcs))

    print(f"Portfolios folder: {portfolios}")

    for report in reports:
        print("  ", report)

    for amc, reason in BLOCKED_AMCS.items():
        print(f"   SKIPPED  {amc:<8} {reason}")


if __name__ == "__main__":
    main()
