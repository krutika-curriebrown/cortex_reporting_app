"""
Table definitions and connection helper for the Cortex Tracker app.

Two tables, matching the design worked out with the team:

- PROJECTS: one row per project, live current state. HASH_ID is the
  permanent identity, generated once at creation and never touched again -
  it's what lets a project survive being renamed without losing its history.
  CURRENT_STAGE is a single field (not several independent status flags),
  so a project is always in exactly one place in its pipeline, never an
  ambiguous combination.

- PROJECT_EVENTS: append-only log, one row per real action (stage advance,
  correction, assignment change, rename, etc.). VOIDED marks rows that
  shouldn't count in reporting anymore (e.g. a correction undoing an
  accidental double-click) without ever deleting the record of what
  actually happened - every reporting query filters WHERE VOIDED = FALSE.
"""

import os
from pathlib import Path

from databricks import sql

# Local dev only - loads .env next to this file if present (and if the
# actual env vars aren't already set some other way, e.g. Azure App
# Service's Configuration blade at deploy time). No dependency on
# python-dotenv for something this small.
_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _key, _value = _line.split("=", 1)
            os.environ.setdefault(_key.strip(), _value.strip())

SERVER_HOSTNAME = os.getenv("server_hostname")
HTTP_PATH = os.getenv("http_path")
DATABRICKS_TOKEN = os.getenv("passkey")

CATALOG = "hive_metastore"
SCHEMA = "cortex_etl"
PROJECTS_TABLE = f"{CATALOG}.{SCHEMA}.projects"
EVENTS_TABLE = f"{CATALOG}.{SCHEMA}.project_events"


def get_connection():
    return sql.connect(
        server_hostname=SERVER_HOSTNAME,
        http_path=HTTP_PATH,
        access_token=DATABRICKS_TOKEN,
    )


def init_tables():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")

    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {PROJECTS_TABLE} (
            -- Identity, pipeline state, and the mandatory "Add New Project"
            -- fields - populated for every project, new or migrated.
            HASH_ID STRING,
            TRACKER STRING,
            PROJECT_NAME STRING,
            PRIORITY STRING,
            COUNTRY STRING,
            REGION STRING,
            SECTOR STRING,
            PROJECT_LOCATION STRING,
            YEAR BIGINT,
            PROJECT_TYPE STRING,
            KEY_QUANTITY DOUBLE,
            KEY_QUANTITY_UNITS STRING,
            SOURCE_DOC_LINK STRING,
            CURRENT_STAGE STRING,
            ANALYST STRING,
            REVIEWER STRING,
            CREATED_BY STRING,
            CREATED_AT STRING,
            IS_LEGACY_IMPORT BOOLEAN,
            ARCHIVED BOOLEAN,

            -- Supplementary descriptive fields - optional on "Add New
            -- Project" (not part of the mandatory set), locked after
            -- creation like everything else. Real, ongoing fields, not
            -- migration-only - carried over from the old tracker sheets
            -- where most of this data originally came from.
            PROJECT_REFERENCE_ID STRING,
            SUB_TYPE STRING,
            CONSTRUCTION_TYPE STRING,
            LME_RATES STRING,
            CURRIE_BROWN_CONTACT STRING,
            NOTES STRING,

            -- "Page # for Total", "Translation Notes", and "Order" (a UK
            -- tracker row-sort helper, never real project data) were all
            -- dropped entirely, not carried over - see migration.py's
            -- COLUMN_RENAME.

            -- "2024/2025 dropdown", "Entered in excel sheet", and
            -- "In Project Library" (all obscure, US/Global-only
            -- bookkeeping fields whose meaning was never confirmed) were
            -- all dropped entirely rather than carried over as historical-
            -- only fields - see migration.py's COLUMN_RENAME.

            -- Raw historical status values, preserved for audit - shows
            -- exactly what each sheet said before being mapped onto
            -- CURRENT_STAGE at migration time. Superseded by CURRENT_STAGE;
            -- not used by the app itself, never a form field.
            LEGACY_TEMPLATE_STATUS STRING,
            LEGACY_REVIEW_STATUS STRING,
            LEGACY_IN_CORTEX_UPLOAD_FOLDER STRING,
            LEGACY_IN_CORTEX STRING
        ) USING DELTA
        TBLPROPERTIES ('delta.columnMapping.mode' = 'name')
    """)

    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {EVENTS_TABLE} (
            EVENT_ID STRING,
            HASH_ID STRING,
            EVENT_TYPE STRING,
            OLD_VALUE STRING,
            NEW_VALUE STRING,
            CHANGED_BY STRING,
            EFFECTIVE_DATE STRING,
            LOGGED_AT STRING,
            VOIDED BOOLEAN,
            VOIDED_BY_EVENT_ID STRING
        ) USING DELTA
        TBLPROPERTIES ('delta.columnMapping.mode' = 'name')
    """)

    cursor.close()
    conn.close()
