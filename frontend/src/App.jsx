import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useDropzone } from "react-dropzone";
import { LoadingSkeleton } from "./components";
import "./app.css";

const MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024;
const POLL_INTERVAL_MS = 2500;
const POLL_TIMEOUT_MS = 4 * 60 * 1000;
const REQUEST_TIMEOUT_MS = 30 * 1000;

const ASSET_BASE_PATH = `${process.env.PUBLIC_URL || ""}/assets`;
const BOOTCAMP_LOGO_SRC = `${ASSET_BASE_PATH}/logo.png`;
const GEMINI_LOGO_SRC = `${ASSET_BASE_PATH}/gemini.png`;
const GCLOUD_LOGO_SRC = `${ASSET_BASE_PATH}/gcloud.png`;
const POWERED_BY_LOGO_SRC = `${ASSET_BASE_PATH}/logo-servinformacion.png`;

function parseResponseJson(text) {
  if (!text) {
    return {};
  }

  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

function getErrorByType(type, messageOverride) {
  const catalog = {
    invalid_file: {
      title: "Arquivo invalido",
      message: "Selecione apenas um PDF valido para continuar.",
    },
    file_too_large: {
      title: "Arquivo muito grande",
      message: "O PDF excede o limite permitido para processamento.",
    },
    timeout: {
      title: "Tempo de processamento excedido",
      message: "A analise demorou alem do esperado. Tente novamente com um arquivo menor.",
    },
    queue_full: {
      title: "Fila de processamento cheia",
      message: "O servico esta com alta demanda no momento. Aguarde alguns segundos e tente novamente.",
    },
    api_unavailable: {
      title: "API indisponivel",
      message: "Nao foi possivel conectar ao servico agora. Verifique a conexao e tente novamente.",
    },
    processing_error: {
      title: "Falha no processamento",
      message: "Ocorreu um erro durante a analise do documento.",
    },
    parse_error: {
      title: "Falha na leitura do resultado",
      message: "A resposta da IA nao pode ser interpretada corretamente.",
    },
    dependency_error: {
      title: "Dependencia indisponivel",
      message: "O servico esta sem dependencias necessarias para analisar o arquivo.",
    },
    configuration_error: {
      title: "Configuracao incompleta",
      message: "Preencha as variaveis de ambiente obrigatorias antes de processar o arquivo.",
    },
    server_error: {
      title: "Erro interno no servidor",
      message: "O servidor encontrou um erro inesperado.",
    },
    not_found: {
      title: "Job nao encontrado",
      message: "A referencia da analise expirou ou nao foi encontrada.",
    },
    unknown: {
      title: "Erro inesperado",
      message: "Nao foi possivel concluir a operacao.",
    },
  };

  const base = catalog[type] || catalog.unknown;
  return {
    type,
    title: base.title,
    message: messageOverride || base.message,
  };
}

function prettyKey(key) {
  if (!key || typeof key !== "string") {
    return "Campo";
  }

  return key
    .split("_")
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function renderValue(value) {
  if (value === null || value === undefined) {
    return <span className="app-value-empty">null</span>;
  }

  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return <p className="text-body-sm text-on-surface-variant whitespace-pre-wrap">{String(value)}</p>;
  }

  return <pre className="app-code-preview">{JSON.stringify(value, null, 2)}</pre>;
}

async function fetchWithTimeout(url, options = {}, timeoutMs = REQUEST_TIMEOUT_MS) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timeoutId);
  }
}

function getJobErrorInfo(jobData) {
  return getErrorByType(jobData?.error_type || "processing_error", jobData?.error_message);
}

function AnalysisCards({ analysis }) {
  const entries = Object.entries(analysis || {});

  if (entries.length === 0) {
    return (
      <div className="text-body-sm text-on-surface-variant">
        <p>A IA retornou um objeto vazio para este documento.</p>
      </div>
    );
  }

  return (
    <div className="app-result-grid">
      {entries.map(([key, value]) => (
        <article key={key} className="bg-surface border border-outline-variant rounded-lg p-4">
          <h4 className="text-body-md font-semibold text-on-surface mb-2">{prettyKey(key)}</h4>
          {renderValue(value)}
        </article>
      ))}
    </div>
  );
}

export default function App() {
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [job, setJob] = useState(null);
  const [bootcampConfig, setBootcampConfig] = useState(null);
  const [showBootcampLogo, setShowBootcampLogo] = useState(true);
  const [showPoweredByLogo, setShowPoweredByLogo] = useState(true);

  const pollStartedAtRef = useRef(null);
  const pollRequestInFlightRef = useRef(false);

  const resetAnalysisState = useCallback(() => {
    setResult(null);
    setError(null);
    setJob(null);
    setLoading(false);
    pollStartedAtRef.current = null;
    pollRequestInFlightRef.current = false;
  }, []);

  const loadRuntimeConfig = useCallback(async () => {
    try {
      const response = await fetchWithTimeout("/api/config", {}, REQUEST_TIMEOUT_MS);
      const payload = parseResponseJson(await response.text());

      if (!response.ok || !payload?.success) {
        return;
      }

      setBootcampConfig(payload.config);
    } catch {
      // A pagina continua funcional mesmo sem config.
    }
  }, []);

  useEffect(() => {
    loadRuntimeConfig();
  }, [loadRuntimeConfig]);

  const onDropAccepted = useCallback((acceptedFiles) => {
    if (acceptedFiles.length === 0) {
      return;
    }

    setFile(acceptedFiles[0]);
    setResult(null);
    setError(null);
    setJob(null);
  }, []);

  const onDropRejected = useCallback((fileRejections) => {
    const firstError = fileRejections?.[0]?.errors?.[0];

    if (!firstError) {
      setError(getErrorByType("invalid_file"));
      return;
    }

    if (firstError.code === "file-too-large") {
      setError(
        getErrorByType(
          "file_too_large",
          `O limite atual e ${(MAX_FILE_SIZE_BYTES / 1024 / 1024).toFixed(0)}MB por arquivo.`
        )
      );
      return;
    }

    if (firstError.code === "file-invalid-type") {
      setError(getErrorByType("invalid_file", "Somente arquivos PDF sao aceitos."));
      return;
    }

    if (firstError.code === "too-many-files") {
      setError(getErrorByType("invalid_file", "Envie apenas um arquivo por analise."));
      return;
    }

    setError(getErrorByType("invalid_file", firstError.message));
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDropAccepted,
    onDropRejected,
    accept: { "application/pdf": [".pdf"] },
    maxFiles: 1,
    maxSize: MAX_FILE_SIZE_BYTES,
  });

  const handleBackendError = useCallback((status, payload, fallbackMessage) => {
    if (status === 503) {
      return getErrorByType("api_unavailable");
    }

    if (status === 408 || status === 504) {
      return getErrorByType("timeout");
    }

    if (payload && typeof payload === "object") {
      return getErrorByType(payload.error_type || "processing_error", payload.error || payload.message);
    }

    return getErrorByType("server_error", fallbackMessage);
  }, []);

  const fetchResult = useCallback(
    async (jobId) => {
      const response = await fetchWithTimeout(`/api/analyze/${jobId}/result`, {}, REQUEST_TIMEOUT_MS);
      const payload = parseResponseJson(await response.text());

      if (response.status === 202) {
        return false;
      }

      if (!response.ok || !payload?.success) {
        throw handleBackendError(response.status, payload, "Nao foi possivel obter o resultado da analise.");
      }

      setResult(payload);
      setLoading(false);
      setJob(payload.job || null);
      return true;
    },
    [handleBackendError]
  );

  const pollJobStatus = useCallback(async () => {
    if (!job?.job_id || pollRequestInFlightRef.current) {
      return;
    }

    if (!pollStartedAtRef.current) {
      pollStartedAtRef.current = Date.now();
    }

    if (Date.now() - pollStartedAtRef.current > POLL_TIMEOUT_MS) {
      setError(getErrorByType("timeout"));
      setLoading(false);
      setJob(null);
      return;
    }

    pollRequestInFlightRef.current = true;

    try {
      const response = await fetchWithTimeout(`/api/analyze/${job.job_id}/status`, {}, REQUEST_TIMEOUT_MS);
      const payload = parseResponseJson(await response.text());

      if (!response.ok || !payload?.success) {
        throw handleBackendError(response.status, payload, "Nao foi possivel consultar o status da analise.");
      }

      const nextJob = payload.job || null;
      if (nextJob) {
        setJob(nextJob);
      }

      if (nextJob?.status === "failed") {
        setError(getJobErrorInfo(nextJob));
        setLoading(false);
        return;
      }

      if (nextJob?.status === "completed") {
        await fetchResult(job.job_id);
      }
    } catch (err) {
      if (err?.name === "AbortError") {
        setError(getErrorByType("timeout"));
      } else if (err?.type && err?.title) {
        setError(err);
      } else {
        setError(getErrorByType("api_unavailable"));
      }
      setLoading(false);
    } finally {
      pollRequestInFlightRef.current = false;
    }
  }, [fetchResult, handleBackendError, job]);

  useEffect(() => {
    if (!loading || !job?.job_id) {
      return undefined;
    }

    pollJobStatus();
    const intervalId = setInterval(pollJobStatus, POLL_INTERVAL_MS);

    return () => {
      clearInterval(intervalId);
    };
  }, [loading, job?.job_id, pollJobStatus]);

  const handleAnalyze = async () => {
    if (!file) {
      return;
    }

    setLoading(true);
    setResult(null);
    setError(null);
    pollStartedAtRef.current = Date.now();

    let enqueueSucceeded = false;

    try {
      const formData = new FormData();
      formData.append("file", file);

      const response = await fetchWithTimeout(
        "/api/analyze",
        {
          method: "POST",
          body: formData,
        },
        REQUEST_TIMEOUT_MS
      );

      const payload = parseResponseJson(await response.text());
      if (!response.ok || !payload?.success) {
        throw handleBackendError(response.status, payload, "Nao foi possivel iniciar a analise.");
      }

      if (!payload?.job?.job_id) {
        throw getErrorByType("server_error", "A API nao retornou o identificador do job.");
      }

      enqueueSucceeded = true;
      setJob(payload.job);
    } catch (err) {
      if (err?.name === "AbortError") {
        setError(getErrorByType("timeout", "O servidor demorou para responder ao iniciar a analise."));
      } else if (err?.type && err?.title) {
        setError(err);
      } else {
        setError(getErrorByType("api_unavailable"));
      }
    } finally {
      if (!enqueueSucceeded) {
        setLoading(false);
      }
    }
  };

  const handleReset = () => {
    setFile(null);
    resetAnalysisState();
  };

  const analyzerInfo = bootcampConfig?.analyzer || null;
  const warnings = bootcampConfig?.warnings || [];

  const responseTemplatePreview = useMemo(() => {
    if (!analyzerInfo?.response_template) {
      return "{}";
    }
    return JSON.stringify(analyzerInfo.response_template, null, 2);
  }, [analyzerInfo]);

  return (
    <div className="bg-background text-on-background min-h-screen flex flex-col">
      <nav className="bg-primary-container text-on-primary-container border-b border-outline-variant shadow-sm w-full z-50">
        <div className="flex justify-between items-center w-full px-margin-mobile md:px-margin-desktop py-4 max-w-max-width mx-auto">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-3">
              <div className="h-12 w-12 rounded-lg bg-surface-container-high overflow-hidden flex items-center justify-center">
                {showBootcampLogo ? (
                  <img
                    alt="Logo da empresa do bootcamp"
                    className="h-12 w-12 object-contain"
                    src={BOOTCAMP_LOGO_SRC}
                    onError={() => setShowBootcampLogo(false)}
                  />
                ) : (
                  <span className="text-label-md text-on-primary-container/70">LOGO</span>
                )}
              </div>
              <div className="flex flex-col border-l border-on-primary-container/20 pl-3">
                <span className="text-headline-md font-bold tracking-tight text-on-primary-container">
                  {bootcampConfig?.organization_name || "AI Boot Camp"}
                </span>
                <span className="text-label-md text-on-primary-container/70 uppercase tracking-widest">
                  Powered by Gemini
                </span>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <button className="transition-transform text-on-primary-container/70 hover:text-on-primary-container" type="button" aria-label="Notificacoes">
              <span className="material-symbols-outlined">notifications</span>
            </button>
            <button className="transition-transform text-on-primary-container/70 hover:text-on-primary-container" type="button" aria-label="Perfil">
              <span className="material-symbols-outlined">account_circle</span>
            </button>
          </div>
        </div>
      </nav>

      <main className="flex-grow flex flex-col items-center px-margin-mobile md:px-margin-desktop py-xl w-full max-w-max-width mx-auto gap-6">
        {!result && (
          <>
            <section className="w-full max-w-3xl">
              <div
                {...getRootProps()}
                className={`bg-surface-container-lowest border border-outline-variant border-dashed rounded-xl p-xl flex flex-col items-center justify-center text-center shadow-sm hover:shadow-md transition-shadow duration-300 group cursor-pointer ${
                  isDragActive ? "ring-2 ring-secondary" : ""
                }`}
              >
                <input {...getInputProps()} />
                <div className="h-16 w-16 bg-surface-container rounded-full flex items-center justify-center mb-6 group-hover:bg-secondary-container group-hover:text-on-secondary-container transition-colors duration-300">
                  <span className="material-symbols-outlined text-headline-lg" style={{ fontVariationSettings: '"FILL" 0' }}>
                    {file ? "description" : "upload_file"}
                  </span>
                </div>
                <h2 className="text-headline-md font-bold text-primary mb-2">UPLOAD</h2>
                {file ? (
                  <>
                    <p className="text-body-lg text-on-surface-variant mb-2">{file.name}</p>
                    <p className="text-body-md text-on-surface-variant mb-4">
                      {(file.size / 1024 / 1024).toFixed(2)} MB · pronto para analise
                    </p>
                  </>
                ) : (
                  <p className="text-body-lg text-on-surface-variant mb-6">
                    Arraste e solte um arquivo PDF aqui
                    <br />
                    <span className="text-body-md">ou clique para selecionar</span>
                  </p>
                )}
                <span className="inline-flex items-center px-4 py-2 rounded-full bg-surface-container-high text-on-surface-variant text-label-md">
                  Limite de 50MB · 1 arquivo por analise
                </span>
              </div>

              {file && !loading && (
                <div className="flex justify-center mt-5">
                  <button
                    className="bg-secondary text-on-secondary px-6 py-3 rounded-full text-body-md font-semibold hover:opacity-90 transition"
                    onClick={handleAnalyze}
                    type="button"
                  >
                    Iniciar analise
                  </button>
                </div>
              )}

              {loading && (
                <div className="mt-5">
                  <LoadingSkeleton stage={job?.stage} progress={job?.progress} />
                </div>
              )}

              {error && (
                <div className="app-error-box" role="alert">
                  <strong>{error.title}</strong>
                  <p>{error.message}</p>
                </div>
              )}
            </section>

            <section className="w-full max-w-4xl pt-lg border-t border-outline-variant">
              <h3 className="text-headline-md font-semibold text-center mb-md text-on-surface">Tecnologia de Ponta</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-gutter">
                <div className="bg-surface-container-lowest border border-outline-variant rounded-lg p-md shadow-sm flex flex-col items-center text-center">
                  <div className="h-12 mb-4 flex items-center justify-center">
                    <img alt="Gemini Logo" className="h-full object-contain" src={GEMINI_LOGO_SRC} />
                  </div>
                  <h4 className="text-body-lg font-semibold mb-2">Gemini</h4>
                  <p className="text-body-sm text-on-surface-variant">
                    Analise profunda e contextual de contratos complexos, extraindo clausulas e identificando riscos com
                    precisao.
                  </p>
                </div>

                <div className="bg-surface-container-lowest border border-outline-variant rounded-lg p-md shadow-sm flex flex-col items-center text-center">
                  <div className="h-12 mb-4 flex items-center justify-center">
                    <img alt="Google Cloud Logo" className="h-full object-contain" src={GCLOUD_LOGO_SRC} />
                  </div>
                  <h4 className="text-body-lg font-semibold mb-2">Vertex AI</h4>
                  <p className="text-body-sm text-on-surface-variant">
                    Infraestrutura escalavel e segura para processamento rapido de documentos, com foco em confiabilidade
                    durante o bootcamp.
                  </p>
                </div>
              </div>
            </section>
          </>
        )}

        <section className="w-full max-w-4xl bg-surface-container-lowest border border-outline-variant rounded-xl p-md shadow-sm">
          <h3 className="text-headline-md font-semibold mb-3">Config do Analisador Ativo</h3>
          <p className="text-body-sm text-on-surface-variant mb-3">
            Este bloco mostra exatamente o prompt enviado para a IA e os campos esperados no retorno.
          </p>
          <div className="app-info-grid">
            <div className="bg-surface border border-outline-variant rounded-lg p-3">
              <p className="text-body-sm"><strong>Empresa:</strong> {bootcampConfig?.organization_name || "Nao definida"}</p>
              <p className="text-body-sm"><strong>Participante:</strong> {bootcampConfig?.participant_name || "Nao definido"}</p>
              <p className="text-body-sm"><strong>Perfil:</strong> {analyzerInfo?.active_profile_id || "Nao carregado"}</p>
            </div>
            <div className="bg-surface border border-outline-variant rounded-lg p-3">
              <p className="text-body-sm"><strong>Vertex:</strong> {bootcampConfig?.vertex_project_configured ? "ok" : "pendente"}</p>
              <p className="text-body-sm"><strong>Bucket:</strong> {bootcampConfig?.bucket_configured ? "ok" : "pendente"}</p>
              <p className="text-body-sm"><strong>Regiao:</strong> {bootcampConfig?.vertex_location || "us-central1"}</p>
            </div>
          </div>

          {warnings.length > 0 && (
            <div className="app-warning-box" role="alert">
              <strong>Atencao:</strong>
              <ul>
                {warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="mt-4">
            <h4 className="text-body-md font-semibold mb-2">Prompt enviado para a IA</h4>
            <pre className="app-code-preview">{analyzerInfo?.prompt || "Carregando prompt..."}</pre>
          </div>

          <div className="mt-4">
            <h4 className="text-body-md font-semibold mb-2">Campos esperados no retorno</h4>
            {analyzerInfo?.expected_fields?.length > 0 ? (
              <div className="app-fields-table-wrap">
                <table className="app-fields-table">
                  <thead>
                    <tr>
                      <th>Campo</th>
                      <th>Tipo</th>
                      <th>Descricao</th>
                    </tr>
                  </thead>
                  <tbody>
                    {analyzerInfo.expected_fields.map((field) => (
                      <tr key={field.name}>
                        <td>{field.name}</td>
                        <td>{field.type}</td>
                        <td>{field.description}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-body-sm text-on-surface-variant">Campos ainda nao carregados.</p>
            )}
          </div>

          <div className="mt-4">
            <h4 className="text-body-md font-semibold mb-2">Template de resposta JSON</h4>
            <pre className="app-code-preview">{responseTemplatePreview}</pre>
          </div>
        </section>

        {result && (
          <section className="w-full max-w-4xl bg-surface-container-lowest border border-outline-variant rounded-xl p-md shadow-sm">
            <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4 mb-4">
              <div>
                <h2 className="text-headline-md font-semibold text-on-surface">
                  {result?.analysis?.document_title || result.file_name || "Resultado da analise"}
                </h2>
                <p className="text-body-sm text-on-surface-variant mt-1">
                  Arquivo: {result.file_name} · Perfil: {result.analyzer_profile_id || analyzerInfo?.active_profile_id}
                </p>
              </div>
              <button
                className="bg-secondary-container text-on-secondary-container px-4 py-2 rounded-lg text-body-sm font-semibold"
                type="button"
                onClick={handleReset}
              >
                Nova analise
              </button>
            </div>

            <h3 className="text-body-lg font-semibold mb-3">Campos extraidos</h3>
            <AnalysisCards analysis={result.analysis} />

            <h3 className="text-body-lg font-semibold mt-5 mb-2">JSON completo</h3>
            <pre className="app-code-preview">{JSON.stringify(result.analysis || {}, null, 2)}</pre>
          </section>
        )}
      </main>

      <footer className="bg-surface-container-lowest border-t border-outline-variant w-full mt-auto">
        <div className="flex flex-col md:flex-row justify-between items-center w-full px-margin-mobile md:px-margin-desktop py-md max-w-max-width mx-auto gap-3">
          <div className="flex flex-col items-center md:items-start gap-2">
            <span className="text-body-sm text-on-surface-variant">© 2026 AI Boot Camp.</span>
            <div className="flex items-center gap-2">
              <span className="text-label-md text-on-surface-variant/80">Powered by</span>
              {showPoweredByLogo && (
                <img
                  alt="Powered by"
                  className="h-6 object-contain"
                  src={POWERED_BY_LOGO_SRC}
                  onError={() => setShowPoweredByLogo(false)}
                />
              )}
            </div>
          </div>
          <div className="flex flex-wrap justify-center gap-6">
            <span className="text-label-md text-on-surface-variant/80">Google Cloud Platform</span>
            <span className="text-label-md text-on-surface-variant/80">Gemini AI</span>
          </div>
        </div>
      </footer>
    </div>
  );
}

