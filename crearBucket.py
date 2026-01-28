import boto3
from botocore.exceptions import ClientError
import pandas as pd
from TradingviewData import TradingViewData, Interval

request = TradingViewData()

s3 = boto3.client("s3", region_name="eu-south-2")


def delete_bucket_if_exists(bucket_name: str):
    try:
        # Comprobamos si el bucket existe
        s3.head_bucket(Bucket=bucket_name)
        print(f"El bucket {bucket_name} existe. Borrándolo...")

        # Listar y borrar objetos
        response = s3.list_objects_v2(Bucket=bucket_name)
        if "Contents" in response:
            objects = [{"Key": obj["Key"]} for obj in response["Contents"]]
            s3.delete_objects(
                Bucket=bucket_name,
                Delete={"Objects": objects}
            )

        # Borrar el bucket
        s3.delete_bucket(Bucket=bucket_name)
        print(f"Bucket eliminado: {bucket_name}")

    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code == "404":
            print(f"El bucket {bucket_name} no existe. Continuamos...")
        else:
            print(f"Error borrando bucket {bucket_name}: {e}")
            raise


def create_bucket(bucket_name: str, region: str = "eu-west-1"):
    try:
        if region == "us-east-1":
            s3.create_bucket(Bucket=bucket_name)
        else:
            s3.create_bucket(
                Bucket=bucket_name,
                CreateBucketConfiguration={"LocationConstraint": region},
            )

        print(f"Bucket creado: {bucket_name} ({region})")
        return True

    except ClientError as e:
        print(f"Error creando bucket: {e}")
        return False


def upload_file(file_name: str, bucket_name: str):
    s3.upload_file(file_name, bucket_name, file_name)
    print(f"Archivo {file_name} subido a {bucket_name}")


# -------------------------
# DATA
# -------------------------
avax_data = request.get_hist(
    symbol="AVAXUSD",
    exchange="Binance",
    interval=Interval.daily,
    n_bars=1461
)

avax_data["year"] = avax_data.index.year

for i in range(1, 6):
    year = 2021 + i
    bucket_name = f"avax{year}bigtech"
    avax_year = avax_data[avax_data["year"] == year]
    avax_year.drop(columns=["year"], inplace=True)
    file_name = f"avax_{year}.csv"
    avax_year.to_csv(file_name)

    delete_bucket_if_exists(bucket_name)

    create_bucket(bucket_name, region="eu-south-2")
    upload_file(file_name=file_name, bucket_name=bucket_name)
