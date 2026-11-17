"""Read-only document parsing; public DTOs live in backend.contracts."""

from .parser import DocumentProcessingError, TextDocumentParser

__all__ = ["DocumentProcessingError", "TextDocumentParser"]
