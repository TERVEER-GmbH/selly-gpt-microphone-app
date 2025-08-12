export type AskResponse = {
  answer: string | []
  citations: Citation[]
  generated_chart: string | null
  error?: string
  message_id?: string
  feedback?: Feedback
  exec_results?: ExecResults[]
}

export type Citation = {
  part_index?: number
  content: string
  id: string
  title: string | null
  filepath: string | null
  url: string | null
  metadata: string | null
  chunk_id: string | null
  reindex_id: string | null
}

export type ToolMessageContent = {
  citations: Citation[]
  intent: string
}

export type AzureSqlServerExecResult = {
  intent: string
  search_query: string | null
  search_result: string | null
  code_generated: string | null
  code_exec_result?: string | undefined
}

export type AzureSqlServerExecResults = {
  all_exec_results: AzureSqlServerExecResult[]
}

export type ChatMessage = {
  id: string
  role: string
  content: string | [{ type: string; text: string }, { type: string; image_url: { url: string } }]
  end_turn?: boolean
  date: string
  feedback?: Feedback
  context?: string
}

export type ExecResults = {
  intent: string
  search_query: string | null
  search_result: string | null
  code_generated: string | null
}

export type Conversation = {
  id: string
  title: string
  messages: ChatMessage[]
  date: string
}

export enum ChatCompletionType {
  ChatCompletion = 'chat.completion',
  ChatCompletionChunk = 'chat.completion.chunk'
}

export type ChatResponseChoice = {
  messages: ChatMessage[]
}

export type ChatResponse = {
  id: string
  model: string
  created: number
  object: ChatCompletionType
  choices: ChatResponseChoice[]
  history_metadata: {
    conversation_id: string
    title: string
    date: string
  }
  error?: any
}

export type ConversationRequest = {
  messages: ChatMessage[]
}

export type UserInfo = {
  access_token: string
  expires_on: string
  id_token: string
  provider_name: string
  user_claims: any[]
  user_id: string
}

export type WhoAmI = {
  authenticated: boolean
  user_name:     string
  email:         string
  roles:         string[]
  is_admin:      boolean
}

export enum CosmosDBStatus {
  NotConfigured = 'CosmosDB is not configured',
  NotWorking = 'CosmosDB is not working',
  InvalidCredentials = 'CosmosDB has invalid credentials',
  InvalidDatabase = 'Invalid CosmosDB database name',
  InvalidContainer = 'Invalid CosmosDB container name',
  Working = 'CosmosDB is configured and working'
}

export type CosmosDBHealth = {
  cosmosDB: boolean
  status: string
}

export enum ChatHistoryLoadingState {
  Loading = 'loading',
  Success = 'success',
  Fail = 'fail',
  NotStarted = 'notStarted'
}

export type ErrorMessage = {
  title: string
  subtitle: string
}

export type UI = {
  title: string
  chat_title: string
  chat_description: string
  logo?: string
  chat_logo?: string
  show_share_button?: boolean
  show_chat_history_button?: boolean
}

export type FrontendSettings = {
  auth_enabled?: string | null
  feedback_enabled?: string | null
  ui?: UI
  sanitize_answer?: boolean
  oyd_enabled?: boolean
}

export enum Feedback {
  Neutral = 'neutral',
  Positive = 'positive',
  Negative = 'negative',
  MissingCitation = 'missing_citation',
  WrongCitation = 'wrong_citation',
  OutOfScope = 'out_of_scope',
  InaccurateOrIrrelevant = 'inaccurate_or_irrelevant',
  OtherUnhelpful = 'other_unhelpful',
  HateSpeech = 'hate_speech',
  Violent = 'violent',
  Sexual = 'sexual',
  Manipulative = 'manipulative',
  OtherHarmful = 'other_harmlful'
}

export interface Prompt {
  id: string;
  text: string;
  golden_answer: string;
  tags: string[];
}

export interface TestParams {
  model: string;
  temperature: number;
  max_tokens: number;
  top_p?: number;
}

export interface TestResult {
  id: string
  run_id: string

  prompt_id: string
  prompt_text: string
  ai_response: string
  golden_answer: string
  timestamp: string

  // Scores
  relevance?: number;
  factual_accuracy?: number;
  completeness?: number;
  tone?: number;
  comprehensibility?: number;

  // Kommentare
  relevance_comment?: string;
  factual_accuracy_comment?: string;
  completeness_comment?: string;
  tone_comment?: string;
  comprehensibility_comment?: string;

  overall_comment?: string | null;
}

export type TestResultUpdate = Partial<Pick<
  TestResult,
  | 'relevance' | 'relevance_comment'
  | 'factual_accuracy' | 'factual_accuracy_comment'
  | 'completeness' | 'completeness_comment'
  | 'tone' | 'tone_comment'
  | 'comprehensibility' | 'comprehensibility_comment'
  | 'overall_comment'
>>;

export interface RunSummary {
  id: string;
  prompt_ids: string[];
  params: TestParams;
  status: 'Pending' | 'Running' | 'Done';
  created_at: string;
  // results fehlt hier bewusst, kommt erst in der Detail-API
}

// bereits vorhanden: RunStatus für /status
export interface RunStatus {
  run_id: string;
  prompt_ids: string[];
  params: TestParams;
  status: 'Pending' | 'Running' | 'Done';
  total: number;
  completed: number;
  created_at: string;
}

export interface RunMetrics {
  count: number;
  category_averages: {
    relevance: number;
    factual_accuracy: number;
    completeness: number;
    tone: number;
    comprehensibility: number;
  };
  avg_subscore: number;
  product_score_avg: number;       // roh (Produkt)
  product_score_norm_avg: number;  // 1–5 (5. Wurzel des Produkts)
}

export interface RunListItem {
  id: string
  prompt_ids: string[]
  params: TestParams
  status: 'Pending' | 'Running' | 'Done'
  created_at: string
  metrics?: RunMetrics
}

export interface CompareSummary {
  left:  { run_id: string; count: number; avg_subscore: number; product_score_norm_avg: number; };
  right: { run_id: string; count: number; avg_subscore: number; product_score_norm_avg: number; };
  coverage: { intersection: number; left_only: number; right_only: number; union: number; };
  delta: { avg_subscore: number; product_score_norm_avg: number; };
}

export interface ComparePairSide {
  prompt_id?: string;
  prompt_text: string;
  ai_response: string;
  golden_answer: string;
  scores: {
    relevance: number;
    factual_accuracy: number;
    completeness: number;
    tone: number;
    comprehensibility: number;
  };
  subscore: number;
  product_score_raw: number;
  product_score_norm: number;
}

export type ComparePair =
  | {
      prompt_key: string;
      matched: true;
      left: ComparePairSide;
      right: ComparePairSide;
      delta: { product_score_norm: number; subscore: number };
    }
  | {
      prompt_key: string;
      matched: false;
      side: 'left_only';
      left: ComparePairSide;
      right: null;
    }
  | {
      prompt_key: string;
      matched: false;
      side: 'right_only';
      left: null;
      right: ComparePairSide;
    };

export interface CompareFull {
  summary: CompareSummary;
  pairs: ComparePair[];
}

// Hilfstyp, falls du sowohl RunSummary als auch RunListItem im Projekt hast
export type RunWithMetrics<Base extends { id: string } = any> = Base & { metrics: RunMetrics };
