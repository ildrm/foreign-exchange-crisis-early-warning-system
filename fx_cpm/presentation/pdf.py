"""Optional, deterministic Playwright PDF export for installed FX-CPM packages."""

from __future__ import annotations

from pathlib import Path


def export_pdf(html_path: Path, pdf_path: Path) -> None:
    """Render a self-contained HTML report to an A4-landscape PDF."""

    if not html_path.is_file():
        raise FileNotFoundError(f"HTML report does not exist: {html_path}")
    if html_path.suffix.lower() not in {".html", ".htm"}:
        raise ValueError("input must be an HTML file")
    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError("output must have a .pdf extension")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "PDF support is optional. Install it with `python -m pip install 'fx-cpm[pdf]'` "
            "and then run `python -m playwright install chromium`."
        ) from exc

    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            page.emulate_media(media="print", color_scheme="dark")
            page.goto(html_path.resolve().as_uri(), wait_until="networkidle")
            page.evaluate(
                """() => {
                    document.documentElement.dataset.printMode = 'true';
                    document.documentElement.classList.add('print-mode');
                    document.querySelectorAll('[open-on-print]').forEach((node) => {
                        node.open = true;
                    });
                    window.dispatchEvent(new Event('fx-cpm-print'));
                }"""
            )
            page.wait_for_function("document.fonts ? document.fonts.status === 'loaded' : true")
            page.pdf(
                path=str(pdf_path.resolve()),
                landscape=True,
                print_background=True,
                prefer_css_page_size=True,
            )
        finally:
            browser.close()


__all__ = ["export_pdf"]
