import time
import boto3
from botocore.exceptions import ClientError

# ====== CONFIG ======
REGION = "eu-south-2" 
CRAWLER_NAME = "broncecrawler"
ROLE_ARN = "arn:aws:iam::205930633313:role/SpidermanRol" 
DATABASE_NAME = "trade_data_imat3a03"  # la base de datos del Glue Data Catalog

BUCKET_NAME = "bronceimat3a03"
PREFIX_IN_BUCKET = ""  # ej: "raw/" si tus datos cuelgan de s3://bucket/raw/
S3_TARGET_PATH = f"s3://{BUCKET_NAME}/{PREFIX_IN_BUCKET}"
# ====================


def ensure_database(glue, database_name: str):
    """Crea la DB si no existe."""
    try:
        glue.get_database(Name=database_name)
        print(f"Database ya existe: {database_name}")
    except glue.exceptions.EntityNotFoundException:
        glue.create_database(DatabaseInput={"Name": database_name})
        print(f"Database creada: {database_name}")


def ensure_crawler(glue, crawler_name: str):
    """Crea el crawler si no existe; si existe lo actualiza."""
    targets = {"S3Targets": [{"Path": S3_TARGET_PATH}]}

    crawler_kwargs = dict(
        Name=crawler_name,
        Role=ROLE_ARN,
        DatabaseName=DATABASE_NAME,
        Targets=targets,
        Description=f"Crawler para {S3_TARGET_PATH}",
        RecrawlPolicy={"RecrawlBehavior": "CRAWL_NEW_FOLDERS_ONLY"},  # ideal para /year=/month=
        SchemaChangePolicy={
            "UpdateBehavior": "LOG",
            "DeleteBehavior": "LOG",
        },
    )

    try:
        glue.get_crawler(Name=crawler_name)
        glue.update_crawler(**crawler_kwargs)
        print(f"Crawler actualizado: {crawler_name}")
    except glue.exceptions.EntityNotFoundException:
        glue.create_crawler(**crawler_kwargs)
        print(f"Crawler creado: {crawler_name}")


def start_crawler(glue, crawler_name: str):
    try:
        glue.start_crawler(Name=crawler_name)
        print(f"Crawler iniciado: {crawler_name}")
    except glue.exceptions.CrawlerRunningException:
        print(f"El crawler ya estaba corriendo: {crawler_name}")


def wait_for_crawler(glue, crawler_name: str, poll_seconds: int = 15, timeout_seconds: int = 1800):
    start = time.time()
    while True:
        crawler = glue.get_crawler(Name=crawler_name)["Crawler"]
        state = crawler.get("State")
        last_crawl = crawler.get("LastCrawl", {})
        print(f"Estado: {state}")

        if state not in ("RUNNING", "STOPPING"):
            print(f"Finalizado. Estado: {state}")
            if last_crawl:
                print(f"    LastCrawl Status: {last_crawl.get('Status')}")
                if last_crawl.get("ErrorMessage"):
                    print(f"   ErrorMessage: {last_crawl.get('ErrorMessage')}")
            return crawler

        if time.time() - start > timeout_seconds:
            raise TimeoutError(f"Timeout esperando al crawler {crawler_name}")

        time.sleep(poll_seconds)


def main():
    session = boto3.Session(region_name=REGION)
    glue = session.client("glue")

    print(f"Target: {S3_TARGET_PATH}")

    ensure_database(glue, DATABASE_NAME)
    ensure_crawler(glue, CRAWLER_NAME)
    start_crawler(glue, CRAWLER_NAME)
    crawler = wait_for_crawler(glue, CRAWLER_NAME)

    print("\n Resumen:")
    print(f"- Crawler: {crawler.get('Name')}")
    print(f"- Database: {DATABASE_NAME}")
    print(f"- Target: {S3_TARGET_PATH}")
    if crawler.get("LastCrawl"):
        print(f"- LastCrawl.Status: {crawler['LastCrawl'].get('Status')}")


if __name__ == "__main__":
    main()
