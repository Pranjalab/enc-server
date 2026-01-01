from abc import ABC, abstractmethod

class BaseHandler(ABC):
    def __init__(self, config: dict = None):
        self.config = config or {}

    @abstractmethod
    def verify(self) -> bool:
        """Verify if the backup destination is accessible."""
        pass

    @abstractmethod
    def push(self, source_file: str) -> bool:
        """Upload source_file to backup destination."""
        pass

    @abstractmethod
    def pull(self, dest_file: str) -> bool:
        """Download backup to dest_file."""
        pass
