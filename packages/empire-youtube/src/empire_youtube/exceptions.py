"""Custom exceptions for empire_youtube."""


class EmpireYouTubeError(Exception):
    """Base exception for empire_youtube failures."""


class YouTubeConfigError(EmpireYouTubeError):
    """Raised when scraper configuration is missing or invalid."""


class YouTubeAPIError(EmpireYouTubeError):
    """Raised when the YouTube Data API returns an error response."""


class YouTubeResponseError(EmpireYouTubeError):
    """Raised when a YouTube API response is not shaped as expected."""
