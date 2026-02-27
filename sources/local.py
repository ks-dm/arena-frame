"""Local folder content source (future implementation)."""

from sources import ContentSource
from config import ERROR_NONE


class LocalSource(ContentSource):
    """Displays images from a local directory."""

    def __init__(self, directory):
        self.directory = directory

    def fetch(self, state=None):
        raise NotImplementedError("Local source not yet implemented")
