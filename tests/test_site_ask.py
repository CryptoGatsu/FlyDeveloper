from fly.website import install_site, template_files


def test_ask_page_survives_redesign(tmp_path):
    site = tmp_path / "site"
    (site / "ask").mkdir(parents=True)
    (site / "ask" / "index.html").write_text("<html>ask</html>")
    (site / "ask.js").write_text("// ask")
    install_site(site, template_files())
    assert (site / "ask" / "index.html").read_text() == "<html>ask</html>"
    assert (site / "ask.js").read_text() == "// ask"
