from contextguardrail.budget import estimate_tokens


def test_estimate_tokens_returns_positive_count():
    assert estimate_tokens("hello world") > 0
