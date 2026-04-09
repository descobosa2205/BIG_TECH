# -*- coding: utf-8 -*-

from pyspark.sql import SparkSession
from pyspark.sql.functions import col, from_json, window, sum as _sum, to_json, struct, date_format
from pyspark.sql.types import StructType, StructField, StringType, DoubleType, LongType

# =========================
# CONFIGURACIÓN KAFKA
# =========================
BOOTSTRAP_SERVERS = "51.49.235.244:9092"
USERNAME = "kafka_client"
PASSWORD = "88b8a35dca1a04da57dc5f3e"
TOPIC_IN = "imat3a-AVAX"       
TOPIC_OUT = "imat3a-AVAX-VWAP"  

JAAS_CONFIG = f'org.apache.kafka.common.security.plain.PlainLoginModule required username="{USERNAME}" password="{PASSWORD}";'

def main():
    # 1. Inicializar Spark
    spark = SparkSession.builder \
        .appName("Calculo_VWAP_Sliding_Trigger") \
        .getOrCreate()

    spark.sparkContext.setLogLevel("WARN")

    # 2. Esquema de entrada
    schema_in = StructType([
        StructField("symbol", StringType()),
        StructField("@timestamp", StringType()),
        StructField("close", DoubleType()),
        StructField("volume", DoubleType()),
        StructField("timestamp_ms", LongType())
    ])

    # 3. Lectura desde Kafka
    raw_df = spark.readStream \
        .format("kafka") \
        .option("kafka.bootstrap.servers", BOOTSTRAP_SERVERS) \
        .option("kafka.security.protocol", "SASL_PLAINTEXT") \
        .option("kafka.sasl.mechanism", "PLAIN") \
        .option("kafka.sasl.jaas.config", JAAS_CONFIG) \
        .option("subscribe", TOPIC_IN) \
        .option("startingOffsets", "latest") \
        .load()

    # 4. Parseo del JSON
    parsed_df = raw_df.selectExpr("CAST(value AS STRING)") \
        .select(from_json(col("value"), schema_in).alias("data")) \
        .select("data.*")

    # 5. Conversión de Tiempo (CRÍTICO: Usamos timestamp_ms para precisión exacta)
    time_df = parsed_df.withColumn(
        "timestamp", 
        (col("timestamp_ms") / 1000).cast("timestamp")
    )

    # 6. Cálculo VWAP (Watermark + Ventana Deslizante Temporal)
    vwap_df = time_df \
        .withWatermark("timestamp", "1 minute") \
        .groupBy(
            window(col("timestamp"), "5 minutes", "1 minute"),
            col("symbol")
        ) \
        .agg(
            (_sum(col("close") * col("volume")) / _sum(col("volume"))).alias("vwap")
        )

    # 7. Formateo del mensaje de salida
    formatted_df = vwap_df.select(
        date_format(col("window.start"), "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'").alias("window_start"),
        date_format(col("window.end"), "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'").alias("window_end"),
        col("symbol"),
        col("vwap")
    )

    kafka_output_df = formatted_df.select(
        col("symbol").alias("key"),
        to_json(struct("*")).alias("value")
    )

    # 8. Escritura en Kafka (El "Santo Grial": Append + Trigger)
    print(f"Iniciando cálculo VWAP (Trigger 1 min) hacia {TOPIC_OUT}...")
    query = kafka_output_df.writeStream \
        .format("kafka") \
        .option("kafka.bootstrap.servers", BOOTSTRAP_SERVERS) \
        .option("kafka.security.protocol", "SASL_PLAINTEXT") \
        .option("kafka.sasl.mechanism", "PLAIN") \
        .option("kafka.sasl.jaas.config", JAAS_CONFIG) \
        .option("topic", TOPIC_OUT) \
        .option("checkpointLocation", "/tmp/checkpoints_vwap_final") \
        .outputMode("append") \
        .trigger(processingTime="1 minute") \
        .start()

    query.awaitTermination()

if __name__ == "__main__":
    main()