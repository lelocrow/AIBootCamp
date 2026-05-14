import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import App from "./App";

function selectPdfFile() {
  const input = document.querySelector('input[type="file"]');
  const file = new File(["%PDF-1.4 test"], "documento.pdf", { type: "application/pdf" });
  fireEvent.change(input, { target: { files: [file] } });
  return file;
}

function buildConfigPayload() {
  return {
    success: true,
    config: {
      service_name: "ai-bootcamp-analyzer",
      organization_name: "Empresa Demo",
      participant_name: "Participante Teste",
      vertex_project_configured: true,
      bucket_configured: true,
      vertex_location: "us-central1",
      model_name: "gemini-2.5-flash",
      warnings: [],
      analyzer: {
        active_profile_id: "contract_risk_guard",
        prompt: "Prompt de teste",
        expected_fields: [{ name: "document_title", type: "string", description: "Titulo do documento" }],
        response_template: { document_title: "string" },
      },
    },
  };
}

function buildResultResponse() {
  return {
    success: true,
    file_name: "documento.pdf",
    analyzer_profile_id: "contract_risk_guard",
    analysis: {
      document_title: "Contrato Exemplo",
      executive_summary: "Resumo de teste.",
      risk_alerts: [{ level: "high", category: "legal", description: "Risco de multa", mitigation: "Revisar clausula" }],
    },
    job: {
      job_id: "job-123",
      status: "completed",
      stage: "completed",
      progress: 100,
      file_name: "documento.pdf",
    },
  };
}

describe("App", () => {
  afterEach(() => {
    jest.resetAllMocks();
  });

  it("renderiza a tela inicial de upload com cards de tecnologia", async () => {
    const configPayload = buildConfigPayload();

    global.fetch = jest.fn(async (url) => {
      if (url === "/api/config") {
        return {
          ok: true,
          status: 200,
          text: async () => JSON.stringify(configPayload),
        };
      }

      throw new Error(`URL nao esperada no teste: ${url}`);
    });

    render(<App />);

    expect(screen.getByText(/upload/i)).toBeInTheDocument();
    expect(screen.getByText(/arraste e solte um arquivo pdf aqui/i)).toBeInTheDocument();
    expect(await screen.findByText(/tecnologia de ponta/i)).toBeInTheDocument();
    expect(screen.getByText(/gemini/i)).toBeInTheDocument();
    expect(screen.getByText(/vertex ai/i)).toBeInTheDocument();
  });

  it("enfileira e processa a analise assincrona com polling", async () => {
    const resultPayload = buildResultResponse();
    const configPayload = buildConfigPayload();

    global.fetch = jest.fn(async (url) => {
      if (url === "/api/config") {
        return {
          ok: true,
          status: 200,
          text: async () => JSON.stringify(configPayload),
        };
      }

      if (url === "/api/analyze") {
        return {
          ok: true,
          status: 202,
          text: async () =>
            JSON.stringify({
              success: true,
              job: {
                job_id: "job-123",
                status: "queued",
                stage: "queued",
                progress: 5,
                file_name: "documento.pdf",
              },
            }),
        };
      }

      if (url === "/api/analyze/job-123/status") {
        return {
          ok: true,
          status: 200,
          text: async () =>
            JSON.stringify({
              success: true,
              result_ready: true,
              job: {
                job_id: "job-123",
                status: "completed",
                stage: "completed",
                progress: 100,
                file_name: "documento.pdf",
              },
            }),
        };
      }

      if (url === "/api/analyze/job-123/result") {
        return {
          ok: true,
          status: 200,
          text: async () => JSON.stringify(resultPayload),
        };
      }

      throw new Error(`URL nao esperada no teste: ${url}`);
    });

    render(<App />);
    selectPdfFile();

    fireEvent.click(screen.getByRole("button", { name: /iniciar analise/i }));

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        "/api/analyze",
        expect.objectContaining({
          method: "POST",
          body: expect.any(FormData),
        })
      );
    });

    expect(await screen.findByText("Contrato Exemplo")).toBeInTheDocument();
    expect(screen.getByText(/json completo/i)).toBeInTheDocument();
  });

  it("mostra erro tipado quando a API retorna arquivo invalido", async () => {
    const configPayload = buildConfigPayload();

    global.fetch = jest.fn(async (url) => {
      if (url === "/api/config") {
        return {
          ok: true,
          status: 200,
          text: async () => JSON.stringify(configPayload),
        };
      }

      if (url === "/api/analyze") {
        return {
          ok: false,
          status: 400,
          text: async () => JSON.stringify({ error_type: "invalid_file", error: "Apenas PDF e suportado." }),
        };
      }

      throw new Error(`URL nao esperada no teste: ${url}`);
    });

    render(<App />);
    selectPdfFile();

    fireEvent.click(screen.getByRole("button", { name: /iniciar analise/i }));

    expect(await screen.findByText(/arquivo invalido/i)).toBeInTheDocument();
    expect(screen.getByText(/apenas pdf e suportado/i)).toBeInTheDocument();
  });
});

