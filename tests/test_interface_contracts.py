"""Contract validation tests; run with python -m unittest discover -s tests."""
import unittest
from datetime import date
from pydantic import ValidationError

from backend.contracts.models import (
    DocumentMetadata,
    DocumentPackage,
    ParsedChunk,
    ParsedFile,
    RetrievalStatus,
    SourceVerificationStatus,
    TimelinessVerificationStatus,
    InclusionStatus,
)


class InterfaceContractTests(unittest.TestCase):
    def test_document_metadata_defaults_to_blocked(self):
        metadata = DocumentMetadata(
            title="示例文件", document_type="办法",
            category_name="综评与奖学金", record_code="TEST-001",
            version_no="import-1", source_url="https://example.edu.cn/policy",
        )
        self.assertEqual(metadata.retrieval_status, RetrievalStatus.BLOCKED)

    def test_enabled_retrieval_requires_review_prerequisites(self):
        with self.assertRaises(ValidationError):
            DocumentMetadata(
                title="示例文件", document_type="办法",
                category_name="综评与奖学金", record_code="TEST-002",
                version_no="import-1", source_url="https://example.edu.cn/policy",
                retrieval_status=RetrievalStatus.ENABLED,
            )

    def test_enabled_retrieval_accepts_verified_metadata(self):
        metadata = DocumentMetadata(
            title="示例文件", document_type="办法",
            category_name="综评与奖学金", record_code="TEST-003",
            version_no="v1", source_url="https://example.edu.cn/policy",
            v1_inclusion_status=InclusionStatus.INCLUDED,
            source_verification_status=SourceVerificationStatus.VERIFIED,
            extraction_status="extracted",
            timeliness_verification_status=TimelinessVerificationStatus.CURRENT,
            retrieval_status=RetrievalStatus.ENABLED,
        )
        self.assertEqual(metadata.retrieval_status, RetrievalStatus.ENABLED)

    def test_document_package_rejects_unknown_chunk_file(self):
        with self.assertRaises(ValidationError):
            DocumentPackage(
                metadata=DocumentMetadata(
                    title="示例文件", document_type="办法",
                    category_name="综评与奖学金", record_code="TEST-004",
                    version_no="import-1", source_url="https://example.edu.cn/policy",
                ),
                files=[ParsedFile(
                    file_role="original", storage_key="official/test.pdf",
                    original_name="test.pdf",
                )],
                chunks=[ParsedChunk(
                    chunk_no=1, content="示例正文",
                    source_file_key="missing/test.pdf",
                )],
            )

    def test_contract_models_serialize_dates(self):
        metadata = DocumentMetadata(
            title="示例文件", document_type="办法",
            category_name="综评与奖学金", record_code="TEST-005",
            version_no="v1", source_url="https://example.edu.cn/policy",
            published_on=date(2026, 6, 1),
        )
        self.assertEqual(metadata.model_dump(mode="json")["published_on"], "2026-06-01")


if __name__ == "__main__":
    unittest.main()
