"""Cloudflare R2 storage service with singleton pattern."""
import logging
from typing import Optional
from datetime import datetime, timedelta
import boto3
from botocore.client import Config

from app.config import get_settings

logger = logging.getLogger(__name__)

_storage_instance: Optional["StorageService"] = None


class StorageService:
    """Singleton service for Cloudflare R2 storage."""

    def __init__(self):
        settings = get_settings()

        # Check if R2 is configured
        if not all([
            settings.r2_account_id,
            settings.r2_access_key_id,
            settings.r2_secret_access_key
        ]):
            logger.warning("R2 credentials not fully configured - storage service disabled")
            self.enabled = False
            self.client = None
            self.bucket_name = None
            return

        self.enabled = True
        self.bucket_name = settings.r2_bucket_name

        # Configure boto3 for R2
        endpoint_url = f"https://{settings.r2_account_id}.r2.cloudflarestorage.com"

        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=settings.r2_access_key_id,
            aws_secret_access_key=settings.r2_secret_access_key,
            config=Config(signature_version="s3v4"),
            region_name="auto"
        )

        logger.info(f"R2 storage initialized: bucket={self.bucket_name}")

    def upload_document(
        self,
        file_bytes: bytes,
        filename: str,
        document_type: str,
        category: Optional[str] = None,
        date: Optional[datetime] = None
    ) -> Optional[str]:
        """
        Upload a document to R2 storage.

        Args:
            file_bytes: The file content
            filename: Original filename
            document_type: Type of document (invoice, receipt, etc.)
            category: Optional category for organization
            date: Optional date for organization (defaults to now)

        Returns:
            R2 object key if successful, None if disabled or error
        """
        if not self.enabled:
            return None

        try:
            # Use current date if not provided
            if date is None:
                date = datetime.now()

            # Build organized key: {category}/{year}/{date}_{document_type}_{original_filename}
            year = date.strftime("%Y")
            date_str = date.strftime("%Y-%m-%d")
            category_prefix = category if category else "uncategorized"

            # Sanitize filename (remove spaces, special chars)
            safe_filename = filename.replace(" ", "_")

            key = f"{category_prefix}/{year}/{date_str}_{document_type}_{safe_filename}"

            # Upload to R2
            self.client.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=file_bytes,
                ContentType=self._get_content_type(filename)
            )

            logger.info(f"Uploaded to R2: {key} ({len(file_bytes)} bytes)")
            return key

        except Exception as e:
            logger.error(f"R2 upload failed: {e}")
            return None

    def get_presigned_url(self, key: str, expires_in: int = 3600) -> Optional[str]:
        """
        Generate a presigned download URL for an R2 object.

        Args:
            key: R2 object key
            expires_in: URL validity in seconds (default: 1 hour)

        Returns:
            Presigned URL if successful, None if disabled or error
        """
        if not self.enabled:
            return None

        try:
            url = self.client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": key},
                ExpiresIn=expires_in
            )
            logger.info(f"Generated presigned URL for: {key}")
            return url

        except Exception as e:
            logger.error(f"Failed to generate presigned URL for {key}: {e}")
            return None

    def download_file(self, key: str) -> Optional[bytes]:
        """
        Download a file from R2 storage.

        Args:
            key: R2 object key

        Returns:
            File bytes if successful, None if disabled or error
        """
        if not self.enabled:
            return None

        try:
            response = self.client.get_object(Bucket=self.bucket_name, Key=key)
            file_bytes = response["Body"].read()
            logger.info(f"Downloaded from R2: {key} ({len(file_bytes)} bytes)")
            return file_bytes

        except Exception as e:
            logger.error(f"R2 download failed for {key}: {e}")
            return None

    def _get_content_type(self, filename: str) -> str:
        """Detect content type from filename extension."""
        filename_lower = filename.lower()

        if filename_lower.endswith(".pdf"):
            return "application/pdf"
        elif filename_lower.endswith((".jpg", ".jpeg")):
            return "image/jpeg"
        elif filename_lower.endswith(".png"):
            return "image/png"
        elif filename_lower.endswith(".webp"):
            return "image/webp"
        elif filename_lower.endswith(".gif"):
            return "image/gif"
        else:
            return "application/octet-stream"


def get_storage() -> StorageService:
    """Get or create the singleton StorageService instance."""
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = StorageService()
    return _storage_instance
