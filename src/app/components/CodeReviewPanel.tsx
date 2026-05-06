import { useState, useEffect, useCallback } from 'react';
import {
  GitCommit, ChevronDown, ChevronRight, FileCode2,
  Loader2, RefreshCw, Clock, User, ExternalLink,
} from 'lucide-react';
import { githubService } from '../../services';
import type { ApiGithubPushEvent, ApiGithubCommitDiff } from '../../services';
import { CodeDiffViewer } from './CodeDiffViewer';

interface CodeReviewPanelProps {
  projectId: number;
  repoFullName: string | null;
}

interface ExpandedCommit {
  sha: string;
  diff: ApiGithubCommitDiff | null;
  loading: boolean;
  error: string | null;
}

export function CodeReviewPanel({ projectId, repoFullName }: CodeReviewPanelProps) {
  const [pushes, setPushes] = useState<ApiGithubPushEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<Map<string, ExpandedCommit>>(new Map());

  const fetchPushes = useCallback(async () => {
    setLoading(true);
    try {
      const data = await githubService.listPushes({ project_id: projectId });
      setPushes(data);
    } catch {
      setPushes([]);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => { fetchPushes(); }, [fetchPushes]);

  const toggleCommit = async (sha: string) => {
    if (expanded.has(sha)) {
      setExpanded((prev) => {
        const next = new Map(prev);
        next.delete(sha);
        return next;
      });
      return;
    }

    if (!repoFullName) return;

    setExpanded((prev) => new Map(prev).set(sha, { sha, diff: null, loading: true, error: null }));
    try {
      const diff = await githubService.getCommitDiff(repoFullName, sha);
      setExpanded((prev) => new Map(prev).set(sha, { sha, diff, loading: false, error: null }));
    } catch {
      setExpanded((prev) => new Map(prev).set(sha, { sha, diff: null, loading: false, error: 'No se pudo cargar el diff' }));
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16 text-muted-foreground gap-2">
        <Loader2 className="w-4 h-4 animate-spin" /> <span className="text-[12px]">Cargando push events…</span>
      </div>
    );
  }

  if (!repoFullName) {
    return (
      <div className="text-center py-16">
        <FileCode2 className="w-8 h-8 text-muted-foreground/30 mx-auto mb-3" />
        <p className="text-[12px] text-muted-foreground">Sin repositorio vinculado a este proyecto.</p>
        <p className="text-[10px] text-muted-foreground/60 mt-1">Vincula un repositorio en la pestaña Repositorios.</p>
      </div>
    );
  }

  if (pushes.length === 0) {
    return (
      <div className="text-center py-16">
        <GitCommit className="w-8 h-8 text-muted-foreground/30 mx-auto mb-3" />
        <p className="text-[12px] text-muted-foreground">No se encontraron push events.</p>
        <p className="text-[10px] text-muted-foreground/60 mt-1">Los push events aparecerán cuando se hagan pushes al repositorio.</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <GitCommit className="w-3.5 h-3.5 text-muted-foreground" />
          <span className="text-[12px] font-semibold text-foreground">{pushes.length} push events</span>
        </div>
        <button
          onClick={fetchPushes}
          className="p-1 rounded-[3px] hover:bg-surface-secondary text-muted-foreground hover:text-foreground transition-colors"
        >
          <RefreshCw className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Push events list */}
      {pushes.map((push) => {
        const pushCommits: Array<{
          id: string;
          message: string;
          timestamp?: string;
          author?: { name?: string; email?: string; username?: string };
          url?: string;
          added?: string[];
          removed?: string[];
          modified?: string[];
        }> = Array.isArray(push.commits) ? push.commits : [];

        return (
          <div key={push.id_push} className="border border-border rounded-[4px] overflow-hidden">
            {/* Push header */}
            <div className="px-3 py-2.5 bg-surface-secondary/30 border-b border-border">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="text-[10px] font-mono text-primary bg-primary/10 px-1.5 py-0.5 rounded-[2px]">
                    {push.ref?.replace('refs/heads/', '') ?? 'main'}
                  </span>
                  <span className="text-[11px] text-foreground font-medium truncate">
                      {push.pusher ?? 'unknown'}
                  </span>
                </div>
                <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground shrink-0">
                  <Clock className="w-3 h-3" />
                  {new Date(push.received_at).toLocaleDateString('es-MX', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}
                </div>
              </div>
              <p className="text-[10px] text-muted-foreground mt-1">
                {pushCommits.length} commit{pushCommits.length !== 1 ? 's' : ''}
              </p>
            </div>

            {/* Commits */}
            <div className="divide-y divide-border/50">
              {pushCommits.map((commit) => {
                const exp = expanded.get(commit.id);
                const isExpanded = !!exp;
                const filesChanged = [
                  ...(commit.added ?? []),
                  ...(commit.removed ?? []),
                  ...(commit.modified ?? []),
                ];

                return (
                  <div key={commit.id}>
                    <button
                      onClick={() => toggleCommit(commit.id)}
                      className="w-full px-3 py-2 flex items-start gap-2 hover:bg-surface-secondary/30 transition-colors text-left"
                    >
                      <span className="mt-0.5">
                        {isExpanded
                          ? <ChevronDown className="w-3 h-3 text-muted-foreground" />
                          : <ChevronRight className="w-3 h-3 text-muted-foreground" />
                        }
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="text-[11px] text-foreground leading-snug truncate">{commit.message}</p>
                        <div className="flex items-center gap-3 mt-1 text-[10px] text-muted-foreground">
                          <span className="font-mono">{commit.id.slice(0, 7)}</span>
                          {commit.author?.name && (
                            <span className="flex items-center gap-1">
                              <User className="w-2.5 h-2.5" /> {commit.author.name}
                            </span>
                          )}
                          {filesChanged.length > 0 && (
                            <span>{filesChanged.length} archivo{filesChanged.length !== 1 ? 's' : ''}</span>
                          )}
                          {commit.url && (
                            <a
                              href={commit.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              onClick={(e) => e.stopPropagation()}
                              className="hover:text-primary transition-colors"
                            >
                              <ExternalLink className="w-2.5 h-2.5" />
                            </a>
                          )}
                        </div>
                      </div>
                    </button>

                    {/* Expanded diff */}
                    {isExpanded && (
                      <div className="px-3 pb-3 space-y-2">
                        {exp.loading && (
                          <div className="flex items-center gap-2 text-[11px] text-muted-foreground py-2">
                            <Loader2 className="w-3 h-3 animate-spin" /> Cargando diff…
                          </div>
                        )}
                        {exp.error && (
                          <p className="text-[11px] text-destructive py-2">{exp.error}</p>
                        )}
                        {exp.diff && exp.diff.files && (
                          <>
                            <div className="flex items-center gap-3 text-[10px] text-muted-foreground py-1.5 border-b border-border/30 mb-2">
                              <span className="text-emerald-500">+{exp.diff.stats?.additions ?? 0}</span>
                              <span className="text-red-500">−{exp.diff.stats?.deletions ?? 0}</span>
                              <span>{exp.diff.files.length} archivo{exp.diff.files.length !== 1 ? 's' : ''}</span>
                            </div>
                            {exp.diff.files.map((file, fi) => (
                              <CodeDiffViewer
                                key={fi}
                                filename={file.filename}
                                patch={file.patch ?? ''}
                              />
                            ))}
                          </>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}
