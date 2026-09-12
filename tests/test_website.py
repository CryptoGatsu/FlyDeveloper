from fly.mind import OfflineMind, ProjectFile
from fly.website import ROUTES, build_website, install_site, site_exists, template_files, validate_site


def test_template_validates_and_installs(tmp_path):
    files = template_files()
    assert validate_site(files) == []
    site = tmp_path / "site"
    (site / "data").mkdir(parents=True); (site / "data" / "state.json").write_text("{}")
    (site / "memes").mkdir(); (site / "memes" / "x.png").write_bytes(b"png")
    (site / "old.html").write_text("stale")
    written = install_site(site, files)
    for route, _ in ROUTES:
        assert (site / (f"{route}/index.html" if route else "index.html")).is_file()
    assert (site / "data" / "state.json").is_file() and (site / "memes" / "x.png").is_file()
    assert not (site / "old.html").exists()
    assert site_exists(site) and "app.js" in written


def test_validate_rejects_hash_and_html_links():
    files = [f for f in template_files()]
    bad = [ProjectFile(path=f.path, content=f.content.replace('href="/"', 'href="#now"').replace('href="/style.css"', 'href="style.html"'))
           if f.path == "index.html" else f for f in files]
    problems = validate_site(bad)
    assert any("#now" in p for p in problems)
    assert any(".html" in p for p in problems) or any("must load" in p for p in problems)
    missing = [f for f in files if f.path != "coins/index.html"]
    assert any("coins/index.html" in p for p in validate_site(missing))


class BrokenMind(OfflineMind):
    def website(self, brief, context):
        from fly.mind import WebsiteFiles
        return WebsiteFiles(notes="oops", files=[ProjectFile(path="index.html", content="<a href='#x'>x</a>")])


def test_build_falls_back_to_template(tmp_path):
    res = build_website(BrokenMind(), tmp_path / "site", log=lambda s: None, visual_qa=False)
    assert res.source == "template" and res.problems
    assert site_exists(tmp_path / "site")
    res2 = build_website(OfflineMind(), tmp_path / "site2", log=lambda s: None, visual_qa=False)
    assert res2.source == "mind" and not res2.problems


def test_validate_rejects_literal_unicode_escapes():
    files = [ProjectFile(path=f.path, content=f.content.replace("</footer>", "a \\u00b7 b</footer>")) if f.path == "index.html" else f
             for f in template_files()]
    assert any("escape" in p for p in validate_site(files))


def test_screenshots_when_chrome_available(tmp_path):
    from fly.render import find_chrome, screenshot_site
    site = tmp_path / "site"
    install_site(site, template_files())
    if not find_chrome():
        return
    shots = screenshot_site(site, tmp_path / "shots", routes=("",))
    assert len(shots) == 2
    from fly.render import edge_overflow
    phone = [s for s in shots if "phone" in s.name][0]
    assert edge_overflow(phone) < 0.12          # the template fits a 400px screen


def test_refine_reloads_existing_site(tmp_path):
    from fly.website import load_site_files
    site = tmp_path / "site"
    install_site(site, template_files())
    (site / "data").mkdir(); (site / "data" / "state.json").write_text("{}")
    files = load_site_files(site)
    assert {f.path for f in files} == {f.path for f in template_files()}
    res = build_website(OfflineMind(), site, log=lambda s: None, visual_qa=False, refine=True)
    assert res.source == "refined" and site_exists(site)


def test_head_tags_injected_and_kept_on_install(tmp_path):
    from fly.website import ensure_head_tags
    html = "<html><head><title>x</title></head><body data-route=''><script src='/app.js'></script></body></html>"
    fixed = ensure_head_tags(html)
    assert '/favicon.png' in fixed and '/apple-touch-icon.png' in fixed and 'upgrade-insecure-requests' in fixed
    assert ensure_head_tags(fixed) == fixed
    site = tmp_path / "site"
    site.mkdir(); (site / "favicon.png").write_bytes(b"x")
    install_site(site, template_files())
    assert (site / "favicon.png").read_bytes() == b"x" and (site / "robots.txt").is_file()


def test_install_keeps_browsing_shots(tmp_path):
    site = tmp_path / "site"
    install_site(site, template_files())
    (site / "browsing" / "shots").mkdir(parents=True)
    (site / "browsing" / "shots" / "a.jpg").write_bytes(b"jpg")
    install_site(site, template_files())
    assert (site / "browsing" / "shots" / "a.jpg").is_file() and (site / "browsing" / "index.html").is_file()


def test_screenshot_url_when_chrome_available(tmp_path):
    from fly.render import find_chrome, screenshot_url
    if not find_chrome():
        return
    page = tmp_path / "p.html"; page.write_text("<html><body style='background:#123'><h1>hello fly</h1></body></html>")
    out = screenshot_url(page.as_uri(), tmp_path / "shot.jpg", stamp="seen by the fly · test · file")
    assert out and out.stat().st_size > 1000
    from PIL import Image
    assert Image.open(out).width <= 720


def test_house_panels_injected_once():
    from fly.website import ensure_house_panels
    html = "<html><head></head><body><main><h1>x</h1></main></body></html>"
    out = ensure_house_panels(html, "index.html")
    assert 'id="flybrain"' in out and '/brain.js' in out
    assert 'id="flycoin"' in out and '/coin.js' in out
    assert ensure_house_panels(out, "index.html") == out                 # idempotent
    other = ensure_house_panels(html, "memes/index.html")
    assert 'id="flybrain"' not in other and '/brain.js' not in other      # brain only on the home page
    assert 'id="flycoin"' in other and '/coin.js' in other                # coin strip everywhere


def test_refine_keeps_site_when_mind_fails(tmp_path):
    class DeadMind(OfflineMind):
        def website(self, brief, context):
            raise RuntimeError("credit balance is too low")
        def revise_website(self, brief, files, problems, screenshots):
            raise RuntimeError("credit balance is too low")

    site = tmp_path / "site"
    install_site(site, template_files())
    (site / "index.html").write_text((site / "index.html").read_text().replace("The Fly Dev", "MY OWN DESIGN"))
    res = build_website(DeadMind(), site, log=lambda s: None, visual_qa=False, refine=True, changes=["add a thing"])
    assert res.source == "kept"
    assert "MY OWN DESIGN" in (site / "index.html").read_text()
