import boto3
import pandas as pd
import io
import pyarrow as pa
import pyarrow.parquet as pq

REGION = "eu-south-2"
s3 = boto3.client("s3", region_name=REGION)

def list_csv_keys(bucket: str, prefix: str):
    """Lista todos los objetos .csv bajo un prefijo (con paginación)."""
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.lower().endswith(".csv") and not key.endswith("/"):
                yield key

def csv_key_to_parquet_key(csv_key: str, bronce_prefix: str, plata_prefix: str):
    """Convierte la key de bronce a la key destino en plata, manteniendo subcarpetas."""
    if not csv_key.startswith(bronce_prefix):
        raise ValueError(f"La key no empieza por el prefijo bronce: {csv_key}")
    relative = csv_key[len(bronce_prefix):]  # lo que cuelga del prefijo
    if relative.startswith("/"):
        relative = relative[1:]
    return f"{plata_prefix.rstrip('/')}/{relative[:-4]}.parquet"  # quita .csv

def convert_csv_s3_to_parquet_s3(
    bucket_bronce: str,
    bronce_prefix: str,
    bucket_plata: str,
    plata_prefix: str,
    csv_read_kwargs: dict | None = None,
):
    csv_read_kwargs = csv_read_kwargs or {"dtype_backend": "numpy_nullable"}  # opcional

    keys = list(list_csv_keys(bucket_bronce, bronce_prefix))
    if not keys:
        print(f"No se encontraron CSV en s3://{bucket_bronce}/{bronce_prefix}")
        return

    for csv_key in keys:
        parquet_key = csv_key_to_parquet_key(csv_key, bronce_prefix, plata_prefix)

        # 1) Descargar CSV
        obj = s3.get_object(Bucket=bucket_bronce, Key=csv_key)
        csv_bytes = obj["Body"].read()

        # 2) Leer CSV
        df = pd.read_csv(io.BytesIO(csv_bytes), **csv_read_kwargs)

        # 3) Convertir a Parquet (en memoria)
        table = pa.Table.from_pandas(df, preserve_index=False)
        out_buf = io.BytesIO()
        pq.write_table(table, out_buf, compression="snappy")  # snappy es estándar en data lakes
        out_buf.seek(0)

        # 4) Subir Parquet a S3
        s3.put_object(Bucket=bucket_plata, Key=parquet_key, Body=out_buf.getvalue())

        print(f"OK: s3://{bucket_bronce}/{csv_key} -> s3://{bucket_plata}/{parquet_key}")

if __name__ == "__main__":
    # Ajusta estos valores a tu estructura real:
    BUCKET_BRONCE = "bronceimat3a03"   # o el mismo bucket si usas prefijos
    BUCKET_PLATA  = "plataimat3a03"    # o el mismo bucket si usas prefijos

    BRONCE_PREFIX = "bronce/"            # p.ej. "crypto=avalanche/" o "entrada/"
    PLATA_PREFIX  = "plata/"             # p.ej. "crypto=avalanche_parquet/" o "salida-parquet/"

    convert_csv_s3_to_parquet_s3(
        bucket_bronce=BUCKET_BRONCE,
        bronce_prefix=BRONCE_PREFIX,
        bucket_plata=BUCKET_PLATA,
        plata_prefix=PLATA_PREFIX,
    )
