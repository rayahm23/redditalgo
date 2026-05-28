from scanner.pipeline import _should_keep_previous_results


def test_keep_previous_when_fetch_too_small():
    assert _should_keep_previous_results(
        posts=[],
        aggregates={},
        results=[],
        previous=[{"ticker": "NVDA"}],
    )


def test_keep_previous_when_many_posts_but_no_aggregates():
    assert _should_keep_previous_results(
        posts=[{"id": "1"}] * 10,
        aggregates={},
        results=[],
        previous=[{"ticker": "NVDA"}],
    )


def test_do_not_keep_previous_when_aggregates_exist_but_all_excluded():
    assert not _should_keep_previous_results(
        posts=[{"id": "1"}] * 10,
        aggregates={"FAQ": object()},
        results=[],
        previous=[{"ticker": "NVDA"}],
    )
