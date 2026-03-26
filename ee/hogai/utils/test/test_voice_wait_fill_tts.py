from ee.hogai.utils.voice_wait_fill_tts import _fallback_lines, _validate_lines


def test_fallback_lines_single():
    out = _fallback_lines(["x"])
    assert len(out) == 1
    assert "x" in out[0]
    assert "let me share this with you" in out[0]


def test_fallback_lines_two():
    out = _fallback_lines(["a", "b"])
    assert len(out) == 2
    assert "a" in out[0]
    assert "b" in out[1]


def test_validate_lines_requires_verbatim_tweet():
    tweets = ["hello world"]
    assert _validate_lines(tweets, ["prefix hello world"]) == ["prefix hello world"]
    assert _validate_lines(tweets, ["missing"]) is None
    assert _validate_lines(tweets, []) is None
