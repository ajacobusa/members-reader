"""Family registry (audit #6): a single source of truth for non-wall-art families so a
new product is ONE entry instead of edits across both ingest seams + the render if/elif.
"""


def test_registry_covers_the_four_families():
    from quoteforge.etsy.families import FAMILIES, family_for, enrichers, WALLART_TYPES
    assert {f.product_type for f in FAMILIES} == {"apparel", "mug", "calendar", "branded"}
    assert len(enrichers()) == 4
    assert family_for("mug").product_type == "mug"
    assert family_for("PRINT") is None and family_for("") is None   # wall art / unknown
    assert "" in WALLART_TYPES and "poster" in WALLART_TYPES


def test_enrichers_are_noop_for_wall_art():
    # Running every enricher on a wall-art order must not tag it as another family.
    from quoteforge.etsy.families import enrichers
    data = {"material": "Poster (unframed print)", "product_size": "8x10"}
    for e in enrichers():
        data.update(e(data))
    assert data.get("product_type") not in ("apparel", "mug", "calendar", "branded")


def test_render_size_resolves_via_registry():
    from quoteforge.etsy.families import family_for
    rs = family_for("mug").render_size({"product_id": ""}, "11oz")
    assert isinstance(rs, tuple) and len(rs) == 2 and all(isinstance(x, int) for x in rs)
    ps = family_for("apparel").photo_size({"garment_id": ""}, "M")
    assert ps == "12x16 in"


def test_both_ingest_seams_use_the_registry():
    # Guard against the duplication regressing: neither seam may re-introduce a
    # hand-written enrich chain (they must import the registry).
    import inspect
    from quoteforge.automation import webhook_server, pipeline_orchestrator
    for mod in (webhook_server, pipeline_orchestrator):
        src = inspect.getsource(mod)
        assert "from quoteforge.etsy.families import enrichers" in src
