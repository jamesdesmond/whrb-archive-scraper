"""Exception hierarchy for archive operations."""


class ArchiveError(Exception):
    """Base exception for archive errors."""


class ScheduleError(ArchiveError):
    """Raised when schedule data cannot be retrieved or parsed."""


class DownloadError(ArchiveError):
    """Raised when segment or playlist downloads fail."""
