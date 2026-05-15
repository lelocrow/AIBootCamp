import os
import uuid
import json
import re
import time
import queue
import atexit
import signal
import logging
import tempfile
import threading
from copy import deepcopy
from datetime import datetime, timezone

from flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:
    ZoneInfo = None
    ZoneInfoNotFoundError = Exception

try:
    from .analyzer_profiles import (
        DEFAULT_ANALYZER_PROFILE_ID,
        build_profile_json_schema,
        build_profile_vertex_response_schema,
        get_profile_or_default,
        get_profile_schema_version,
        list_profiles_summary,
        render_profile_prompt,
    )
except ImportError:
    from analyzer_profiles import (  # type: ignore
        DEFAULT_ANALYZER_PROFILE_ID,
        build_profile_json_schema,
        build_profile_vertex_response_schema,
        get_profile_or_default,
        get_profile_schema_version,
        list_profiles_summary,
        render_profile_prompt,
    )

try:
    import vertexai
    from vertexai.generative_models import GenerativeModel, Part
except ImportError:
    vertexai = None
    GenerativeModel = None
    Part = None

try:
    from google.cloud import storage
except ImportError:
    storage = None

try:
    from jsonschema import Draft202012Validator
except ImportError:
    Draft202012Validator = None

try:
    import psycopg
    from psycopg.types.json import Jsonb
except ImportError:
    psycopg = None
    Jsonb = None


def _read_int_env(var_name, default_value):
    value = os.getenv(var_name, str(default_value))
    try:
        return int(value)
    except (TypeError, ValueError):
        return default_value


def _read_float_env(var_name, default_value):
    value = os.getenv(var_name, str(default_value))
    try:
        return float(value)
    except (TypeError, ValueError):
        return default_value


def _read_bool_env(var_name, default_value=False):
    value = os.getenv(var_name)
    if value is None:
        return default_value

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default_value


# =====================================================================
# BLOCO OBRIGATORIO DE CUSTOMIZACAO - BOOTCAMP / EMPRESA CONVIDADA
# =====================================================================
# Configure estes valores por participante/empresa via variaveis de ambiente.
# Exemplo pronto: cloudrun.env.example
#
# Obrigatorias para executar analise real com IA:
# - VERTEX_PROJECT_ID
# - GCS_BUCKET_NAME
#
# Obrigatorias para identidade do evento:
# - BOOTCAMP_ORG_NAME
# - BOOTCAMP_PARTICIPANT_NAME
#
# Personalizacao do caso de uso:
# - ANALYZER_PROFILE_ID (veja opcoes em backend/analyzer_profiles.py)
# =====================================================================
PROJECT_ID = os.getenv("VERTEX_PROJECT_ID", "").strip()
LOCATION = os.getenv("VERTEX_LOCATION", "us-central1").strip() or "us-central1"
BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "").strip()
MODEL_NAME = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash").strip() or "gemini-2.5-flash"
UPLOAD_PREFIX = os.getenv("GCS_UPLOAD_PREFIX", "uploads").strip() or "uploads"
SERVICE_NAME = os.getenv("SERVICE_NAME", "ai-bootcamp-analyzer").strip() or "ai-bootcamp-analyzer"
BOOTCAMP_ORG_NAME = os.getenv("BOOTCAMP_ORG_NAME", "Empresa Convidada").strip() or "Empresa Convidada"
BOOTCAMP_PARTICIPANT_NAME = os.getenv("BOOTCAMP_PARTICIPANT_NAME", "Participante Bootcamp").strip() or "Participante Bootcamp"
ANALYZER_PROFILE_ID = os.getenv("ANALYZER_PROFILE_ID", DEFAULT_ANALYZER_PROFILE_ID).strip() or DEFAULT_ANALYZER_PROFILE_ID

# Banco Postgres (Cloud SQL) - opcional mas recomendado no bootcamp
POSTGRES_ENABLED = _read_bool_env("POSTGRES_ENABLED", False)
POSTGRES_DATABASE = os.getenv("POSTGRES_DATABASE", "").strip()
POSTGRES_USER = os.getenv("POSTGRES_USER", "").strip()
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "").strip()
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "").strip()
POSTGRES_PORT = max(1, _read_int_env("POSTGRES_PORT", 5432))
POSTGRES_SSLMODE = os.getenv("POSTGRES_SSLMODE", "disable").strip() or "disable"
CLOUDSQL_INSTANCE_CONNECTION_NAME = os.getenv("CLOUDSQL_INSTANCE_CONNECTION_NAME", "").strip()
POSTGRES_AUTO_CREATE_TABLES = _read_bool_env("POSTGRES_AUTO_CREATE_TABLES", True)
POSTGRES_CONNECT_TIMEOUT_SECONDS = max(1, _read_int_env("POSTGRES_CONNECT_TIMEOUT_SECONDS", 10))

MAX_UPLOAD_SIZE_MB = _read_int_env("MAX_UPLOAD_SIZE_MB", 25)
JOB_RETENTION_SECONDS = _read_int_env("JOB_RETENTION_SECONDS", 3600)
MAX_STORED_JOBS = _read_int_env("MAX_STORED_JOBS", 300)
MAX_QUEUE_SIZE = max(1, _read_int_env("MAX_QUEUE_SIZE", 20))
MAX_OUTPUT_TOKENS = max(512, _read_int_env("MAX_OUTPUT_TOKENS", 8192))
GENERATION_TEMPERATURE = max(0.0, min(1.0, _read_float_env("GENERATION_TEMPERATURE", 0.1)))
PROMPT_REFERENCE_TIMEZONE = os.getenv("PROMPT_REFERENCE_TIMEZONE", "UTC").strip() or "UTC"
WORKER_QUEUE_POLL_SECONDS = max(0.1, _read_float_env("WORKER_QUEUE_POLL_SECONDS", 0.5))
WORKER_SHUTDOWN_TIMEOUT_SECONDS = max(1.0, _read_float_env("WORKER_SHUTDOWN_TIMEOUT_SECONDS", 8.0))
QUEUE_RETRY_AFTER_SECONDS = max(1, _read_int_env("QUEUE_RETRY_AFTER_SECONDS", 10))
SCHEMA_REPAIR_MAX_RETRIES = max(0, _read_int_env("SCHEMA_REPAIR_MAX_RETRIES", 1))

ACTIVE_PROFILE = get_profile_or_default(ANALYZER_PROFILE_ID)
ACTIVE_PROFILE_ID = ACTIVE_PROFILE["id"]
ACTIVE_PROFILE_SCHEMA_VERSION = get_profile_schema_version(ACTIVE_PROFILE)
ANALYSIS_PROMPT = render_profile_prompt(ACTIVE_PROFILE)
ACTIVE_PROFILE_JSON_SCHEMA = build_profile_json_schema(ACTIVE_PROFILE)
ACTIVE_PROFILE_VERTEX_RESPONSE_SCHEMA = build_profile_vertex_response_schema(ACTIVE_PROFILE)
ACTIVE_PROFILE_VALIDATOR = Draft202012Validator(ACTIVE_PROFILE_JSON_SCHEMA) if Draft202012Validator is not None else None

# Inicializa Flask - serve arquivos estaticos do React a partir de /app/static
app = Flask(__name__, static_folder="static", static_url_path="")
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_SIZE_MB * 1024 * 1024
app.logger.setLevel(logging.INFO)

_vertex_initialized = False
_model_instance = None
_model_lock = threading.Lock()
_storage_client = None
_storage_lock = threading.Lock()
_postgres_init_lock = threading.Lock()
_postgres_schema_ready = False

# Fila e armazenamento em memoria para jobs assincronos
_analysis_queue = queue.Queue(maxsize=MAX_QUEUE_SIZE)
_jobs = {}
_jobs_lock = threading.Lock()
_worker_thread = None
_worker_lock = threading.Lock()
_worker_stop_event = threading.Event()


class JobQueueFullError(Exception):
    """Erro levantado quando a fila de processamento esta no limite."""


def _utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def _runtime_configuration_warnings():
    warnings = []
    if not PROJECT_ID:
        warnings.append("VERTEX_PROJECT_ID nao configurada.")
    if not BUCKET_NAME:
        warnings.append("GCS_BUCKET_NAME nao configurada.")
    if ANALYZER_PROFILE_ID != ACTIVE_PROFILE_ID:
        warnings.append(
            f"ANALYZER_PROFILE_ID '{ANALYZER_PROFILE_ID}' nao encontrado. Usando '{ACTIVE_PROFILE_ID}'."
        )
    if ZoneInfo is not None:
        try:
            ZoneInfo(PROMPT_REFERENCE_TIMEZONE)
        except ZoneInfoNotFoundError:
            warnings.append(
                f"PROMPT_REFERENCE_TIMEZONE '{PROMPT_REFERENCE_TIMEZONE}' nao encontrada. Usando UTC no prompt."
            )

    if Draft202012Validator is None:
        warnings.append("Dependencia 'jsonschema' nao instalada.")

    warnings.extend(_postgres_configuration_warnings())
    return warnings


def _ensure_runtime_configuration():
    missing = []
    if not PROJECT_ID:
        missing.append("VERTEX_PROJECT_ID")
    if not BUCKET_NAME:
        missing.append("GCS_BUCKET_NAME")

    if missing:
        missing_text = ", ".join(missing)
        raise RuntimeError(
            "Configuracao obrigatoria ausente para processar analise: "
            f"{missing_text}. Configure no arquivo de env do participante/empresa."
        )

    if POSTGRES_ENABLED:
        _ensure_postgres_runtime_configuration()


def _resolve_prompt_reference_datetime():
    now_utc = datetime.now(timezone.utc)

    if ZoneInfo is None:
        return {
            "requested_timezone": PROMPT_REFERENCE_TIMEZONE,
            "effective_timezone": "UTC",
            "source": "zoneinfo_unavailable",
            "date_iso": now_utc.date().isoformat(),
            "datetime_iso": now_utc.isoformat(),
        }

    try:
        tzinfo = ZoneInfo(PROMPT_REFERENCE_TIMEZONE)
        now_ref = now_utc.astimezone(tzinfo)
        return {
            "requested_timezone": PROMPT_REFERENCE_TIMEZONE,
            "effective_timezone": PROMPT_REFERENCE_TIMEZONE,
            "source": "zoneinfo",
            "date_iso": now_ref.date().isoformat(),
            "datetime_iso": now_ref.isoformat(),
        }
    except ZoneInfoNotFoundError:
        return {
            "requested_timezone": PROMPT_REFERENCE_TIMEZONE,
            "effective_timezone": "UTC",
            "source": "invalid_timezone_fallback_utc",
            "date_iso": now_utc.date().isoformat(),
            "datetime_iso": now_utc.isoformat(),
        }


def _build_runtime_analysis_prompt(temporal_context=None):
    temporal_context = temporal_context or _resolve_prompt_reference_datetime()
    return (
        f"{ANALYSIS_PROMPT}\n\n"
        "Contexto temporal obrigatorio para esta analise:\n"
        f"- Data de referencia atual: {temporal_context['date_iso']}\n"
        f"- Data/hora de referencia: {temporal_context['datetime_iso']}\n"
        f"- Timezone de referencia efetiva: {temporal_context['effective_timezone']}\n"
        "Regras temporais obrigatorias:\n"
        "- Use essa data de referencia para qualquer validacao de passado/presente/futuro.\n"
        "- Nao marque como futuro uma data anterior a data de referencia.\n"
        "- Se houver ambiguidade de data no documento, sinalize como 'necessita validacao'.\n"
    )


def _get_model():
    """Inicializa Vertex AI apenas quando necessario."""
    if vertexai is None or GenerativeModel is None:
        raise RuntimeError("Dependencias do Vertex AI nao estao instaladas.")

    if not PROJECT_ID:
        raise RuntimeError("VERTEX_PROJECT_ID nao configurada.")

    global _vertex_initialized, _model_instance
    with _model_lock:
        if not _vertex_initialized:
            vertexai.init(project=PROJECT_ID, location=LOCATION)
            _vertex_initialized = True
        if _model_instance is None:
            _model_instance = GenerativeModel(MODEL_NAME)
    return _model_instance


def _get_storage_client():
    if storage is None:
        raise RuntimeError("Dependencias de Storage nao estao instaladas.")

    global _storage_client
    with _storage_lock:
        if _storage_client is None:
            _storage_client = storage.Client()
    return _storage_client


def _extract_json_from_model_response(raw_text):
    """Extrai um JSON mesmo quando o modelo envolve a resposta em markdown."""
    if not raw_text:
        raise json.JSONDecodeError("Resposta vazia do modelo", "", 0)

    cleaned = raw_text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        return json.loads(cleaned[start : end + 1])




def _json_path_to_string(path_parts):
    if not path_parts:
        return "$"

    segments = ["$"]
    for part in path_parts:
        if isinstance(part, int):
            segments.append(f"[{part}]")
        else:
            segments.append(f".{part}")
    return "".join(segments)


def _format_schema_validation_errors(validation_errors):
    formatted = []
    for error in validation_errors:
        formatted.append(
            {
                "path": _json_path_to_string(list(getattr(error, "path", []))),
                "message": error.message,
                "validator": getattr(error, "validator", None),
            }
        )

    formatted.sort(key=lambda item: item["path"])
    return formatted


def _summarize_validation_errors(validation_errors, limit=8):
    if not validation_errors:
        return "Sem detalhes"

    chunks = []
    for item in validation_errors[:limit]:
        chunks.append(f"{item['path']}: {item['message']}")
    return " | ".join(chunks)


def _fallback_validate_against_schema(value, schema_node, path="$"):
    errors = []

    if not isinstance(schema_node, dict):
        return errors

    expected_type = schema_node.get("type")

    if expected_type == "object":
        if not isinstance(value, dict):
            return [
                {
                    "path": path,
                    "message": "Deve ser um objeto JSON.",
                    "validator": "type",
                }
            ]

        required_fields = schema_node.get("required", [])
        properties = schema_node.get("properties", {})
        for field_name in required_fields:
            if field_name not in value:
                errors.append(
                    {
                        "path": f"{path}.{field_name}",
                        "message": "Campo obrigatorio ausente.",
                        "validator": "required",
                    }
                )

        if schema_node.get("additionalProperties") is False:
            for field_name in value.keys():
                if field_name not in properties:
                    errors.append(
                        {
                            "path": f"{path}.{field_name}",
                            "message": "Campo nao permitido pelo schema.",
                            "validator": "additionalProperties",
                        }
                    )

        for field_name, field_schema in properties.items():
            if field_name in value:
                errors.extend(
                    _fallback_validate_against_schema(
                        value[field_name], field_schema, f"{path}.{field_name}"
                    )
                )

        return errors

    if expected_type == "array":
        if not isinstance(value, list):
            return [
                {
                    "path": path,
                    "message": "Deve ser uma lista (array).",
                    "validator": "type",
                }
            ]

        item_schema = schema_node.get("items")
        for idx, item in enumerate(value):
            errors.extend(
                _fallback_validate_against_schema(item, item_schema, f"{path}[{idx}]")
            )
        return errors

    if expected_type == "string":
        if not isinstance(value, str):
            errors.append(
                {
                    "path": path,
                    "message": "Deve ser string.",
                    "validator": "type",
                }
            )
        else:
            enum_values = schema_node.get("enum")
            if enum_values and value not in enum_values:
                errors.append(
                    {
                        "path": path,
                        "message": f"Valor fora do enum permitido: {enum_values}.",
                        "validator": "enum",
                    }
                )
        return errors

    if expected_type == "number":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            errors.append(
                {
                    "path": path,
                    "message": "Deve ser numero.",
                    "validator": "type",
                }
            )
        return errors

    if expected_type == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            errors.append(
                {
                    "path": path,
                    "message": "Deve ser inteiro.",
                    "validator": "type",
                }
            )
        return errors

    if expected_type == "boolean":
        if not isinstance(value, bool):
            errors.append(
                {
                    "path": path,
                    "message": "Deve ser booleano.",
                    "validator": "type",
                }
            )
        return errors

    if expected_type == "null":
        if value is not None:
            errors.append(
                {
                    "path": path,
                    "message": "Deve ser null.",
                    "validator": "type",
                }
            )
        return errors

    return errors


def _validate_analysis_payload(analysis_data):
    if ACTIVE_PROFILE_VALIDATOR is None:
        fallback_errors = _fallback_validate_against_schema(
            analysis_data, ACTIVE_PROFILE_JSON_SCHEMA, path="$"
        )
        if not fallback_errors:
            return True, []
        return False, fallback_errors

    errors = list(ACTIVE_PROFILE_VALIDATOR.iter_errors(analysis_data))
    if not errors:
        return True, []

    return False, _format_schema_validation_errors(errors)


def _build_generation_config(include_response_schema=True):
    config = {
        "temperature": GENERATION_TEMPERATURE,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "response_mime_type": "application/json",
    }

    if include_response_schema:
        config["response_schema"] = ACTIVE_PROFILE_VERTEX_RESPONSE_SCHEMA

    return config


def _generate_content_with_schema_support(model, contents):
    schema_config = _build_generation_config(include_response_schema=True)
    try:
        return model.generate_content(contents, generation_config=schema_config)
    except Exception as exc:
        message = str(exc).lower()
        schema_related_error = "response_schema" in message or "schema" in message
        if not schema_related_error:
            raise

        app.logger.warning(
            "Falha ao usar response_schema no Gemini. Fallback sem response_schema. Detalhe: %s",
            str(exc),
        )
        fallback_config = _build_generation_config(include_response_schema=False)
        return model.generate_content(contents, generation_config=fallback_config)


def _build_schema_repair_prompt(raw_text, validation_errors):
    error_lines = []
    for item in validation_errors[:12]:
        error_lines.append(f"- {item['path']}: {item['message']}")

    errors_text = "\n".join(error_lines) if error_lines else "- Sem detalhes"
    schema_json = json.dumps(ACTIVE_PROFILE_JSON_SCHEMA, ensure_ascii=False, indent=2)

    return (
        "Corrija o JSON abaixo para que ele fique valido no schema informado.\n"
        "Retorne EXCLUSIVAMENTE o JSON corrigido, sem markdown.\n\n"
        "Schema:\n"
        f"{schema_json}\n\n"
        "Erros de validacao encontrados:\n"
        f"{errors_text}\n\n"
        "JSON atual:\n"
        f"{raw_text}"
    )


def _build_postgres_connect_kwargs():
    if CLOUDSQL_INSTANCE_CONNECTION_NAME:
        host = f"/cloudsql/{CLOUDSQL_INSTANCE_CONNECTION_NAME}"
    else:
        host = POSTGRES_HOST

    kwargs = {
        "dbname": POSTGRES_DATABASE,
        "user": POSTGRES_USER,
        "password": POSTGRES_PASSWORD,
        "host": host,
        "port": POSTGRES_PORT,
        "connect_timeout": POSTGRES_CONNECT_TIMEOUT_SECONDS,
    }

    if POSTGRES_SSLMODE:
        kwargs["sslmode"] = POSTGRES_SSLMODE

    return kwargs


def _postgres_configuration_warnings():
    warnings = []
    if not POSTGRES_ENABLED:
        return warnings

    required = {
        "POSTGRES_DATABASE": POSTGRES_DATABASE,
        "POSTGRES_USER": POSTGRES_USER,
        "POSTGRES_PASSWORD": POSTGRES_PASSWORD,
    }

    if not CLOUDSQL_INSTANCE_CONNECTION_NAME and not POSTGRES_HOST:
        warnings.append("Cloud SQL nao configurado: defina CLOUDSQL_INSTANCE_CONNECTION_NAME (recomendado) ou POSTGRES_HOST.")

    for key, value in required.items():
        if not value:
            warnings.append(f"{key} nao configurada.")

    if psycopg is None:
        warnings.append("Dependencia 'psycopg' nao instalada.")

    return warnings


def _ensure_postgres_runtime_configuration():
    if not POSTGRES_ENABLED:
        return

    warnings = _postgres_configuration_warnings()
    if warnings:
        raise RuntimeError(
            "Configuracao obrigatoria de Postgres ausente/invalida: " + "; ".join(warnings)
        )


def _ensure_postgres_table():
    global _postgres_schema_ready

    if not POSTGRES_ENABLED:
        return

    if _postgres_schema_ready:
        return

    _ensure_postgres_runtime_configuration()

    with _postgres_init_lock:
        if _postgres_schema_ready:
            return

        if not POSTGRES_AUTO_CREATE_TABLES:
            _postgres_schema_ready = True
            return

        create_table_sql = """
        CREATE TABLE IF NOT EXISTS analysis_runs (
            id BIGSERIAL PRIMARY KEY,
            job_id TEXT UNIQUE NOT NULL,
            file_name TEXT NOT NULL,
            service_name TEXT NOT NULL,
            organization_name TEXT NOT NULL,
            participant_name TEXT NOT NULL,
            analyzer_profile_id TEXT NOT NULL,
            analyzer_profile_schema_version TEXT NOT NULL,
            status TEXT NOT NULL,
            gcs_path TEXT,
            analysis_json JSONB,
            validation_errors JSONB,
            raw_model_response TEXT,
            prompt_reference_date DATE,
            prompt_reference_datetime TIMESTAMPTZ,
            prompt_reference_timezone TEXT,
            created_at TIMESTAMPTZ NOT NULL,
            started_at TIMESTAMPTZ,
            finished_at TIMESTAMPTZ,
            updated_at TIMESTAMPTZ NOT NULL
        );
        """

        with psycopg.connect(**_build_postgres_connect_kwargs()) as conn:
            with conn.cursor() as cursor:
                cursor.execute(create_table_sql)

        _postgres_schema_ready = True


def _parse_iso_datetime(value):
    if not value:
        return None

    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _to_jsonb(value):
    if Jsonb is not None:
        return Jsonb(value)
    return json.dumps(value, ensure_ascii=False)


def _persist_analysis_run(job, raw_model_response=None, validation_errors=None, prompt_context=None):
    if not POSTGRES_ENABLED:
        return False

    _ensure_postgres_table()

    prompt_context = prompt_context or {}

    job_id = job.get("job_id")
    status = job.get("status")
    analysis_json = job.get("analysis")

    sql = """
    INSERT INTO analysis_runs (
        job_id,
        file_name,
        service_name,
        organization_name,
        participant_name,
        analyzer_profile_id,
        analyzer_profile_schema_version,
        status,
        gcs_path,
        analysis_json,
        validation_errors,
        raw_model_response,
        prompt_reference_date,
        prompt_reference_datetime,
        prompt_reference_timezone,
        created_at,
        started_at,
        finished_at,
        updated_at
    ) VALUES (
        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
    )
    ON CONFLICT (job_id) DO UPDATE SET
        status = EXCLUDED.status,
        gcs_path = EXCLUDED.gcs_path,
        analysis_json = EXCLUDED.analysis_json,
        validation_errors = EXCLUDED.validation_errors,
        raw_model_response = EXCLUDED.raw_model_response,
        prompt_reference_date = EXCLUDED.prompt_reference_date,
        prompt_reference_datetime = EXCLUDED.prompt_reference_datetime,
        prompt_reference_timezone = EXCLUDED.prompt_reference_timezone,
        started_at = EXCLUDED.started_at,
        finished_at = EXCLUDED.finished_at,
        updated_at = EXCLUDED.updated_at;
    """

    analysis_value = _to_jsonb(analysis_json) if analysis_json is not None else None
    validation_value = _to_jsonb(validation_errors or [])

    values = (
        job_id,
        job.get("file_name"),
        SERVICE_NAME,
        BOOTCAMP_ORG_NAME,
        BOOTCAMP_PARTICIPANT_NAME,
        job.get("analyzer_profile_id") or ACTIVE_PROFILE_ID,
        job.get("analyzer_profile_schema_version") or ACTIVE_PROFILE_SCHEMA_VERSION,
        status,
        job.get("gcs_path"),
        analysis_value,
        validation_value,
        raw_model_response,
        prompt_context.get("date_iso"),
        _parse_iso_datetime(prompt_context.get("datetime_iso")),
        prompt_context.get("effective_timezone"),
        _parse_iso_datetime(job.get("created_at")) or datetime.now(timezone.utc),
        _parse_iso_datetime(job.get("started_at")),
        _parse_iso_datetime(job.get("finished_at")),
        _parse_iso_datetime(job.get("updated_at")) or datetime.now(timezone.utc),
    )

    with psycopg.connect(**_build_postgres_connect_kwargs()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, values)

    return True


def _public_job_data(job):
    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "stage": job["stage"],
        "progress": job["progress"],
        "file_name": job["file_name"],
        "gcs_path": job.get("gcs_path"),
        "error_type": job.get("error_type"),
        "error_message": job.get("error_message"),
        "analyzer_profile_id": job.get("analyzer_profile_id"),
        "analyzer_profile_schema_version": job.get("analyzer_profile_schema_version") or ACTIVE_PROFILE_SCHEMA_VERSION,
        "created_at": job.get("created_at"),
        "started_at": job.get("started_at"),
        "finished_at": job.get("finished_at"),
        "updated_at": job.get("updated_at"),
    }


def _get_job(job_id):
    with _jobs_lock:
        job = _jobs.get(job_id)
        return deepcopy(job) if job else None


def _update_job(job_id, **updates):
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            return None
        job.update(updates)
        job["updated_at"] = _utc_now_iso()
        return deepcopy(job)


def _cleanup_job_storage():
    """Remove jobs antigos e limita o tamanho do dicionario em memoria."""
    now_ts = time.time()
    with _jobs_lock:
        to_delete = []
        for job_id, job in _jobs.items():
            finished_at = job.get("finished_at")
            if not finished_at:
                continue
            try:
                finished_ts = datetime.fromisoformat(finished_at).timestamp()
            except ValueError:
                finished_ts = now_ts
            if now_ts - finished_ts > JOB_RETENTION_SECONDS:
                to_delete.append(job_id)

        for job_id in to_delete:
            _jobs.pop(job_id, None)

        if len(_jobs) <= MAX_STORED_JOBS:
            return

        ordered_jobs = sorted(
            _jobs.values(),
            key=lambda item: item.get("updated_at") or item.get("created_at") or "",
        )
        overflow = len(_jobs) - MAX_STORED_JOBS
        for job in ordered_jobs[:overflow]:
            _jobs.pop(job["job_id"], None)


def _create_job(file_name, safe_file_name, local_path):
    job_id = uuid.uuid4().hex
    now = _utc_now_iso()
    job_data = {
        "job_id": job_id,
        "file_name": file_name,
        "safe_file_name": safe_file_name,
        "local_path": local_path,
        "status": "queued",
        "stage": "queued",
        "progress": 5,
        "analysis": None,
        "gcs_path": None,
        "error_type": None,
        "error_message": None,
        "analyzer_profile_id": ACTIVE_PROFILE_ID,
        "analyzer_profile_schema_version": ACTIVE_PROFILE_SCHEMA_VERSION,
        "created_at": now,
        "updated_at": now,
        "started_at": None,
        "finished_at": None,
    }

    _cleanup_job_storage()
    with _jobs_lock:
        _jobs[job_id] = job_data
    return deepcopy(job_data)


def _stage_progress(stage):
    mapping = {
        "queued": 5,
        "uploading": 25,
        "analyzing": 65,
        "parsing": 85,
        "completed": 100,
        "failed": 100,
    }
    return mapping.get(stage, 5)


def _set_job_stage(job_id, stage):
    _update_job(job_id, stage=stage, progress=_stage_progress(stage))


def _build_blob_name(safe_file_name):
    prefix = UPLOAD_PREFIX.strip("/") or "uploads"
    return f"{prefix}/{uuid.uuid4()}/{safe_file_name}"


def _classify_error(message):
    lowered = (message or "").lower()
    if "timeout" in lowered or "timed out" in lowered:
        return "timeout"
    if "dependencias" in lowered:
        return "dependency_error"
    if "nao foi encontrado" in lowered:
        return "not_found"
    if "fila" in lowered and "cheia" in lowered:
        return "queue_full"
    if "configuracao" in lowered or "variavel" in lowered:
        return "configuration_error"
    if "schema" in lowered and "json" in lowered:
        return "schema_validation_error"
    if "postgres" in lowered or "cloud sql" in lowered:
        return "database_error"
    return "processing_error"


def _process_analysis_job(job_id):
    job = _get_job(job_id)
    if not job:
        return

    local_path = job.get("local_path")
    safe_file_name = job.get("safe_file_name")
    raw_text = ""
    validation_errors = []
    prompt_context = _resolve_prompt_reference_datetime()

    try:
        _update_job(job_id, status="processing", started_at=_utc_now_iso(), error_type=None, error_message=None)

        if Part is None:
            raise RuntimeError("Dependencias de IA/Storage nao estao instaladas.")

        _ensure_runtime_configuration()

        _set_job_stage(job_id, "uploading")
        storage_client = _get_storage_client()
        bucket = storage_client.bucket(BUCKET_NAME)
        blob_name = _build_blob_name(safe_file_name)
        blob = bucket.blob(blob_name)

        with open(local_path, "rb") as temp_pdf:
            blob.upload_from_file(temp_pdf, content_type="application/pdf")

        gcs_uri = f"gs://{BUCKET_NAME}/{blob_name}"
        _update_job(job_id, gcs_path=gcs_uri)

        _set_job_stage(job_id, "analyzing")
        model = _get_model()
        pdf_part = Part.from_uri(uri=gcs_uri, mime_type="application/pdf")
        runtime_prompt = _build_runtime_analysis_prompt(prompt_context)

        response = _generate_content_with_schema_support(model, [pdf_part, runtime_prompt])
        raw_text = (response.text or "").strip()

        _set_job_stage(job_id, "parsing")

        analysis_data = None
        current_text = raw_text
        for attempt in range(SCHEMA_REPAIR_MAX_RETRIES + 1):
            try:
                candidate = _extract_json_from_model_response(current_text)
            except json.JSONDecodeError as exc:
                validation_errors = [
                    {
                        "path": "$",
                        "message": f"JSON invalido: {str(exc)}",
                        "validator": "json_parse",
                    }
                ]

                if attempt >= SCHEMA_REPAIR_MAX_RETRIES:
                    raise

                repair_prompt = _build_schema_repair_prompt(current_text, validation_errors)
                repair_response = _generate_content_with_schema_support(model, [repair_prompt])
                current_text = (repair_response.text or "").strip()
                continue

            is_valid, validation_errors = _validate_analysis_payload(candidate)
            if is_valid:
                analysis_data = candidate
                break

            if attempt >= SCHEMA_REPAIR_MAX_RETRIES:
                raise RuntimeError(
                    "Schema validation failed: " + _summarize_validation_errors(validation_errors)
                )

            repair_prompt = _build_schema_repair_prompt(current_text, validation_errors)
            repair_response = _generate_content_with_schema_support(model, [repair_prompt])
            current_text = (repair_response.text or "").strip()

        if analysis_data is None:
            raise RuntimeError("Nao foi possivel obter JSON valido para o schema ativo.")

        raw_text = current_text

        _update_job(
            job_id,
            status="completed",
            stage="completed",
            progress=100,
            analysis=analysis_data,
            finished_at=_utc_now_iso(),
        )

        persisted_job = _get_job(job_id)
        if persisted_job:
            try:
                _persist_analysis_run(
                    persisted_job,
                    raw_model_response=raw_text,
                    validation_errors=validation_errors,
                    prompt_context=prompt_context,
                )
            except Exception:
                app.logger.exception("Falha ao persistir resultado no Postgres para o job %s", job_id)

    except json.JSONDecodeError as exc:
        app.logger.exception("Falha ao parsear resposta JSON do Gemini")
        _update_job(
            job_id,
            status="failed",
            stage="failed",
            progress=100,
            error_type="parse_error",
            error_message=f"Erro ao interpretar resposta do Gemini: {str(exc)}",
            finished_at=_utc_now_iso(),
        )
    except Exception as exc:
        app.logger.exception("Erro no processamento assincrono do job %s", job_id)
        message = str(exc)
        _update_job(
            job_id,
            status="failed",
            stage="failed",
            progress=100,
            error_type=_classify_error(message),
            error_message=message,
            finished_at=_utc_now_iso(),
        )
    finally:
        final_job = _get_job(job_id)
        if final_job and final_job.get("status") == "failed":
            try:
                _persist_analysis_run(
                    final_job,
                    raw_model_response=raw_text,
                    validation_errors=validation_errors,
                    prompt_context=prompt_context,
                )
            except Exception:
                app.logger.exception("Falha ao persistir falha de processamento no Postgres para o job %s", job_id)

        if local_path and os.path.exists(local_path):
            try:
                os.remove(local_path)
            except OSError:
                app.logger.warning("Nao foi possivel remover arquivo temporario: %s", local_path)
        _update_job(job_id, local_path=None)


def _analysis_worker_loop():
    app.logger.info("Worker de analise iniciado")
    while not _worker_stop_event.is_set():
        try:
            job_id = _analysis_queue.get(timeout=WORKER_QUEUE_POLL_SECONDS)
        except queue.Empty:
            continue

        if job_id is None:
            _analysis_queue.task_done()
            break

        try:
            _process_analysis_job(job_id)
        finally:
            _analysis_queue.task_done()

    app.logger.info("Worker de analise finalizado")


def _start_worker():
    global _worker_thread
    with _worker_lock:
        if _worker_thread and _worker_thread.is_alive():
            return

        _worker_stop_event.clear()
        _worker_thread = threading.Thread(
            target=_analysis_worker_loop,
            name="analysis-worker",
            daemon=True,
        )
        _worker_thread.start()


def _stop_worker():
    global _worker_thread
    with _worker_lock:
        thread = _worker_thread
        if not thread:
            return

        _worker_stop_event.set()
        try:
            _analysis_queue.put_nowait(None)
        except queue.Full:
            # O worker encerra no proximo ciclo ao detectar o stop_event.
            pass

    if thread.is_alive():
        thread.join(timeout=WORKER_SHUTDOWN_TIMEOUT_SECONDS)

    with _worker_lock:
        if _worker_thread is thread:
            _worker_thread = None


def _register_signal_handlers():
    def _handle_shutdown(_signum, _frame):
        app.logger.info("Sinal de encerramento recebido. Finalizando worker.")
        _stop_worker()

    for sig_name in ("SIGTERM", "SIGINT"):
        sig = getattr(signal, sig_name, None)
        if sig is None:
            continue
        try:
            signal.signal(sig, _handle_shutdown)
        except (ValueError, OSError):
            # Evita erro quando nao estamos no thread principal.
            pass


@atexit.register
def _shutdown_background_worker():
    _stop_worker()


def _enqueue_analysis_job(file_obj):
    file_name = file_obj.filename
    safe_file_name = secure_filename(file_name) or f"documento_{uuid.uuid4().hex}.pdf"

    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    temp_file_path = temp_file.name
    try:
        file_obj.stream.seek(0)
        file_obj.save(temp_file.name)
    finally:
        temp_file.close()

    job = _create_job(file_name=file_name, safe_file_name=safe_file_name, local_path=temp_file_path)
    try:
        _analysis_queue.put_nowait(job["job_id"])
    except queue.Full as exc:
        if os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except OSError:
                app.logger.warning("Nao foi possivel remover arquivo temporario rejeitado: %s", temp_file_path)
        with _jobs_lock:
            _jobs.pop(job["job_id"], None)
        raise JobQueueFullError("Fila de processamento cheia.") from exc

    return job


def _queue_snapshot():
    with _jobs_lock:
        active_jobs = sum(1 for job in _jobs.values() if job.get("status") in ("queued", "processing"))
    return {
        "current_size": _analysis_queue.qsize(),
        "max_size": MAX_QUEUE_SIZE,
        "active_jobs": active_jobs,
    }


def _public_runtime_config():
    temporal_context = _resolve_prompt_reference_datetime()
    postgres_warnings = _postgres_configuration_warnings()

    return {
        "service_name": SERVICE_NAME,
        "organization_name": BOOTCAMP_ORG_NAME,
        "participant_name": BOOTCAMP_PARTICIPANT_NAME,
        "vertex_project_configured": bool(PROJECT_ID),
        "vertex_location": LOCATION,
        "bucket_configured": bool(BUCKET_NAME),
        "bucket_name_preview": BUCKET_NAME if BUCKET_NAME else None,
        "model_name": MODEL_NAME,
        "analyzer": {
            "active_profile_id": ACTIVE_PROFILE_ID,
            "active_profile_name": ACTIVE_PROFILE["name"],
            "active_profile_description": ACTIVE_PROFILE["description"],
            "active_profile_schema_version": ACTIVE_PROFILE_SCHEMA_VERSION,
            "prompt": _build_runtime_analysis_prompt(temporal_context),
            "prompt_reference_context": temporal_context,
            "expected_fields": ACTIVE_PROFILE["expected_fields"],
            "response_template": ACTIVE_PROFILE["response_template"],
            "response_schema_json": ACTIVE_PROFILE_JSON_SCHEMA,
            "response_schema_vertex": ACTIVE_PROFILE_VERTEX_RESPONSE_SCHEMA,
            "available_profiles": list_profiles_summary(),
        },
        "postgres": {
            "enabled": POSTGRES_ENABLED,
            "auto_create_tables": POSTGRES_AUTO_CREATE_TABLES,
            "database_configured": bool(POSTGRES_DATABASE),
            "user_configured": bool(POSTGRES_USER),
            "password_configured": bool(POSTGRES_PASSWORD),
            "cloudsql_socket_configured": bool(CLOUDSQL_INSTANCE_CONNECTION_NAME),
            "host_configured": bool(POSTGRES_HOST),
            "connection_mode": "cloudsql_unix_socket" if CLOUDSQL_INSTANCE_CONNECTION_NAME else "tcp_host",
            "schema_ready": _postgres_schema_ready,
            "warnings": postgres_warnings,
        },
        "warnings": _runtime_configuration_warnings(),
    }


_register_signal_handlers()
_start_worker()

# =============================================
# ENDPOINTS
# =============================================


@app.route("/api/health")
def health_check():
    """Health check para o Cloud Run."""
    queue_info = _queue_snapshot()
    worker_alive = _worker_thread.is_alive() if _worker_thread else False
    return jsonify(
        {
            "status": "ok",
            "service": SERVICE_NAME,
            "worker_alive": worker_alive,
            "queue": queue_info,
            "limits": {
                "max_upload_size_mb": MAX_UPLOAD_SIZE_MB,
                "job_retention_seconds": JOB_RETENTION_SECONDS,
            },
            "postgres": {
                "enabled": POSTGRES_ENABLED,
                "schema_ready": _postgres_schema_ready,
                "warnings": _postgres_configuration_warnings(),
            },
            "analyzer_profile_id": ACTIVE_PROFILE_ID,
            "analyzer_profile_schema_version": ACTIVE_PROFILE_SCHEMA_VERSION,
            "configuration_warnings": _runtime_configuration_warnings(),
        }
    )


@app.route("/api/config", methods=["GET"])
def get_runtime_config():
    return jsonify({"success": True, "config": _public_runtime_config()})


@app.route("/api/analyze", methods=["POST"])
def analyze_document_async():
    """Recebe um PDF e enfileira para processamento assincrono."""
    try:
        if "file" not in request.files:
            return jsonify({"error": "Nenhum arquivo enviado. Use o campo 'file'.", "error_type": "invalid_file"}), 400

        file = request.files["file"]

        if not file or file.filename == "":
            return jsonify({"error": "Arquivo invalido ou sem nome.", "error_type": "invalid_file"}), 400

        if not file.filename.lower().endswith(".pdf"):
            return jsonify({"error": "Apenas arquivos PDF sao suportados.", "error_type": "invalid_file"}), 400

        job = _enqueue_analysis_job(file)
        response_payload = {
            "success": True,
            "message": "Arquivo recebido e enfileirado para analise.",
            "job": _public_job_data(job),
            "status_url": f"/api/analyze/{job['job_id']}/status",
            "result_url": f"/api/analyze/{job['job_id']}/result",
            "analyzer_profile_id": ACTIVE_PROFILE_ID,
            "analyzer_profile_schema_version": ACTIVE_PROFILE_SCHEMA_VERSION,
        }
        return jsonify(response_payload), 202
    except JobQueueFullError as exc:
        app.logger.warning("Fila cheia ao tentar enfileirar novo job.")
        response = jsonify(
            {
                "error": str(exc),
                "error_type": "queue_full",
                "retry_after_seconds": QUEUE_RETRY_AFTER_SECONDS,
            }
        )
        response.headers["Retry-After"] = str(QUEUE_RETRY_AFTER_SECONDS)
        return response, 429
    except Exception as exc:
        app.logger.exception("Erro interno no endpoint /api/analyze")
        return jsonify({"error": f"Erro interno: {str(exc)}", "error_type": "server_error"}), 500


@app.route("/api/analyze/<job_id>/status", methods=["GET"])
def analyze_status(job_id):
    job = _get_job(job_id)
    if not job:
        return jsonify({"error": "Job nao encontrado.", "error_type": "not_found"}), 404

    payload = {
        "success": True,
        "job": _public_job_data(job),
        "result_ready": job["status"] == "completed",
    }

    if job["status"] == "queued" or job["status"] == "processing":
        return jsonify(payload), 202

    if job["status"] == "failed":
        return jsonify(payload), 200

    return jsonify(payload), 200


@app.route("/api/analyze/<job_id>/result", methods=["GET"])
def analyze_result(job_id):
    job = _get_job(job_id)
    if not job:
        return jsonify({"error": "Job nao encontrado.", "error_type": "not_found"}), 404

    if job["status"] == "completed":
        return jsonify(
            {
                "success": True,
                "file_name": job["file_name"],
                "gcs_path": job.get("gcs_path"),
                "analysis": job.get("analysis"),
                "analyzer_profile_id": job.get("analyzer_profile_id") or ACTIVE_PROFILE_ID,
                "analyzer_profile_schema_version": job.get("analyzer_profile_schema_version") or ACTIVE_PROFILE_SCHEMA_VERSION,
                "job": _public_job_data(job),
            }
        )

    if job["status"] == "failed":
        return (
            jsonify(
                {
                    "success": False,
                    "error": job.get("error_message") or "Falha no processamento.",
                    "error_type": job.get("error_type") or "processing_error",
                    "job": _public_job_data(job),
                }
            ),
            500,
        )

    return (
        jsonify(
            {
                "success": False,
                "message": "Analise ainda em processamento.",
                "job": _public_job_data(job),
            }
        ),
        202,
    )


@app.route("/api/postgres/health", methods=["GET"])
def postgres_health_check():
    if not POSTGRES_ENABLED:
        return jsonify(
            {
                "success": False,
                "enabled": False,
                "message": "Persistencia Postgres desabilitada (POSTGRES_ENABLED=false).",
                "warnings": _postgres_configuration_warnings(),
            }
        ), 200

    try:
        _ensure_postgres_table()
        with psycopg.connect(**_build_postgres_connect_kwargs()) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()

        return jsonify(
            {
                "success": True,
                "enabled": True,
                "schema_ready": _postgres_schema_ready,
                "warnings": _postgres_configuration_warnings(),
            }
        ), 200
    except Exception as exc:
        app.logger.exception("Falha no health check do Postgres")
        return jsonify(
            {
                "success": False,
                "enabled": True,
                "error_type": "database_error",
                "error": str(exc),
                "warnings": _postgres_configuration_warnings(),
            }
        ), 500


@app.errorhandler(413)
def payload_too_large(_):
    return jsonify({"error": f"Arquivo muito grande. Limite de {MAX_UPLOAD_SIZE_MB}MB.", "error_type": "file_too_large"}), 413


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_spa(path):
    """Serve arquivos estaticos e fallback para o React Router."""
    if path.startswith("api/"):
        return jsonify({"error": "Endpoint nao encontrado.", "error_type": "not_found"}), 404

    static_file = os.path.join(app.static_folder, path)
    if path and os.path.exists(static_file):
        return send_from_directory(app.static_folder, path)

    return send_from_directory(app.static_folder, "index.html")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)

