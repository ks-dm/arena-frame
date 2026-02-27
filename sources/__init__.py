"""Content source abstraction for Arena Frame."""

from abc import ABC, abstractmethod


class ContentSource(ABC):
    """Base class for content sources."""

    @abstractmethod
    def fetch(self, state):
        """Fetch next content to display.

        Returns (content_path, error_code) tuple.
        content_path is a string path to the downloaded file, or None.
        error_code is one of the error constants from config.
        """
        ...
