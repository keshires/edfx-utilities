from datetime import date
import pd_precheck as p

REF = date(2026, 7, 1)


# ---- classify_status (private/custom, after pds + mapping) ----

def test_status_orphaned_skips():
    c = p.classify_status("private", p.EntityStatus(pd=None, orphaned=True), REF)
    assert (c.category, c.action) == ("orphaned", "SKIP")


def test_status_mapped_no_pd_skips():
    c = p.classify_status("private", p.EntityStatus(pd=None, orphaned=False), REF)
    assert (c.category, c.action) == ("mapped_no_pd", "SKIP")


def test_status_no_pd_bankrupt_skips():
    st = p.EntityStatus(pd=p.PdResult(date(2026, 7, 1), False, "bankrupt"), orphaned=False)
    assert p.classify_status("private", st, REF).action == "SKIP"


def test_status_private_current_posts():
    st = p.EntityStatus(pd=p.PdResult(date(2026, 7, 1), True), orphaned=False)
    c = p.classify_status("private", st, REF)
    assert (c.category, c.action) == ("current_pd", "POST")


def test_status_private_source_stale_skips():
    st = p.EntityStatus(pd=p.PdResult(date(2019, 1, 1), True), orphaned=False)
    assert p.classify_status("private", st, REF).category == "source_stale"


def test_status_custom_haspd_posts_regardless_of_asofdate():
    # custom asOfDate is the financials date, not the publication date -> pd presence is the signal
    st = p.EntityStatus(pd=p.PdResult(date(2020, 5, 1), True), orphaned=False)
    c = p.classify_status("custom", st, REF)
    assert (c.category, c.action) == ("refreshable", "POST")


# ---- classify_public (DB-only) ----

def test_public_fresh_when_current_and_active():
    c = p.classify_public(date(2026, 7, 10), "Active", REF)
    assert (c.category, c.action) == ("public_fresh", "SKIP")


def test_public_fresh_when_status_null():
    c = p.classify_public(date(2026, 7, 1), None, REF)
    assert c.category == "public_fresh"


def test_public_stale_when_old_pd():
    c = p.classify_public(date(2026, 6, 1), "Active", REF)
    assert c.category == "public_stale"


def test_public_invalid_status():
    c = p.classify_public(date(2026, 7, 1), "Bankruptcy", REF)
    assert c.category == "public_invalid_status"


# ---- PdMappingResolver (pds -> mapping fallback) ----

def test_resolver_pds_found_mapping_orphan():
    rows = [
        p.StaleRow("HASPD", "t", None, None, False),
        p.StaleRow("NODATA_ORPH", "t", None, None, False),
        p.StaleRow("NODATA_MAPPED", "t", None, None, False),
    ]

    def pds_post(ids):
        out = []
        for i in ids:
            if i == "HASPD":
                out.append({"entityId": i, "asOfDate": "2026-07-01", "pd": 0.01})
            else:
                out.append({"entityId": i, "message": "No data found"})
        return out

    def mapping_lookup(external_ids, tenant_id=None):
        return {e for e in external_ids if e == "NODATA_MAPPED"}  # only this one maps

    resolver = p.PdMappingResolver(pds_post, mapping_lookup, batch_size=10)
    out = resolver.resolve(rows, "private")
    assert out["HASPD"].pd.has_pd is True and out["HASPD"].orphaned is False
    assert out["NODATA_ORPH"].orphaned is True
    assert out["NODATA_MAPPED"].orphaned is False and out["NODATA_MAPPED"].pd is None
