"""The Inspector's pages carry NMOS's icon inline (a data URI), so the tab shows it at any address."""

from urllib.parse import unquote

from nmos_sidecar import inspector


def test_every_page_has_the_icon_inline():
    html = inspector.page("NMOS", "<p>x</p>")
    assert '<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,' in html
    assert "#" not in inspector.FAVICON  # a raw '#' would end the data URI at a fragment
    svg = unquote(inspector.FAVICON.split(",", 1)[1])
    assert svg.startswith("<svg") and 'd="M6 19V5l12 14V9.5"' in svg and "prefers-color-scheme:dark" in svg
