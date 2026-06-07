"""Test the end-to-end workflow PDF generator."""


def test_workflow_pdf_builds(tmp_path):
    from quoteforge.etsy.workflow_doc import build_workflow_pdf, STAGES
    out = build_workflow_pdf(out_path=tmp_path / "wf.pdf")
    assert out.exists()
    data = out.read_bytes()
    assert data[:5] == b"%PDF-" and len(data) > 3000
    # the journey covers entry -> delivery (>=15 stages)
    assert len(STAGES) >= 15


def test_workflow_command_registered():
    from quoteforge import admin
    assert "workflow-pdf" in admin.COMMANDS
