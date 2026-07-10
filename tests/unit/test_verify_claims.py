"""Tests for agent-claim extraction."""

from cngx.verify.claims import extract_claim


def test_empty_is_no_claim():
    c = extract_claim("")
    assert c.claims_success is False
    assert c.has_claim is False


def test_all_tests_pass_claim():
    c = extract_claim("I fixed it and all tests pass. Ready to merge.")
    assert c.claims_success is True
    assert "all tests pass" in c.markers
    assert "ready to merge" in c.markers


def test_passed_count_is_success_claim():
    c = extract_claim("Done. 12 passed.")
    assert c.claims_success is True
    assert c.claimed_passed == 12


def test_admitted_failures_not_success():
    c = extract_claim("9 passed, 3 failed. Still debugging.")
    assert c.claimed_passed == 9
    assert c.claimed_failed == 3
    assert c.claims_success is False


def test_plain_done_is_not_a_claim():
    # "done" alone is too weak to be a verification claim.
    c = extract_claim("Done with the refactor.")
    assert c.claims_success is False
    assert c.has_claim is False


def test_lgtm_and_ship_it():
    assert extract_claim("LGTM").claims_success is True
    assert extract_claim("ship it").claims_success is True


def test_no_failures_marker():
    c = extract_claim("The fix works, no failures.")
    assert c.claims_success is True
    assert c.claimed_no_failures is True


def test_markers_deduped():
    c = extract_claim("all tests pass. all tests pass again.")
    assert c.markers.count("all tests pass") == 1
