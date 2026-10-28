from urllib.parse import quote

import boto3
from botocore.client import Config

from app.config import settings


s3 = boto3.client(
    "s3",
    endpoint_url=settings.s3_endpoint_url,
    aws_access_key_id=settings.s3_access_key,
    aws_secret_access_key=settings.s3_secret_key,
    region_name="us-east-1",
    config=Config(signature_version="s3v4"),
)


def upload_image(key: str, content: bytes, content_type: str) -> None:
    s3.put_object(
        Bucket=settings.s3_bucket,
        Key=key,
        Body=content,
        ContentType=content_type,
        CacheControl="public, max-age=86400",
    )


def make_image_url(key: str) -> str:
    encoded_key = quote(key, safe="/")
    return (
        f"{settings.s3_public_base_url.rstrip('/')}"
        f"/{settings.s3_bucket}/{encoded_key}"
    )
