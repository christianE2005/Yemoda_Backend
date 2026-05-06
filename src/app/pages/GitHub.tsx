import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { Github, CheckCircle2, XCircle, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { githubService } from "../../services/github.service";

type CallbackState = "processing" | "success" | "error" | "invalid";

export default function GitHubCallback() {
  const navigate = useNavigate();
  const [cbState, setCbState] = useState<CallbackState>("processing");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [githubLogin, setGithubLogin] = useState<string | null>(null);
  const handledRef = useRef(false);

  useEffect(() => {
    if (handledRef.current) return;
    handledRef.current = true;

    const params = new URLSearchParams(window.location.search);
    const code = params.get("code");
    const state = params.get("state");

    // Clean query params from URL immediately
    window.history.replaceState({}, "", window.location.pathname);

    if (!code || !state) {
      setCbState("invalid");
      return;
    }

    // Idempotency guard - React StrictMode runs effects twice in dev
    const dedupKey = `pip_gh_oauth_handled_${state}`;
    if (sessionStorage.getItem(dedupKey)) {
      setCbState("invalid");
      return;
    }
    sessionStorage.setItem(dedupKey, "done");

    githubService
      .completeOAuth({ code, state })
      .then((res) => {
        setGithubLogin(res.github_login);
        setCbState("success");
        toast.success("Cuenta de GitHub conectada", {
          description: `Conectado como ${res.github_login}`,
        });
        setTimeout(() => navigate("/dashboard", { replace: true }), 2000);
      })
      .catch((err) => {
        const detail = err instanceof Error ? err.message : "Error desconocido";
        setErrorMessage(detail);
        setCbState("error");
      });
  }, [navigate]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-background px-4">
      <div className="bg-card border border-border rounded-[4px] p-8 max-w-sm w-full text-center shadow-sm">
        <div className="flex justify-center mb-4">
          <Github className="w-8 h-8 text-foreground" />
        </div>

        {cbState === "processing" && (
          <>
            <Loader2 className="w-6 h-6 animate-spin text-primary mx-auto mb-3" />
            <h1 className="text-[14px] font-semibold text-foreground mb-1">
              Conectando con GitHub...
            </h1>
            <p className="text-[12px] text-muted-foreground">
              Completando la autorizacion, por favor espera.
            </p>
          </>
        )}

        {cbState === "success" && (
          <>
            <CheckCircle2 className="w-6 h-6 text-success mx-auto mb-3" />
            <h1 className="text-[14px] font-semibold text-foreground mb-1">
              Cuenta conectada!
            </h1>
            <p className="text-[12px] text-muted-foreground mb-1">
              Conectado como{" "}
              <span className="font-medium text-foreground">{githubLogin}</span>.
            </p>
            <p className="text-[11px] text-muted-foreground">Redirigiendo al dashboard...</p>
          </>
        )}

        {cbState === "error" && (
          <>
            <XCircle className="w-6 h-6 text-destructive mx-auto mb-3" />
            <h1 className="text-[14px] font-semibold text-foreground mb-1">
              Error al conectar
            </h1>
            {errorMessage && (
              <p className="text-[12px] text-muted-foreground mb-4">{errorMessage}</p>
            )}
            <button
              type="button"
              onClick={() => navigate("/dashboard", { replace: true })}
              className="h-7 px-4 bg-primary hover:bg-primary-hover text-primary-foreground rounded-[3px] text-[11px] font-medium transition-colors"
            >
              Volver al dashboard
            </button>
          </>
        )}

        {cbState === "invalid" && (
          <>
            <XCircle className="w-6 h-6 text-destructive mx-auto mb-3" />
            <h1 className="text-[14px] font-semibold text-foreground mb-1">
              Callback invalido
            </h1>
            <p className="text-[12px] text-muted-foreground mb-4">
              No se encontraron los parametros de autorizacion esperados.
            </p>
            <button
              type="button"
              onClick={() => navigate("/dashboard", { replace: true })}
              className="h-7 px-4 bg-primary hover:bg-primary-hover text-primary-foreground rounded-[3px] text-[11px] font-medium transition-colors"
            >
              Volver al dashboard
            </button>
          </>
        )}
      </div>
    </div>
  );
}
