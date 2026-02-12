from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.window import Window
from awsglue.context import GlueContext
from pyspark.context import SparkContext
import boto3
from botocore.exceptions import ClientError

# =========================
# Parámetros
# =========================
SMA_WINDOW = 200
EMA_SPAN = 50

RSI_PERIOD = 14

MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

PATH_ORO = "s3://oroimat3a03/data"
CRYPTO_NAME = "avalanche" 

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

def add_ema(df, value_col, order_col, partition_cols, span, out_col):
    """
    EMA 100% Spark usando pesos exponenciales en ventana acumulada.
    EMA_t = sum(x_i * (1-a)^(t-i)) / sum((1-a)^(t-i))
    Se reescribe como: base^t * sum(x_i * base^-i) / (base^t * sum(base^-i)) => se cancela base^t
    donde base = (1 - alpha), alpha = 2/(span+1)

    Implementación:
      - generamos idx creciente por tiempo dentro de cada partición
      - usamos sum(x * base^(-idx)) / sum(base^(-idx)) en ventana unboundedPreceding..currentRow
    """
    alpha = 2.0 / (span + 1.0)
    base = 1.0 - alpha

    w_ord = Window.partitionBy(*partition_cols).orderBy(F.col(order_col))
    w_cum = w_ord.rowsBetween(Window.unboundedPreceding, Window.currentRow)

    df2 = df.withColumn("__idx", (F.row_number().over(w_ord) - 1).cast("double"))
    weight = F.pow(F.lit(base), -F.col("__idx"))

    num = F.sum(F.col(value_col) * weight).over(w_cum)
    den = F.sum(weight).over(w_cum)

    df2 = df2.withColumn(out_col, num / den).drop("__idx")
    return df2


def add_rsi(df, close_col, order_col, partition_cols, period, out_col):
    """
    RSI14 estilo Wilder:
      delta = close - lag(close)
      gain = max(delta, 0)
      loss = max(-delta, 0)
      avg_gain = EMA(gain, span=period con alpha=1/period)  (Wilder smoothing)
      avg_loss = EMA(loss, span=period con alpha=1/period)
      RSI = 100 - 100/(1 + avg_gain/avg_loss)

    Para Wilder: alpha = 1/period (no 2/(span+1)).
    Usamos el mismo truco de EMA con alpha fijo.
    """
    w_ord = Window.partitionBy(*partition_cols).orderBy(F.col(order_col))

    df2 = df.withColumn("__prev_close", F.lag(F.col(close_col)).over(w_ord))
    df2 = df2.withColumn("__delta", F.col(close_col) - F.col("__prev_close"))
    df2 = df2.withColumn("__gain", F.when(F.col("__delta") > 0, F.col("__delta")).otherwise(F.lit(0.0)))
    df2 = df2.withColumn("__loss", F.when(F.col("__delta") < 0, -F.col("__delta")).otherwise(F.lit(0.0)))

    # EMA con alpha = 1/period => base = 1 - 1/period
    alpha = 1.0 / float(period)
    base = 1.0 - alpha

    w_cum = w_ord.rowsBetween(Window.unboundedPreceding, Window.currentRow)

    df2 = df2.withColumn("__idx", (F.row_number().over(w_ord) - 1).cast("double"))
    weight = F.pow(F.lit(base), -F.col("__idx"))

    avg_gain = (F.sum(F.col("__gain") * weight).over(w_cum) / F.sum(weight).over(w_cum))
    avg_loss = (F.sum(F.col("__loss") * weight).over(w_cum) / F.sum(weight).over(w_cum))

    rs = avg_gain / F.when(avg_loss == 0, F.lit(None)).otherwise(avg_loss)
    rsi = F.lit(100.0) - (F.lit(100.0) / (F.lit(1.0) + rs))

    df2 = (
        df2
        .withColumn("__avg_gain", avg_gain)
        .withColumn("__avg_loss", avg_loss)
        .withColumn(out_col, rsi)
        .drop("__prev_close", "__delta", "__gain", "__loss", "__avg_gain", "__avg_loss", "__idx")
    )
    return df2


if __name__ == "__main__":
    s3 = boto3.client("s3", region_name="eu-south-2")
    spark = SparkSession.builder.appName("PlataToOro_Indicators_PySpark").getOrCreate()
    delete_bucket_if_exists("oroimat3a03")
    create_bucket(bucket_name="oroimat3a03", region="eu-south-2")
    glueContext = GlueContext(SparkContext.getOrCreate())

    dynamic_frame = glueContext.create_dynamic_frame.from_catalog(
        database="trade_data_imat3a03",
        table_name="silverdata"
    )
    df_plata = dynamic_frame.toDF()

    # -------------------------
    # Normalizar/asegurar tipos
    # -------------------------
    df = (
        df_plata
        .withColumn("datetime", F.col("datetime").cast("timestamp"))
        .withColumn("symbol", F.col("symbol").cast("string"))
        .withColumn("open", F.col("open").cast("double"))
        .withColumn("high", F.col("high").cast("double"))
        .withColumn("low", F.col("low").cast("double"))
        .withColumn("close", F.col("close").cast("double"))
        .withColumn("volume", F.col("volume").cast("double"))
        .filter(F.col("datetime").isNotNull() & F.col("symbol").isNotNull() & F.col("close").isNotNull())
    )

    # -------------------------
    # Particiones Oro
    # -------------------------
    df = (
        df
        .withColumn("crypto", F.lit(CRYPTO_NAME))
        .withColumn("year", F.year("datetime"))
        .withColumn("month", F.month("datetime"))
    )

    partition_cols = ["symbol"]  # o ["crypto","symbol"] si tienes varias cryptos mezcladas
    order_col = "datetime"

    # -------------------------
    # SMA 200 (Spark nativo)
    # -------------------------
    w_sma = Window.partitionBy(*partition_cols).orderBy(F.col(order_col)).rowsBetween(-SMA_WINDOW + 1, 0)
    df = df.withColumn("sma_200", F.avg(F.col("close")).over(w_sma))

    # -------------------------
    # EMA 50
    # -------------------------
    df = add_ema(df, value_col="close", order_col=order_col, partition_cols=partition_cols,
                 span=EMA_SPAN, out_col="ema_50")

    # -------------------------
    # RSI 14
    # -------------------------
    df = add_rsi(df, close_col="close", order_col=order_col, partition_cols=partition_cols,
                 period=RSI_PERIOD, out_col="rsi_14")

    # -------------------------
    # MACD (12,26, signal 9)
    # -------------------------
    df = add_ema(df, value_col="close", order_col=order_col, partition_cols=partition_cols,
                 span=MACD_FAST, out_col="ema_12")
    df = add_ema(df, value_col="close", order_col=order_col, partition_cols=partition_cols,
                 span=MACD_SLOW, out_col="ema_26")

    df = df.withColumn("macd", F.col("ema_12") - F.col("ema_26"))

    df = add_ema(df, value_col="macd", order_col=order_col, partition_cols=partition_cols,
                 span=MACD_SIGNAL, out_col="macd_signal")

    df = df.withColumn("macd_hist", F.col("macd") - F.col("macd_signal")).drop("ema_12", "ema_26")

    # -------------------------
    # Guardar Oro
    # -------------------------
    (
        df
        .write
        .mode("overwrite")
        .partitionBy("crypto", "year", "month")
        .parquet(PATH_ORO)
    )

    spark.stop()
