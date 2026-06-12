import logging

STAGE_DOWNLOAD = "download"
STAGE_PARSE = "parse"
STAGE_DB_MAP = "db_map"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(stage)s] %(message)s",
)


def get_logger(stage: str) -> logging.LoggerAdapter:
    logger = logging.getLogger("hs_athletes")
    return logging.LoggerAdapter(logger, {"stage": stage})
