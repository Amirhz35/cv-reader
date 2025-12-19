import logging
from abc import ABC, abstractmethod
from typing import Optional
import fitz
from pdfminer.high_level import extract_text

logger = logging.getLogger(__name__)


class CVParser(ABC):
    @abstractmethod
    def extract_text(self, file_path: str) -> Optional[str]:
        pass


class PDFMinerParser(CVParser):
    def extract_text(self, file_path: str) -> Optional[str]:
        try:
            return extract_text(file_path)
        except Exception as e:
            logger.error(f"Error extracting text with pdfminer: {e}")
            return None


class PyMuPDFParser(CVParser):
    def extract_text(self, file_path: str) -> Optional[str]:
        try:
            doc = fitz.open(file_path)
            text = ""
            for page in doc:
                text += page.get_text()
            doc.close()
            return text
        except Exception as e:
            logger.error(f"Error extracting text with PyMuPDF: {e}")
            return None


class CVParserService:
    def __init__(self):
        self.parsers = [PDFMinerParser(), PyMuPDFParser()]

    def extract_text(self, file_path: str) -> Optional[str]:
        for parser in self.parsers:
            text = parser.extract_text(file_path)
            if text and text.strip():
                return text.strip()

        logger.error(f"Failed to extract text from {file_path}")
        return None
