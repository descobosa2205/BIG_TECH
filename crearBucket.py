import boto3
from botocore.exceptions import ClientError

def create_bucket(bucket_name: str, region: str = "eu-west-1"):
    s3 = boto3.client("s3", region_name=region)

    try:
        if region == "us-east-1":
            # En us-east-1 NO hace falta LocationConstraint
            s3.create_bucket(Bucket=bucket_name)
        else:
            s3.create_bucket(
                Bucket=bucket_name,
                CreateBucketConfiguration={"LocationConstraint": region},
            )

        print(f"✅ Bucket creado: {bucket_name} ({region})")
        return True

    except ClientError as e:
        print(f"❌ Error creando bucket: {e}")
        return False

create_bucket("avax2022bigtech", region="eu-south-2")