export interface GeneratePprRequest {
  work_type: string;
  object_name: string;
  deadline_days: number;
}

export interface GenerateEstimateRequest {
  base: 'ГЭСН' | 'ФЕР';
  boq_file_name?: string;
  boq_text?: string;
}

export interface AnalyzeTenderResponse {
  summary: string;
  requirements: string[];
  risks: string[];
  deadlines: string[];
  estimated_budget: string;
  [key: string]: unknown;
}

export interface GenerateExecAlbumRequest {
  project_id: string;
  work_items: string[];
}

export interface AnalyticsSummaryResponse {
  total_generations: number;
  total_tokens: number;
  avg_response_ms: number;
  by_day: Array<{
    date: string;
    generations: number;
    tokens: number;
    avg_response_ms: number;
  }>;
  [key: string]: unknown;
}

export interface ComplianceRule {
  id: string;
  code: string;
  title: string;
  status?: string;
}

export interface ComplianceCheckRequest {
  project_id: string;
  requirement_ids?: string[];
}

export interface ComplianceCheckResponse {
  passed: boolean;
  score?: number;
  violations?: Array<{
    code: string;
    message: string;
    severity?: 'low' | 'medium' | 'high';
  }>;
  details?: string;
  [key: string]: unknown;
}

export interface AuthLoginRequest {
  username: string;
  password: string;
}

export interface AuthRegisterRequest {
  username: string;
  password: string;
  role?: string;
}

export interface AuthTokenResponse {
  access_token: string;
  token_type?: string;
  expires_in?: number;
}

export interface BillingQuotaResponse {
  plan?: string;
  remaining_quota?: number;
  used_quota?: number;
  reset_at?: string;
  history?: Array<{
    id: string;
    action: string;
    amount: number;
    created_at: string;
  }>;
  [key: string]: unknown;
}
