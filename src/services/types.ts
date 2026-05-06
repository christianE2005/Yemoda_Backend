// ─── Backend API types — mirrors Django models exactly ───────────────────────

export interface ApiUserAccount {
  id_user: number;
  email: string;
  username: string;
  created_at: string;
  system_role: number;
  system_role_name: string;
  github_connected?: boolean;
  is_github_connected?: boolean;
  github_login?: string | null;
  github_username?: string | null;
}

export interface ApiSystemRole {
  id_system_role: number;
  name: string;
  description: string | null;
}

export interface ApiProject {
  id_project: number;
  name: string;
  description: string | null;
  created_at: string;
  end_date: string | null;   // ISO date YYYY-MM-DD
  status: string | null;     // free-text e.g. "active", "on_hold", "completed"
  created_by: number | null;
  github_repo_full_name: string | null;
}

export interface ApiRole {
  id_role: number;
  name: string;
  description: string | null;
}

export interface ApiProjectMember {
  id: number;
  user: number;
  project: number;
  role: number | null;
  joined_at: string;
}

export interface ApiBoard {
  id_board: number;
  project: number;
  name: string;
  description: string | null;
  created_at: string;
}

export interface ApiTaskStatus {
  id_status: number;
  name: string;
  description: string | null;
}

export interface ApiTaskPriority {
  id_priority: number;
  name: string;
  level: number;
}

export interface ApiTask {
  id_task: number;
  project: number;
  sprint: number | null;
  board_column: number;
  milestone: number | null;
  tags: number[];
  assigned_users: Array<{
    id_user: number;
    email: string;
    username: string;
    id_assignment: number;
  }>;
  title: string;
  description: string | null;
  priority: number;
  created_by: number | null;
  created_at: string;
  due_date: string | null;   // ISO date
  completed_at: string | null;

  // Legacy compatibility fields retained while frontend migrates.
  board?: number;
  status?: number | null;
  assigned_to?: number | null;
}

export interface ApiTag {
  id_tag: number;
  name: string;
  color: string;
  project: number;
}

export interface ApiSprint {
  id_sprint: number;
  name: string;
  start_date: string | null;
  end_date: string | null;
  status: 'planned' | 'active' | 'closed';
  project: number;
}

export interface ApiMilestone {
  id_milestone: number;
  name: string;
  description: string | null;
  due_date: string | null;
  is_completed: boolean;
  project: number;
}

export interface ApiBoardColumn {
  id_column: number;
  name: string;
  order: number;
  is_final: boolean;
  board: number;
}

export interface ApiTaskAssignment {
  id_assignment: number;
  task: number;
  assigned_to: number;
  created_at?: string | null;
}

export interface ApiTaskComment {
  id_comment: number;
  task: number;
  user: number | null;
  content: string;
  created_at: string;
}

export interface ApiActivityLog {
  id_activity: number;
  user: number | null;
  entity_type: string | null;
  entity_id: number | null;
  action: string | null;
  created_at: string;
}

// ─── Auth response shapes ────────────────────────────────────────────────────

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_at: string;
  user: ApiUserAccount;
}

export interface RefreshResponse {
  access_token: string;
  token_type: string;
  expires_at: string;
}

export interface RegisterResponse extends ApiUserAccount {}

// ─── DRF paginated list (optional — DRF returns plain arrays by default) ────

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

// ─── GitHub integration ───────────────────────────────────────────────────────

export interface GitHubAppInstallStartResponse {
  install_url: string;
}

export interface GitHubOAuthStartResponse {
  authorize_url: string;
}

export interface GitHubOAuthCallbackPayload {
  code: string;
  state: string;
}

export interface GitHubOAuthCallbackResponse {
  access_token: string;
  refresh_token: string;
  expires_at: string;
  github_login: string;
  authorized_orgs: string[];
  user: ApiUserAccount;
}

export interface GitHubConnectionStatusResponse {
  connected: boolean;
  github_login: string | null;
  reason?: string;
}

export interface GitHubCreateRepoPayload {
  user_id: number;
  project_id?: number;
  owner_type?: 'org' | 'user';
  owner?: string;
  name: string;
  description?: string;
  private: boolean;
  auto_init: boolean;
  installation_id?: number;
  webhook_url?: string;
}

export interface GitHubRepo {
  id_repo: number;
  github_repo_id: number;
  name: string;
  full_name: string;
  owner: string;
  html_url: string;
  private: boolean;
  created_at: string;
  user: number;
  project: number | null;
}

export interface GitHubWebhook {
  id: number;
  events: string[];
}

export interface GitHubCreateRepoResponse {
  repository: GitHubRepo;
  webhook: GitHubWebhook;
}

// ─── Task Warnings ───────────────────────────────────────────────────────────

export interface ApiTaskWarning {
  id_warning: number;
  message: string;
  status: 'active' | 'resolved';
  created_at: string;
  resolved_at: string | null;
  task: number;
  resolved_in_push: number | null;
}

// ─── GitHub Push Events ──────────────────────────────────────────────────────

export interface ApiGithubPushEvent {
  id_push: number;
  repo_full_name: string;
  ref: string;
  pusher: string | null;
  commits: unknown;
  received_at: string;
  project: number | null;
}

export interface ApiGithubCommitDiff {
  sha: string;
  message: string;
  stats?: {
    additions: number;
    deletions: number;
    total: number;
  };
  files: Array<{
    filename: string;
    status: string;
    additions: number;
    deletions: number;
    patch?: string;
  }>;
}

export interface ApiGithubContent {
  name: string;
  path: string;
  type: 'file' | 'dir';
  size?: number;
  sha?: string;
  content?: string;
  download_url?: string;
}

// ─── API error shape ─────────────────────────────────────────────────────────

export interface ApiError {
  detail?: string;
  [field: string]: string | string[] | undefined;
}
