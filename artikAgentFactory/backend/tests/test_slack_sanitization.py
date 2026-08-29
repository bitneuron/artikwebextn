from app.services.pipeline.slack_sanitize import sanitize_for_slack


def test_bare_channel_mention_defused():
    out = sanitize_for_slack("urgent @channel please respond")
    assert "@channel" not in out
    assert "channel" in out  # word survives, just not as a live mention


def test_bare_here_and_everyone_defused():
    out = sanitize_for_slack("cc @here and @everyone")
    assert "@here" not in out
    assert "@everyone" not in out


def test_bracket_channel_syntax_escaped():
    out = sanitize_for_slack("click <!channel> now")
    assert "<!channel>" not in out
    assert "&lt;!channel&gt;" in out


def test_bracket_user_mention_escaped():
    out = sanitize_for_slack("ping <@U0123456> immediately")
    assert "<@U0123456>" not in out


def test_empty_and_none_handled_safely():
    assert sanitize_for_slack(None) == ""
    assert sanitize_for_slack("") == ""


def test_normal_text_passes_through_mostly_unchanged():
    out = sanitize_for_slack("Found 3 new colleges matching the criteria.")
    assert "Found 3 new colleges matching the criteria." in out
