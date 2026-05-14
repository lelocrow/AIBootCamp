# AI Bootcamp Analyzer Template

Template full-stack para bootcamp com Google Cloud, pronto para cada participante clonar, personalizar e publicar na propria conta GCP.

## O que este projeto faz

- Frontend React para upload de PDF
- Backend Flask para fila de processamento assincrono
- Analise de documento com Vertex AI (Gemini)
- Deploy em Cloud Run

## Resultado esperado para cada participante

Ao final, cada participante tera:
- Um servico Cloud Run proprio
- Configuracao propria de projeto/bucket/modelo
- Um perfil de analisador escolhido (ou customizado)
- Endpoint funcionando com `/api/health`, `/api/config` e `/api/analyze`

## 1) Pre-requisitos (obrigatorio)

Instalar e validar localmente:

- `git`
- `gcloud` (Google Cloud CLI)
- Conta GCP com permissao para Cloud Run, Cloud Build, Artifact Registry, Vertex AI e Cloud Storage

Comandos de validacao:

```bash
git --version
gcloud --version
```

## 2) Clonar o repositorio

### Opcao A: HTTPS

```bash
git clone <URL_DO_REPOSITORIO>
cd AIBootCamp
```

### Opcao B: SSH

```bash
git clone <URL_SSH_DO_REPOSITORIO>
cd AIBootCamp
```

Validacao:

```bash
ls
```

Voce deve ver: `backend`, `frontend`, `README.md`, `cloudrun.env.example`, `Dockerfile`.

Validacao de assets do layout:

```bash
ls frontend/public/assets
```

Voce deve ver pelo menos:
- `gemini.png`
- `gcloud.png`
- `logo-servinformacion.png`

## 3) Preparar a conta GCP do participante

> Execute estes comandos com os valores da conta do proprio participante.
> Recomendacao: use Cloud Shell (bash) para copiar os comandos exatamente como estao abaixo.

### 3.1 Login no Google Cloud

```bash
gcloud auth login
gcloud auth application-default login
```

### 3.2 Definir variaveis base

Ajuste os valores conforme o participante:

```bash
PROJECT_ID="seu-project-id"
REGION="us-central1"
REPO_NAME="bootcamp-images"
BUCKET_NAME="seu-bucket-unico-bootcamp"
SERVICE_NAME="ai-bootcamp-analyzer"
IMAGE_NAME="ai-bootcamp-analyzer"
```

Se estiver no Windows PowerShell, use:

```powershell
$PROJECT_ID="seu-project-id"
$REGION="us-central1"
$REPO_NAME="bootcamp-images"
$BUCKET_NAME="seu-bucket-unico-bootcamp"
$SERVICE_NAME="ai-bootcamp-analyzer"
$IMAGE_NAME="ai-bootcamp-analyzer"
```

### 3.3 Apontar gcloud para o projeto

```bash
gcloud config set project "$PROJECT_ID"
```

### 3.4 Habilitar APIs necessarias

```bash
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com aiplatform.googleapis.com storage.googleapis.com
```

### 3.5 Criar repositorio do Artifact Registry

```bash
gcloud artifacts repositories create "$REPO_NAME" --repository-format=docker --location="$REGION" --description="Bootcamp Docker images"
```

Se o repositorio ja existir, pode ignorar o erro.

### 3.6 Criar bucket de upload de PDFs

```bash
gcloud storage buckets create "gs://$BUCKET_NAME" --location="$REGION" --uniform-bucket-level-access
```

Se o bucket ja existir, ajuste para um nome unico e tente novamente.

## 4) Configurar o arquivo de ambiente do participante

### 4.1 Criar `cloudrun.env`

Linux/macOS:

```bash
cp cloudrun.env.example cloudrun.env
```

Windows PowerShell:

```powershell
Copy-Item cloudrun.env.example cloudrun.env
```

### 4.2 Editar `cloudrun.env`

Preencha sem deixar placeholders:

```env
BOOTCAMP_ORG_NAME=Empresa_Convidada
BOOTCAMP_PARTICIPANT_NAME=Nome_Sobrenome
SERVICE_NAME=ai-bootcamp-analyzer
ANALYZER_PROFILE_ID=contract_risk_guard

VERTEX_PROJECT_ID=seu-project-id-gcp
VERTEX_LOCATION=us-central1
GCS_BUCKET_NAME=seu-bucket-unico-para-pdfs
GEMINI_MODEL_NAME=gemini-2.5-flash

GCS_UPLOAD_PREFIX=uploads
MAX_UPLOAD_SIZE_MB=25
MAX_QUEUE_SIZE=20
MAX_STORED_JOBS=300
JOB_RETENTION_SECONDS=3600
MAX_OUTPUT_TOKENS=8192
GENERATION_TEMPERATURE=0.1
PROMPT_REFERENCE_TIMEZONE=America/Sao_Paulo
```

### 4.3 Validacao obrigatoria antes do deploy

Confirme:
- `SERVICE_NAME` no arquivo = nome que voce usara no comando `gcloud run deploy`
- `VERTEX_PROJECT_ID` = mesmo `PROJECT_ID` configurado no gcloud
- `GCS_BUCKET_NAME` = bucket criado na etapa 3.6
- `ANALYZER_PROFILE_ID` = um perfil existente em `backend/analyzer_profiles.py`
- `PROMPT_REFERENCE_TIMEZONE` = timezone valida (ex.: `America/Sao_Paulo`) para ancorar a data real no prompt da IA

### 4.4 Logo obrigatoria da empresa convidada

Cada empresa convidada deve fornecer sua logo com o nome exato `logo.png`.

Local obrigatorio:
- `frontend/public/assets/logo.png`

Comandos para copiar a logo:

Linux/macOS:

```bash
cp /caminho/da/sua/logo.png frontend/public/assets/logo.png
```

Windows PowerShell:

```powershell
Copy-Item C:\caminho\da\sua\logo.png frontend\public\assets\logo.png
```

Se `logo.png` nao estiver nesse caminho, o layout mostra um placeholder `LOGO` no topo.

Perfis prontos:
- `contract_risk_guard`
- `invoice_audit_assistant`
- `resume_screening_copilot`
- `support_ticket_triage`
- `policy_compliance_reviewer`
- `customizado` (perfil base para criar manualmente seu proprio analisador)

## 5) Build e push da imagem para Artifact Registry

Linux/macOS (bash):

```bash
TAG="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${IMAGE_NAME}:latest"
echo "$TAG"
gcloud builds submit --tag "$TAG"
```

Windows PowerShell:

```powershell
$TAG = "{0}-docker.pkg.dev/{1}/{2}/{3}:latest" -f $REGION, $PROJECT_ID, $REPO_NAME, $IMAGE_NAME
Write-Output $TAG
gcloud builds submit --tag $TAG
```

## 6) Deploy no Cloud Run

Use o mesmo `SERVICE_NAME` definido no `cloudrun.env`.

Linux/macOS (bash):

```bash
gcloud run deploy "$SERVICE_NAME" --image "$TAG" --region "$REGION" --platform managed --allow-unauthenticated --port 8080 --cpu 2 --memory 2Gi --concurrency 20 --min-instances 0 --max-instances 1 --no-cpu-throttling --timeout 3600 --env-vars-file cloudrun.env
```

Windows PowerShell:

```powershell
gcloud run deploy $SERVICE_NAME --image $TAG --region $REGION --platform managed --allow-unauthenticated --port 8080 --cpu 2 --memory 2Gi --concurrency 20 --min-instances 0 --max-instances 1 --no-cpu-throttling --timeout 3600 --env-vars-file cloudrun.env
```

Observacao importante:
- Este projeto usa fila em memoria no proprio container.
- Mantenha `--max-instances=1` para evitar inconsistencias de estado entre instancias.

## 7) Validacao pos-deploy

### 8.1 Obter URL do servico

```bash
SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" --region "$REGION" --format='value(status.url)')
echo "$SERVICE_URL"
```

Windows PowerShell:

```powershell
$SERVICE_URL=gcloud run services describe $SERVICE_NAME --region $REGION --format="value(status.url)"
Write-Output $SERVICE_URL
```

### 8.2 Testar endpoints no Cloud Run

```bash
curl "$SERVICE_URL/api/health"
curl "$SERVICE_URL/api/config"
```

### 8.3 Teste funcional completo

1. Abrir `SERVICE_URL` no navegador.
2. Fazer upload de um PDF.
3. Confirmar que a analise termina e retorna JSON.

## 8) Onde personalizar prompt e campos esperados

Arquivos principais:
- Prompt, schema e perfis: `backend/analyzer_profiles.py`
- Carregamento de env e perfil ativo: `backend/main.py`
- Exibicao didatica de prompt/campos na interface: `frontend/src/App.jsx`

## 9) Erros comuns e como corrigir

### Erro: `403` em Vertex AI

Causa comum: projeto errado ou API nao habilitada.

Correcao:
- revisar `VERTEX_PROJECT_ID`
- executar novamente `gcloud config set project ...`
- garantir `aiplatform.googleapis.com` habilitada

### Erro: bucket nao encontrado

Causa comum: `GCS_BUCKET_NAME` diferente do bucket criado.

Correcao:
- conferir nome exato no `cloudrun.env`
- conferir se bucket existe: `gcloud storage ls`

### Erro: `ANALYZER_PROFILE_ID` invalido

Causa comum: id digitado incorretamente.

Correcao:
- usar um dos ids listados na secao de perfis
- validar em `/api/config` qual perfil ficou ativo

### Erro: timeout durante analise

Causa comum: PDF muito pesado ou modelo demorando resposta.

Correcao:
- testar com arquivo menor
- revisar limite `MAX_UPLOAD_SIZE_MB`

## 10) Checklist final do participante

1. Clonei o repositorio e entrei na pasta correta.
2. Configurei `PROJECT_ID`, `REGION`, `REPO_NAME`, `BUCKET_NAME`.
3. Habilitei as APIs necessarias.
4. Criei Artifact Registry e bucket.
5. Criei e preenchi `cloudrun.env` sem placeholders.
6. Validei `/api/config` na URL publica.
7. Fiz build/push da imagem.
8. Fiz deploy no Cloud Run.
9. Testei `/api/health` e `/api/config` na URL publica.
10. Executei upload de PDF com sucesso.
