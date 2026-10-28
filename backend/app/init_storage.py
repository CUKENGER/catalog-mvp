import json
import os
import time

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError


bucket = os.environ["S3_BUCKET"]

s3 = boto3.client(
    "s3",
    endpoint_url=os.environ["S3_ENDPOINT_URL"],
    aws_access_key_id=os.environ["S3_ACCESS_KEY"],
    aws_secret_access_key=os.environ["S3_SECRET_KEY"],
    region_name="us-east-1",
    config=Config(signature_version="s3v4"),
)

public_read_policy = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": "*",
            "Action": ["s3:GetObject"],
            "Resource": [f"arn:aws:s3:::{bucket}/*"],
        }
    ],
}


def main() -> None:
    for attempt in range(30):
        try:
            try:
                s3.head_bucket(Bucket=bucket)
            except ClientError as error:
                error_code = error.response.get("Error", {}).get("Code")
                status_code = error.response.get("ResponseMetadata", {}).get(
                    "HTTPStatusCode"
                )

                if (
                    error_code not in {"404", "NoSuchBucket", "NotFound"}
                    and status_code != 404
                ):
                    raise

                s3.create_bucket(Bucket=bucket)

            s3.put_bucket_policy(
                Bucket=bucket,
                Policy=json.dumps(public_read_policy),
            )
            print(f"Bucket {bucket!r} is ready")
            return

        except (BotoCoreError, ClientError) as error:
            if attempt == 29:
                raise

            print(f"Waiting for object storage ({attempt + 1}/30): {error}")
            time.sleep(2)


if __name__ == "__main__":
    main()
