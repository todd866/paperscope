from paperscope.paper_site import PaperSiteConfig, scaffold_paper_site


def test_paper_site_scaffold_supports_optional_subtabs(tmp_path):
    out_dir = tmp_path / "paper-site"

    scaffold_paper_site(
        PaperSiteConfig(project_name="Example Paper Site", title="Example Paper Site", mode="medical"),
        out_dir,
    )

    page = (out_dir / "src/app/page.tsx").read_text()
    reader = (out_dir / "src/app/PaperReader.tsx").read_text()
    css = (out_dir / "src/app/globals.css").read_text()
    readme = (out_dir / "README.md").read_text()

    assert "src/content/sections.json" in page
    assert "type SectionRecord" in page
    assert "manuscriptPath" in page
    assert "sections={sections}" in page

    assert "export type PaperSection" in reader
    assert "normalizePaperSections" in reader
    assert "savedScrollBySection" in reader
    assert "paperMainRef" in reader
    assert "articleTop" in reader
    assert "window.scrollTo" in reader
    assert "switchSection(section.id)" in reader
    assert 'role="tablist"' in reader

    assert ".paper-section-tabs" in css
    assert ".paper-section-tab.active" in css

    assert "First visits open at the top" in readme
    assert "returning to a subtab restores its scroll" in readme


def test_paper_site_scaffold_marks_active_citations_without_selection_fill(tmp_path):
    out_dir = tmp_path / "paper-site"

    scaffold_paper_site(PaperSiteConfig(project_name="Example", title="Example"), out_dir)

    css = (out_dir / "src/app/globals.css").read_text()
    active_block = css.split(".cite-link:hover,", 1)[1].split(".detail-highlight", 1)[0]

    assert "background:" not in active_block
    assert "text-decoration-thickness: 2px" in active_block
