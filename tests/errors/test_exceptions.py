from whrb_archive.errors import ArchiveError, DownloadError, ScheduleError


def test_error_hierarchy():
    assert issubclass(ScheduleError, ArchiveError)
    assert issubclass(DownloadError, ArchiveError)


def test_error_instances():
    message = "failure"
    try:
        raise ScheduleError(message)
    except ScheduleError as exc:
        assert isinstance(exc, ArchiveError)
        assert str(exc) == message
