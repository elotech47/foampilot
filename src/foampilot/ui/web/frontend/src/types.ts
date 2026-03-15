export type Phase =
  | 'idle'
  | 'starting'
  | 'clarifying'
  | 'consulting'
  | 'setup'
  | 'meshing'
  | 'running'
  | 'analyzing'
  | 'complete'
  | 'error';

export interface TokenInfo {
  inputTokens: number;
  outputTokens: number;
  costUsd: number;
  turns: number;
  contextPct: number;
}

// ─── Agent event stream ──────────────────────────────────────────────────────

export interface ToolCall {
  tool: string;
  input: Record<string, unknown>;
  timestamp: number;
  status: 'pending' | 'success' | 'error';
  result?: unknown;
  error?: string;
}

export interface LLMResponse {
  turn: number;
  text: string;
  timestamp: number;
}

export type AgentEventKind = 'phase' | 'tool' | 'llm' | 'system';

export interface AgentEvent {
  id: string;
  kind: AgentEventKind;
  timestamp: number;
  // kind === 'phase'
  phase?: Phase;
  // kind === 'tool'
  toolCall?: ToolCall;
  // kind === 'llm'
  llmResponse?: LLMResponse;
  // kind === 'system'
  message?: string;
}

// ─── Chat messages ───────────────────────────────────────────────────────────

export type MessageRole = 'user' | 'system' | 'approval' | 'clarification';

export interface ClarificationData {
  context?: string | null;
  question: string;
  parameter?: string | null;
  options?: string[] | null;
  default?: string | null;
  hint?: string | null;
}

export interface ChatMessage {
  id: string;
  role: MessageRole;
  text: string;
  timestamp: number;
  // approval only
  resolved?: boolean;
  approved?: boolean;
  approvalTool?: string;
  approvalInput?: Record<string, unknown>;
  // clarification only
  clarificationData?: ClarificationData | null;
  clarificationParams?: Record<string, unknown> | null;
  answered?: boolean;
  answeredWith?: string;
}

// ─── File tree ───────────────────────────────────────────────────────────────

export interface FileNode {
  name: string;
  type: 'file' | 'directory';
  path?: string;
  size?: number;
  children?: FileNode[];
}

// ─── App state ───────────────────────────────────────────────────────────────

export interface AppState {
  connected: boolean;
  running: boolean;
  sessionId: string | null;
  phase: Phase;
  events: AgentEvent[];
  chatMessages: ChatMessage[];
  fileTree: FileNode | null;
  approvalPending: boolean;
  clarificationPending: boolean;
  autoApprove: boolean;
  tokenInfo: TokenInfo;
}
