from whrb_archive.services.calendar_service import extract_calendar_ical_url


def test_extract_calendar_ical_url_no_iframe():
    assert extract_calendar_ical_url("<html></html>") is None


def test_extract_calendar_ical_url_no_src():
    assert extract_calendar_ical_url("<iframe></iframe>") is None


def test_extract_calendar_ical_url_non_google():
    html = '<iframe src="https://example.com/calendar"></iframe>'
    assert extract_calendar_ical_url(html) is None
