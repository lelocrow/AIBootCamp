# AI Bootcamp Analyzer Template

Template full-stack para bootcamp com Google Cloud: cada participante clona, configura com a propria conta GCP, escolhe um perfil de analisador por IA e faz deploy no proprio Cloud Run.

## Objetivo do bootcamp

Ao final da atividade, cada participante tera:
- 1 servico Cloud Run proprio
- 1 bucket proprio para PDFs
- 1 banco Postgres no Cloud SQL proprio
- 1 analisador de documentos por IA com perfil configuravel
- persistencia das analises no Postgres com validacao de schema antes de gravar

## Arquitetura resumida

- Frontend: React (upload de PDF e exibicao da analise)
- Backend: Flask (fila em memoria + integracao com Vertex AI e Cloud Storage)
- IA: Gemini no Vertex AI
- Dados: Cloud Storage (arquivo PDF) + Cloud SQL Postgres (resultado estruturado)

## Como garantimos consistencia dos campos da IA

Este projeto aplica 3 camadas de protecao antes de salvar no banco:

1. `response_schema` enviado ao Gemini (estrutura esperada na origem)
2. validacao JSON Schema no backend (por perfil)
3. tentativa automatica de reparo de JSON/schema quando a primeira resposta vem fora do formato

Somente payload valido segue para persistencia.

## Estrategia de banco para perfis diferentes

Como cada perfil pode ter campos distintos, o banco usa:
- colunas fixas de metadados (job, perfil, status, datas, etc.)
- `analysis_json` (JSONB) para os campos dinamicos da analise

Assim, voce troca de perfil sem quebrar o schema relacional.

## 1) Pre-requisitos

Instale e valide:

- `git`
- `gcloud` (Google Cloud CLI)
- permissao GCP para: Cloud Run, Cloud Build, Artifact Registry, Vertex AI, Cloud Storage, Cloud SQL

Validacao:

```bash
git --version
gcloud --version
```

## 2) Clonar o repositorio

```bash
git clone https://github.com/lelocrow/AIBootCamp.git
cd AIBootCamp
```

Validar estrutura:

```bash
ls
```

Voce deve ver: `backend`, `frontend`, `README.md`, `cloudrun.env.example`, `Dockerfile`.

## 3) Definir variaveis do terminal

### Bash (Linux/macOS/Cloud Shell)

```bash
PROJECT_ID="seu-project-id"
REGION="us-central1"
REPO_NAME="bootcamp-images"
IMAGE_NAME="ai-bootcamp-analyzer"
SERVICE_NAME="ai-bootcamp-analyzer"
BUCKET_NAME="seu-bucket-unico-bootcamp"
SQL_INSTANCE_NAME="bootcamp-pg"
DB_NAME="bootcamp_analyzer"
DB_USER="bootcamp_user"
DB_PASS="troque-esta-senha"
```

### PowerShell (Windows)

```powershell
$PROJECT_ID="seu-project-id"
$REGION="us-central1"
$REPO_NAME="bootcamp-images"
$IMAGE_NAME="ai-bootcamp-analyzer"
$SERVICE_NAME="ai-bootcamp-analyzer"
$BUCKET_NAME="seu-bucket-unico-bootcamp"
$SQL_INSTANCE_NAME="bootcamp-pg"
$DB_NAME="bootcamp_analyzer"
$DB_USER="bootcamp_user"
$DB_PASS="troque-esta-senha"
```

## 4) Preparar GCP do participante

### 4.1 Selecionar projeto

```bash
gcloud config set project "$PROJECT_ID"
```

### 4.2 Habilitar APIs

```bash
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com aiplatform.googleapis.com storage.googleapis.com sqladmin.googleapis.com
```

### 4.3 Criar Artifact Registry (Docker)

```bash
gcloud artifacts repositories create "$REPO_NAME" --repository-format=docker --location="$REGION" --description="Bootcamp Docker images"
```

Se ja existir, pode ignorar o erro.

### 4.4 Criar bucket para PDFs

```bash
gcloud storage buckets create "gs://$BUCKET_NAME" --location="$REGION" --uniform-bucket-level-access
```

## 5) Criar Cloud SQL Postgres (modo rapido para sala)

Observacao importante: Cloud SQL sempre usa "instancia". Para o bootcamp, use uma instancia unica pequena, apenas para laboratorio.

### 5.1 Criar instancia Postgres

```bash
gcloud sql instances create "$SQL_INSTANCE_NAME" --database-version=POSTGRES_16 --tier=db-custom-1-3840 --region="$REGION" --storage-size=10 --storage-auto-increase
```

### 5.2 Criar database

```bash
gcloud sql databases create "$DB_NAME" --instance="$SQL_INSTANCE_NAME"
```

### 5.3 Criar usuario

```bash
gcloud sql users create "$DB_USER" --instance="$SQL_INSTANCE_NAME" --password="$DB_PASS"
```

### 5.4 Obter connection name da instancia

#### Bash

```bash
CLOUDSQL_INSTANCE_CONNECTION_NAME=$(gcloud sql instances describe "$SQL_INSTANCE_NAME" --format='value(connectionName)')
echo "$CLOUDSQL_INSTANCE_CONNECTION_NAME"
```

#### PowerShell

```powershell
$CLOUDSQL_INSTANCE_CONNECTION_NAME=gcloud sql instances describe $SQL_INSTANCE_NAME --format="value(connectionName)"
Write-Output $CLOUDSQL_INSTANCE_CONNECTION_NAME
```

### 5.5 Dar permissao Cloud SQL Client para o runtime do Cloud Run

#### Bash

```bash
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
RUNTIME_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:${RUNTIME_SA}" --role="roles/cloudsql.client"
```

#### PowerShell

```powershell
$PROJECT_NUMBER=gcloud projects describe $PROJECT_ID --format="value(projectNumber)"
$RUNTIME_SA="$PROJECT_NUMBER-compute@developer.gserviceaccount.com"
gcloud projects add-iam-policy-binding $PROJECT_ID --member="serviceAccount:$RUNTIME_SA" --role="roles/cloudsql.client"
```

## 6) Configurar `cloudrun.env`

### 6.1 Criar arquivo

- Linux/macOS: `cp cloudrun.env.example cloudrun.env`
- PowerShell: `Copy-Item cloudrun.env.example cloudrun.env`

### 6.2 Preencher valores obrigatorios

Exemplo minimo recomendado:

```env
BOOTCAMP_ORG_NAME=Empresa_Convidada
BOOTCAMP_PARTICIPANT_NAME=Nome_Sobrenome
SERVICE_NAME=ai-bootcamp-analyzer
ANALYZER_PROFILE_ID=contract_risk_guard

VERTEX_PROJECT_ID=seu-project-id-gcp
VERTEX_LOCATION=us-central1
GCS_BUCKET_NAME=seu-bucket-unico-para-pdfs
GEMINI_MODEL_NAME=gemini-2.5-flash

POSTGRES_ENABLED=true
CLOUDSQL_INSTANCE_CONNECTION_NAME=seu-project:us-central1:bootcamp-pg
POSTGRES_DATABASE=bootcamp_analyzer
POSTGRES_USER=bootcamp_user
POSTGRES_PASSWORD=sua_senha
POSTGRES_PORT=5432
POSTGRES_SSLMODE=disable
POSTGRES_AUTO_CREATE_TABLES=true
POSTGRES_CONNECT_TIMEOUT_SECONDS=10

PROMPT_REFERENCE_TIMEZONE=America/Sao_Paulo
SCHEMA_REPAIR_MAX_RETRIES=1
```

### 6.3 Logo obrigatoria da empresa convidada

Coloque a logo no caminho abaixo com nome exato:

- `frontend/public/assets/logo.png`

Se nao existir, o topo mostra placeholder `LOGO`.

## 7) Build da imagem

### 7.1 Criar TAG da imagem

#### Bash

```bash
TAG="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${IMAGE_NAME}:latest"
echo "$TAG"
```

#### PowerShell

```powershell
$TAG="{0}-docker.pkg.dev/{1}/{2}/{3}:latest" -f $REGION, $PROJECT_ID, $REPO_NAME, $IMAGE_NAME
Write-Output $TAG
```

### 7.2 Validar se TAG nao ficou vazia

Se a TAG aparecer com barra no final (sem nome de imagem), revise variaveis, principalmente `IMAGE_NAME`.

### 7.3 Submeter build

```bash
gcloud builds submit --tag "$TAG"
```

## 8) Deploy no Cloud Run

```bash
gcloud run deploy "$SERVICE_NAME" --image "$TAG" --region "$REGION" --platform managed --allow-unauthenticated --port 8080 --cpu 2 --memory 2Gi --concurrency 20 --min-instances 0 --max-instances 1 --no-cpu-throttling --timeout 3600 --env-vars-file cloudrun.env --add-cloudsql-instances "$CLOUDSQL_INSTANCE_CONNECTION_NAME"
```

Observacao importante:
- este projeto usa fila em memoria no container
- mantenha `--max-instances=1` para evitar inconsistencias entre instancias

## 9) Validacao pos-deploy

### 9.1 Obter URL do servico

```bash
gcloud run services describe "$SERVICE_NAME" --region "$REGION" --format='value(status.url)'
```

Copie a URL retornada e teste:

- `/api/health`
- `/api/config`
- `/api/postgres/health`

Exemplo:

```text
https://SEU-SERVICO.run.app/api/health
https://SEU-SERVICO.run.app/api/config
https://SEU-SERVICO.run.app/api/postgres/health
```

### 9.2 Teste funcional

1. Abra a URL principal no navegador.
2. Envie um PDF.
3. Aguarde a analise finalizar.
4. Confirme retorno na UI.
5. Confirme no `/api/postgres/health` que o Postgres esta ativo.

## 10) Perfis de analisador disponiveis

Defina em `ANALYZER_PROFILE_ID`:

- `contract_risk_guard`
- `invoice_audit_assistant`
- `resume_screening_copilot`
- `support_ticket_triage`
- `policy_compliance_reviewer`
- `customizado`

Arquivo para customizacao completa:
- `backend/analyzer_profiles.py`

## 11) Principais pontos de customizacao por participante/empresa

- identidade visual e texto:
  - `BOOTCAMP_ORG_NAME`
  - `BOOTCAMP_PARTICIPANT_NAME`
  - `frontend/public/assets/logo.png`
- GCP do participante:
  - `VERTEX_PROJECT_ID`
  - `GCS_BUCKET_NAME`
  - `CLOUDSQL_INSTANCE_CONNECTION_NAME`
  - credenciais Postgres
- comportamento do analisador:
  - `ANALYZER_PROFILE_ID`
  - `backend/analyzer_profiles.py` (prompt, campos esperados e template)

## 12) Erros comuns

### Erro no build: `invalid reference format`

Causa comum: `TAG` montada com variavel vazia (ex.: `IMAGE_NAME` vazio).

Correcao:
- valide `PROJECT_ID`, `REGION`, `REPO_NAME`, `IMAGE_NAME`
- imprima a TAG antes de executar o build

### Erro de conexao com Postgres no Cloud Run

Causas comuns:
- faltou `--add-cloudsql-instances` no deploy
- `CLOUDSQL_INSTANCE_CONNECTION_NAME` incorreto
- service account sem `roles/cloudsql.client`

### Erro de configuracao no backend

Revise `cloudrun.env` e compare com `cloudrun.env.example`.

## 13) Checklist final do participante

1. Clonei o repositorio e entrei em `AIBootCamp`.
2. Configurei variaveis de terminal (`PROJECT_ID`, `REGION`, etc.).
3. Habilitei APIs obrigatorias (incluindo `sqladmin.googleapis.com`).
4. Criei Artifact Registry, bucket e Cloud SQL Postgres.
5. Preenchi `cloudrun.env` com dados da minha conta.
6. Coloquei `frontend/public/assets/logo.png`.
7. Build da imagem concluido.
8. Deploy no Cloud Run concluido com Cloud SQL conectado.
9. `/api/health`, `/api/config` e `/api/postgres/health` respondendo.
10. Upload e analise de PDF funcionando na UI.
