from ee.hogai.utils.tts_text import prepare_text_for_elevenlabs_tts


def test_expands_api_and_https():
    assert "application programming interface" in prepare_text_for_elevenlabs_tts("Use the API")
    assert "hypertext transfer protocol" in prepare_text_for_elevenlabs_tts("HTTP and HTTPS")


def test_latin_abbreviations_with_period_before_space():
    assert "for example" in prepare_text_for_elevenlabs_tts("e.g. something")
    assert "that is" in prepare_text_for_elevenlabs_tts("i.e. other")


def test_ci_cd_before_ci_alone():
    out = prepare_text_for_elevenlabs_tts("CI/CD pipeline and CI only")
    assert "continuous integration and continuous delivery" in out
    assert "continuous integration only" in out
