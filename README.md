# AI Bootcamp Analyzer Template

Template full-stack para bootcamp com Google Cloud: cada participante clona, configura com a prÃƒÂ³pria conta GCP, escolhe um perfil de analisador por IA e faz deploy no prÃƒÂ³prio Cloud Run.

## Objetivo do bootcamp

Ao final da atividade, cada participante terÃƒÂ¡:
- 1 serviÃƒÂ§o Cloud Run prÃƒÂ³prio
- 1 bucket prÃƒÂ³prio para PDFs
- 1 banco Postgres no Cloud SQL prÃƒÂ³prio
- 1 analisador de documentos por IA com perfil configurÃƒÂ¡vel
- persistÃƒÂªncia das anÃƒÂ¡lises no Postgres com validaÃƒÂ§ÃƒÂ£o de schema antes de gravar

## Arquitetura resumida

- Frontend: React (upload de PDF e exibiÃƒÂ§ÃƒÂ£o da anÃƒÂ¡lise)
- Backend: Flask (fila em memÃƒÂ³ria + integraÃƒÂ§ÃƒÂ£o com Vertex AI e Cloud Storage)
- IA: Gemini no Vertex AI
- Dados: Cloud Storage (arquivo PDF) + Cloud SQL Postgres (resultado estruturado)

## Como garantimos consistÃƒÂªncia dos campos da IA

Este projeto aplica 3 camadas de proteÃƒÂ§ÃƒÂ£o antes de salvar no banco:

1. `response_schema` enviado ao Gemini (estrutura esperada na origem)
2. validaÃƒÂ§ÃƒÂ£o JSON Schema no backend (por perfil)
3. tentativa automÃƒÂ¡tica de reparo de JSON/schema quando a primeira resposta vem fora do formato

Somente payload vÃƒÂ¡lido segue para persistÃƒÂªncia.

## EstratÃƒÂ©gia de banco para perfis diferentes

Como cada perfil pode ter campos distintos, o banco usa:
- colunas fixas de metadados (job, perfil, status, datas etc.)
- `analysis_json` (JSONB) para os campos dinÃƒÂ¢micos da anÃƒÂ¡lise

Assim, vocÃƒÂª troca de perfil sem quebrar o schema relacional.

## 1) PrÃƒÂ©-requisitos

Instale e valide:

- `git`
- `gcloud` (Google Cloud CLI)
- permissÃƒÂ£o GCP para: Cloud Run, Cloud Build, Artifact Registry, Vertex AI, Cloud Storage e Cloud SQL

ValidaÃƒÂ§ÃƒÂ£o:

```bash
git --version
gcloud --version
```

## 2) Clonar o repositÃƒÂ³rio

```bash
git clone https://github.com/lelocrow/AIBootCamp.git
cd AIBootCamp
```

Validar estrutura:

```bash
ls
```

VocÃƒÂª deve ver: `backend`, `frontend`, `README.md`, `cloudrun.env.example`, `Dockerfile`.

## 3) Definir variÃƒÂ¡veis do terminal

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

Se jÃƒÂ¡ existir, pode ignorar o erro.

### 4.4 Criar bucket para PDFs

```bash
gcloud storage buckets create "gs://$BUCKET_NAME" --location="$REGION" --uniform-bucket-level-access
```

## 5) Criar Cloud SQL Postgres

### 5.1 Criar instÃƒÂ¢ncia Postgres

```bash
gcloud sql instances create "$SQL_INSTANCE_NAME" --database-version=POSTGRES_16 --tier=db-custom-1-3840 --region="$REGION" --storage-size=10 --storage-auto-increase
```

### 5.2 Criar database

```bash
gcloud sql databases create "$DB_NAME" --instance="$SQL_INSTANCE_NAME"
```

### 5.3 Criar usuÃƒÂ¡rio

```bash
gcloud sql users create "$DB_USER" --instance="$SQL_INSTANCE_NAME" --password="$DB_PASS"
```

### 5.4 Obter connection name da instÃƒÂ¢ncia

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

### 5.5 Dar permissÃƒÂ£o Cloud SQL Client para o runtime do Cloud Run

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

### 6.2 Preencher valores obrigatÃƒÂ³rios

Exemplo mÃƒÂ­nimo recomendado:

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

### 6.3 Logo obrigatÃƒÂ³ria da empresa convidada

Coloque a logo no caminho abaixo com nome exato:

- `frontend/public/assets/logo.png`

Se nÃƒÂ£o existir, o topo mostra o placeholder `LOGO`.

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

### 7.2 Submeter build

```bash
gcloud builds submit --tag "$TAG"
```

## 8) Deploy no Cloud Run

```bash
gcloud run deploy "$SERVICE_NAME" --image "$TAG" --region "$REGION" --platform managed --allow-unauthenticated --port 8080 --cpu 2 --memory 2Gi --concurrency 20 --min-instances 0 --max-instances 1 --no-cpu-throttling --timeout 3600 --env-vars-file cloudrun.env --add-cloudsql-instances "$CLOUDSQL_INSTANCE_CONNECTION_NAME"
```

ObservaÃƒÂ§ÃƒÂ£o importante:
- este projeto usa fila em memÃƒÂ³ria no container
- mantenha `--max-instances=1` para evitar inconsistÃƒÂªncias entre instÃƒÂ¢ncias

## 9) ValidaÃƒÂ§ÃƒÂ£o pÃƒÂ³s-deploy

### 9.1 URL do servico (opcional)

A URL ja aparece automaticamente no final do comando `gcloud run deploy`.

Se precisar consultar depois, rode:

```bash
gcloud run services describe "$SERVICE_NAME" --region "$REGION" --format='value(status.url)'
```

Copie a URL e teste:

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
3. Aguarde a anÃƒÂ¡lise finalizar.
4. Confirme retorno na UI.
5. Confirme no `/api/postgres/health` que o Postgres estÃƒÂ¡ ativo.

## 10) Perfis de analisador disponÃƒÂ­veis

Defina em `ANALYZER_PROFILE_ID`:

- `contract_risk_guard`
- `invoice_audit_assistant`
- `resume_screening_copilot`
- `support_ticket_triage`
- `policy_compliance_reviewer`
- `customizado`

Arquivo para customizaÃƒÂ§ÃƒÂ£o completa:
- `backend/analyzer_profiles.py`

## 11) Principais pontos de customizaÃƒÂ§ÃƒÂ£o por participante/empresa

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

Causa comum: `TAG` montada com variÃƒÂ¡vel vazia (ex.: `IMAGE_NAME` vazio).

CorreÃƒÂ§ÃƒÂ£o:
- valide `PROJECT_ID`, `REGION`, `REPO_NAME`, `IMAGE_NAME`
- imprima a TAG antes de executar o build

### Erro de conexÃƒÂ£o com Postgres no Cloud Run

Causas comuns:
- faltou `--add-cloudsql-instances` no deploy
- `CLOUDSQL_INSTANCE_CONNECTION_NAME` incorreto
- service account sem `roles/cloudsql.client`

### Erro de configuraÃƒÂ§ÃƒÂ£o no backend

Revise `cloudrun.env` e compare com `cloudrun.env.example`.

## 13) Checklist final do participante

1. Clonei o repositÃƒÂ³rio e entrei em `AIBootCamp`.
2. Configurei variÃƒÂ¡veis de terminal (`PROJECT_ID`, `REGION` etc.).
3. Habilitei APIs obrigatÃƒÂ³rias (incluindo `sqladmin.googleapis.com`).
4. Criei Artifact Registry, bucket e Cloud SQL Postgres.
5. Preenchi `cloudrun.env` com dados da minha conta.
6. Coloquei `frontend/public/assets/logo.png`.
7. Build da imagem concluÃƒÂ­do.
8. Deploy no Cloud Run concluÃƒÂ­do com Cloud SQL conectado.
9. `/api/health`, `/api/config` e `/api/postgres/health` respondendo.
10. Upload e anÃƒÂ¡lise de PDF funcionando na UI.