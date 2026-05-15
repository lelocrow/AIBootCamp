import json
from copy import deepcopy


# =====================================================================
# BLOCO PRINCIPAL DE CUSTOMIZACAO DO ANALISADOR (PROMPT + CAMPOS)
# =====================================================================
# Cada perfil abaixo representa uma utilidade diferente para o projeto.
# Os participantes podem:
# 1) Escolher um perfil via variavel de ambiente ANALYZER_PROFILE_ID
# 2) Duplicar um perfil existente e criar seu proprio caso de uso
# 3) Ajustar expected_fields / response_template para a necessidade local
#
# IMPORTANTE:
# - O backend envia o prompt final para a IA com base nesses dados.
# - O frontend exibe o prompt e os campos esperados em /api/config.
# =====================================================================


ANALYZER_PROFILES = {
    "contract_risk_guard": {
        "id": "contract_risk_guard",
        "name": "Contract Risk Guard",
        "description": "Analisa contratos e destaca clausulas criticas, obrigacoes e riscos.",
        "objective": "Identificar riscos juridicos e operacionais em contratos comerciais.",
        "expected_fields": [
            {"name": "document_title", "type": "string", "description": "Titulo ou tipo do contrato."},
            {"name": "executive_summary", "type": "string", "description": "Resumo curto com os principais pontos."},
            {"name": "parties", "type": "array", "description": "Lista de partes com papel, nome e documento."},
            {"name": "key_obligations", "type": "array", "description": "Obrigacoes principais das partes."},
            {"name": "critical_clauses", "type": "array", "description": "Clausulas sensiveis com impacto."},
            {"name": "risk_alerts", "type": "array", "description": "Riscos classificados por nivel."},
            {"name": "action_checklist", "type": "array", "description": "Checklist de acoes antes da assinatura."},
        ],
        "response_template": {
            "document_title": "string",
            "executive_summary": "string",
            "parties": [
                {"role": "string", "name": "string", "document": "string"}
            ],
            "key_obligations": [
                {"owner": "string", "obligation": "string", "deadline": "string"}
            ],
            "critical_clauses": [
                {"clause": "string", "impact": "string", "attention_level": "high|medium|low"}
            ],
            "risk_alerts": [
                {"level": "high|medium|low", "category": "legal|financial|operational", "description": "string", "mitigation": "string"}
            ],
            "action_checklist": [
                {"item": "string", "status": "pending|ok|missing", "next_step": "string"}
            ],
        },
    },
    "invoice_audit_assistant": {
        "id": "invoice_audit_assistant",
        "name": "Invoice Audit Assistant",
        "description": "Audita notas fiscais e faturas para encontrar inconsistencias.",
        "objective": "Detectar cobrancas indevidas, impostos suspeitos e divergencias em faturas.",
        "expected_fields": [
            {"name": "document_title", "type": "string", "description": "Titulo da nota fiscal ou fatura."},
            {"name": "executive_summary", "type": "string", "description": "Resumo da auditoria automatica."},
            {"name": "supplier", "type": "object", "description": "Dados principais do fornecedor."},
            {"name": "invoice_metadata", "type": "object", "description": "Numero, data de emissao e vencimento."},
            {"name": "line_items", "type": "array", "description": "Itens faturados com quantidade e valores."},
            {"name": "taxes", "type": "array", "description": "Resumo de impostos identificados."},
            {"name": "inconsistencies", "type": "array", "description": "Divergencias encontradas no documento."},
            {"name": "recommended_actions", "type": "array", "description": "Acoes sugeridas para financeiro/compras."},
        ],
        "response_template": {
            "document_title": "string",
            "executive_summary": "string",
            "supplier": {"name": "string", "document": "string"},
            "invoice_metadata": {"invoice_number": "string", "issue_date": "string", "due_date": "string"},
            "line_items": [
                {"description": "string", "quantity": "number", "unit_price": "number", "total": "number"}
            ],
            "taxes": [
                {"tax_name": "string", "tax_value": "number"}
            ],
            "inconsistencies": [
                {"severity": "high|medium|low", "finding": "string", "evidence": "string"}
            ],
            "recommended_actions": [
                {"action": "string", "owner": "string", "priority": "high|medium|low"}
            ],
        },
    },
    "resume_screening_copilot": {
        "id": "resume_screening_copilot",
        "name": "Resume Screening Copilot",
        "description": "Avalia curriculos para vagas especificas e gera score objetivo.",
        "objective": "Ajudar recrutadores a priorizar candidatos com base em criterios tecnicos.",
        "expected_fields": [
            {"name": "candidate_name", "type": "string", "description": "Nome do candidato identificado no curriculo."},
            {"name": "target_role", "type": "string", "description": "Vaga alvo inferida ou informada."},
            {"name": "executive_summary", "type": "string", "description": "Resumo do perfil profissional."},
            {"name": "core_skills", "type": "array", "description": "Competencias principais encontradas."},
            {"name": "experience_highlights", "type": "array", "description": "Experiencias relevantes para a vaga."},
            {"name": "red_flags", "type": "array", "description": "Sinais de atencao no curriculo."},
            {"name": "interview_questions", "type": "array", "description": "Perguntas recomendadas para entrevista."},
            {"name": "scorecards", "type": "array", "description": "Pontuacao por criterio com justificativa."},
            {"name": "recommendation", "type": "string", "description": "Recomendacao final (seguir ou nao)."},
        ],
        "response_template": {
            "candidate_name": "string",
            "target_role": "string",
            "executive_summary": "string",
            "core_skills": ["string"],
            "experience_highlights": [
                {"period": "string", "company": "string", "highlight": "string"}
            ],
            "red_flags": ["string"],
            "interview_questions": ["string"],
            "scorecards": [
                {"criterion": "string", "score": "number", "max_score": "number", "justification": "string"}
            ],
            "recommendation": "strong_yes|yes|maybe|no",
        },
    },
    "support_ticket_triage": {
        "id": "support_ticket_triage",
        "name": "Support Ticket Triage",
        "description": "Classifica chamados e acelera respostas de suporte tecnico.",
        "objective": "Padronizar triagem de tickets para reduzir tempo de resposta.",
        "expected_fields": [
            {"name": "ticket_id", "type": "string", "description": "Identificador do chamado."},
            {"name": "customer_context", "type": "string", "description": "Contexto relevante do cliente."},
            {"name": "executive_summary", "type": "string", "description": "Resumo do problema reportado."},
            {"name": "issue_category", "type": "string", "description": "Categoria do incidente."},
            {"name": "urgency_level", "type": "string", "description": "Nivel de urgencia sugerido."},
            {"name": "probable_root_causes", "type": "array", "description": "Possiveis causas do problema."},
            {"name": "troubleshooting_steps", "type": "array", "description": "Passos iniciais de diagnostico."},
            {"name": "response_draft", "type": "string", "description": "Rascunho de resposta para o cliente."},
            {"name": "escalation_needed", "type": "boolean", "description": "Se precisa escalonar para outro time."},
            {"name": "next_actions", "type": "array", "description": "Proximas acoes com dono e prazo."},
        ],
        "response_template": {
            "ticket_id": "string",
            "customer_context": "string",
            "executive_summary": "string",
            "issue_category": "string",
            "urgency_level": "critical|high|medium|low",
            "probable_root_causes": ["string"],
            "troubleshooting_steps": [
                {"step": "string", "expected_signal": "string"}
            ],
            "response_draft": "string",
            "escalation_needed": True,
            "next_actions": [
                {"action": "string", "owner": "string", "deadline": "string"}
            ],
        },
    },
    "policy_compliance_reviewer": {
        "id": "policy_compliance_reviewer",
        "name": "Policy Compliance Reviewer",
        "description": "Revisa politicas internas e destaca lacunas de compliance.",
        "objective": "Avaliar aderencia de documentos internos a normas e controles.",
        "expected_fields": [
            {"name": "document_title", "type": "string", "description": "Nome da politica ou procedimento."},
            {"name": "executive_summary", "type": "string", "description": "Resumo da revisao de compliance."},
            {"name": "applicable_regulations", "type": "array", "description": "Normas citadas ou inferidas."},
            {"name": "compliant_points", "type": "array", "description": "Pontos em conformidade."},
            {"name": "non_compliant_points", "type": "array", "description": "Pontos fora de conformidade."},
            {"name": "evidence_gaps", "type": "array", "description": "Evidencias faltantes para auditoria."},
            {"name": "risk_alerts", "type": "array", "description": "Riscos de compliance detectados."},
            {"name": "remediation_plan", "type": "array", "description": "Plano de acao para adequacao."},
        ],
        "response_template": {
            "document_title": "string",
            "executive_summary": "string",
            "applicable_regulations": ["string"],
            "compliant_points": ["string"],
            "non_compliant_points": ["string"],
            "evidence_gaps": ["string"],
            "risk_alerts": [
                {"level": "high|medium|low", "risk": "string", "impact": "string"}
            ],
            "remediation_plan": [
                {"action": "string", "owner": "string", "deadline": "string", "priority": "high|medium|low"}
            ],
        },
    },
    "customizado": {
        "id": "customizado",
        "name": "Customizado",
        "description": "Perfil em branco para o participante montar seu proprio analisador manualmente.",
        "objective": "Definir manualmente um caso de uso de analise documental para o bootcamp.",
        "expected_fields": [
            {"name": "document_title", "type": "string", "description": "Titulo identificado no documento."},
            {"name": "executive_summary", "type": "string", "description": "Resumo principal do documento."},
            {"name": "custom_field_1", "type": "string", "description": "Campo personalizado definido pelo participante."},
            {"name": "custom_field_2", "type": "array", "description": "Lista personalizada definida pelo participante."},
            {"name": "custom_notes", "type": "string", "description": "Observacoes finais do analisador."},
        ],
        "response_template": {
            "document_title": "string",
            "executive_summary": "string",
            "custom_field_1": "string",
            "custom_field_2": [
                {"item": "string", "details": "string"}
            ],
            "custom_notes": "string",
        },
    },
}

DEFAULT_ANALYZER_PROFILE_ID = "contract_risk_guard"
DEFAULT_PROFILE_SCHEMA_VERSION = "1.0.0"

_SCALAR_TEMPLATE_TYPE_MAP = {
    "string": "string",
    "number": "number",
    "integer": "integer",
    "boolean": "boolean",
    "object": "object",
    "array": "array",
    "null": "null",
}


def _build_prompt(profile):
    response_template = json.dumps(profile["response_template"], indent=2, ensure_ascii=False)

    return (
        "Voce e um especialista em leitura de documentos empresariais em portugues.\n\n"
        f"Objetivo do analisador: {profile['objective']}\n\n"
        "Analise o PDF recebido e retorne EXCLUSIVAMENTE um JSON valido no formato abaixo.\n"
        "Nao use markdown. Nao escreva texto fora do JSON.\n\n"
        f"{response_template}\n\n"
        "Regras obrigatorias:\n"
        "- Use somente informacoes presentes no documento.\n"
        "- Quando um campo nao existir no documento, use valor vazio coerente (\"\", [], ou null).\n"
        "- Mantenha o JSON parseavel com aspas duplas e sem comentarios.\n"
        "- Nao adicione chaves fora do formato definido.\n"
    )


def get_profile_or_default(profile_id):
    selected_id = (profile_id or "").strip()
    profile = ANALYZER_PROFILES.get(selected_id) or ANALYZER_PROFILES[DEFAULT_ANALYZER_PROFILE_ID]
    if "schema_version" not in profile:
        profile = deepcopy(profile)
        profile["schema_version"] = DEFAULT_PROFILE_SCHEMA_VERSION
    return deepcopy(profile)


def list_profiles_summary():
    summaries = []
    for profile in ANALYZER_PROFILES.values():
        summaries.append(
            {
                "id": profile["id"],
                "name": profile["name"],
                "description": profile["description"],
                "objective": profile["objective"],
                "schema_version": profile.get("schema_version", DEFAULT_PROFILE_SCHEMA_VERSION),
            }
        )
    return summaries


def render_profile_prompt(profile):
    return _build_prompt(profile)


def get_profile_schema_version(profile):
    if not profile:
        return DEFAULT_PROFILE_SCHEMA_VERSION
    return profile.get("schema_version", DEFAULT_PROFILE_SCHEMA_VERSION)


def _template_value_to_json_schema(template_value):
    if isinstance(template_value, bool):
        return {"type": "boolean"}

    if isinstance(template_value, int) and not isinstance(template_value, bool):
        return {"type": "integer"}

    if isinstance(template_value, float):
        return {"type": "number"}

    if template_value is None:
        return {"type": "null"}

    if isinstance(template_value, list):
        if len(template_value) == 0:
            return {"type": "array", "items": {}}
        return {
            "type": "array",
            "items": _template_value_to_json_schema(template_value[0]),
        }

    if isinstance(template_value, dict):
        properties = {}
        required = []
        for key, nested_value in template_value.items():
            properties[key] = _template_value_to_json_schema(nested_value)
            required.append(key)

        return {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        }

    if isinstance(template_value, str):
        raw_value = template_value.strip()
        if not raw_value:
            return {"type": "string"}

        if "|" in raw_value:
            enum_values = [part.strip() for part in raw_value.split("|") if part.strip()]
            if enum_values:
                return {"type": "string", "enum": enum_values}

        normalized = raw_value.lower()
        scalar_type = _SCALAR_TEMPLATE_TYPE_MAP.get(normalized)
        if scalar_type:
            return {"type": scalar_type}

        return {"type": "string"}

    return {}


def build_profile_json_schema(profile):
    response_template = profile.get("response_template", {})
    expected_fields = profile.get("expected_fields", [])

    if not isinstance(response_template, dict):
        raise ValueError("response_template do perfil deve ser um objeto JSON.")

    property_descriptions = {}
    for field in expected_fields:
        name = field.get("name")
        description = field.get("description")
        if name and description:
            property_descriptions[name] = description

    properties = {}
    required = []
    for key, template_value in response_template.items():
        field_schema = _template_value_to_json_schema(template_value)
        description = property_descriptions.get(key)
        if description and isinstance(field_schema, dict):
            field_schema["description"] = description
        properties[key] = field_schema
        required.append(key)

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": f"{profile.get('id', 'analyzer_profile')}_analysis",
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def _json_schema_to_vertex_schema(schema_node):
    if not isinstance(schema_node, dict):
        return {}

    vertex_schema = {}

    node_type = schema_node.get("type")
    if isinstance(node_type, str):
        vertex_schema["type"] = node_type.upper()

    if "description" in schema_node and isinstance(schema_node["description"], str):
        vertex_schema["description"] = schema_node["description"]

    if "enum" in schema_node and isinstance(schema_node["enum"], list):
        vertex_schema["enum"] = schema_node["enum"]

    if "properties" in schema_node and isinstance(schema_node["properties"], dict):
        properties = {}
        property_ordering = []
        for key, child_schema in schema_node["properties"].items():
            properties[key] = _json_schema_to_vertex_schema(child_schema)
            property_ordering.append(key)

        vertex_schema["properties"] = properties
        if property_ordering:
            vertex_schema["propertyOrdering"] = property_ordering

    if "required" in schema_node and isinstance(schema_node["required"], list):
        vertex_schema["required"] = schema_node["required"]

    if "items" in schema_node:
        vertex_schema["items"] = _json_schema_to_vertex_schema(schema_node["items"])

    if schema_node.get("nullable") is True:
        vertex_schema["nullable"] = True

    return vertex_schema


def build_profile_vertex_response_schema(profile):
    json_schema = build_profile_json_schema(profile)
    return _json_schema_to_vertex_schema(json_schema)

