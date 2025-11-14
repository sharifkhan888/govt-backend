from pathlib import Path
from datetime import datetime
from django.core.management import call_command
from django.conf import settings

EXPORT_DIR = Path(__file__).resolve().parents[3] / "assets" / "exports"
EXPORT_DIR.mkdir(parents=True, exist_ok=True)


def create_backup() -> str:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    file_path = EXPORT_DIR / f"backup-{ts}.json"
    with open(file_path, "w", encoding="utf-8") as f:
        call_command("dumpdata", format="json", indent=2, stdout=f)
    return str(file_path)


def restore_backup(file_path: str) -> None:
    with open(file_path, "r", encoding="utf-8") as f:
        call_command("loaddata", file_path)


