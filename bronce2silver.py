from pyspark.sql import SparkSession
from pyspark.sql.functions import col, trim, lower, to_date, when, to_timestamp, regexp_replace, from_unixtime
import boto3
from pyspark.sql.types import StructType, StructField, StringType, DoubleType, TimestampType
from botocore.exceptions import ClientError
from awsglue.context import GlueContext
from pyspark.context import SparkContext

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

if __name__ == "__main__":
    s3 = boto3.client("s3", region_name="eu-south-2")
    bucket_bronce = "bronceimat3a03"
    bucket_plata = "plataimat3a03"
    delete_bucket_if_exists(bucket_plata)
    create_bucket(bucket_name=bucket_plata, region="eu-south-2")
    spark = SparkSession.builder \
        .appName("BronceToPlata_Transformation") \
        .getOrCreate()
    
    glueContext = GlueContext(SparkContext.getOrCreate())

    dynamic_frame = glueContext.create_dynamic_frame.from_catalog(
        database="trade_data_imat3a03",
        table_name="bucketcryptoimat3a03"
    )
    df_plata = dynamic_frame.toDF()
    
    path_plata = "s3://plataimat3a03/data"
    
    schema = StructType([
    StructField("datetime", TimestampType(), True),
    StructField("symbol", StringType(), True),
    StructField("open", DoubleType(), True),
    StructField("high", DoubleType(), True),
    StructField("low", DoubleType(), True),
    StructField("close", DoubleType(), True),
    StructField("volume", DoubleType(), True)])

    for field in schema.fields:
        df_plata = df_plata.withColumn(field.name, col(field.name).cast(field.dataType))

    df_plata.write.mode("overwrite") \
        .partitionBy("crypto", "year", "month") \
        .parquet(path_plata)