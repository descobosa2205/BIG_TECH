import json
import boto3
import time
from kafka import KafkaConsumer
from datetime import datetime, timezone

# ==========================================
# 1. CONFIGURACIÓN DE CONEXIÓN
# ==========================================
KAFKA_PARAMS = {
    'bootstrap_servers': "51.49.235.244:9092",
    'security_protocol': "SASL_PLAINTEXT",
    'sasl_mechanism': "PLAIN",
    'sasl_plain_username': "kafka_client",
    'sasl_plain_password': "88b8a35dca1a04da57dc5f3e",
    'group_id': "grupo_consultora_dual_stream",
    'auto_offset_reset': "latest"
}

AWS_REGION = "eu-west-1"
DATABASE = "imat3a_crypto_rt"

# ==========================================
# 2. MAPEO DE TOPICS A TABLAS
# ==========================================
# Aquí definimos qué topic va a qué tabla y qué dato buscamos
TOPIC_CONFIG = {
    "imat3a-AVAX": {
        "table": "avax-imat-3a",
        "measure": "close"
    },
    "imat3a-AVAX-VWAP": {
        "table": "avax-vwap-3a",
        "measure": "vwap"
    }
}

def main() -> None:
    # Inicializar clientes
    ts_client = boto3.client("timestream-write", region_name=AWS_REGION)
    
    # Nos suscribimos a la lista de todos los topics definidos arriba
    consumer = KafkaConsumer(
        *TOPIC_CONFIG.keys(),
        **KAFKA_PARAMS,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")) if v else None
    )

    print(f"🚀 Iniciando consumidor dual para: {list(TOPIC_CONFIG.keys())}")

    try:
        for message in consumer:
            topic = message.topic
            data = message.value
            if not data: continue

            # 1. Identificar configuración según el topic de origen
            config = TOPIC_CONFIG.get(topic)
            table_name = config["table"]
            measure_name = config["measure"]
            
            # 2. Extraer valor (buscamos 'close' o 'vwap' según toque)
            value = data.get(measure_name)
            symbol = data.get("symbol", "UNKNOWN")

            if value is None:
                print(f"⚠️ Mensaje sin campo '{measure_name}' en topic {topic}")
                continue

            # 3. Preparar registro para Timestream
            timestamp_ms = str(int(datetime.now(timezone.utc).timestamp() * 1000))
            
            record = {
                "Dimensions": [
                    {"Name": "symbol", "Value": symbol},
                    {"Name": "source_topic", "Value": topic}
                ],
                "MeasureName": measure_name,
                "MeasureValue": str(float(value)),
                "MeasureValueType": "DOUBLE",
                "Time": timestamp_ms,
                "TimeUnit": "MILLISECONDS",
                "Version": int(time.time() * 1000)
            }

            # 4. Escribir en la tabla correspondiente
            try:
                ts_client.write_records(
                    DatabaseName=DATABASE,
                    TableName=table_name,
                    Records=[record]
                )
                print(f"✅ [{topic}] -> {table_name} | {measure_name}: {value}")
            except Exception as e:
                print(f"❌ Error escribiendo en Timestream ({topic}): {e}")

    except KeyboardInterrupt:
        print("\nDeteniendo servicios...")
    finally:
        consumer.close()

if __name__ == "__main__":
    main()