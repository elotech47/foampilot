import { useCallback, useEffect, useRef, useState } from 'react';
import type { AgentEvent, AppState, ChatMessage, ClarificationData, FileNode, Phase, TokenInfo } from '../types';

const RECONNECT_DELAY_MS = 2500;

const INITIAL_TOKEN_INFO: TokenInfo = {
  inputTokens: 0,
  outputTokens: 0,
  costUsd: 0,
  turns: 0,
  contextPct: 0,
};

const INITIAL_STATE: AppState = {
  connected: false,
  running: false,
  sessionId: null,
  phase: 'idle',
  events: [],
  chatMessages: [],
  fileTree: null,
  approvalPending: false,
  clarificationPending: false,
  autoApprove: false,
  tokenInfo: { ...INITIAL_TOKEN_INFO },
};

let _eventId = 0;
function nextId(): string {
  return String(++_eventId);
}

function ts(): number {
  return Date.now();
}

export function useWebSocket(url: string) {
  const [state, setState] = useState<AppState>(INITIAL_STATE);
  const wsRef = useRef<WebSocket | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const stateRef = useRef(state);
  stateRef.current = state;

  const processMessage = useCallback((raw: string) => {
    let msg: { type: string; data?: Record<string, unknown>; message?: string };
    try {
      msg = JSON.parse(raw);
    } catch {
      return;
    }

    const { type, data = {}, message } = msg;
    const now = ts();
    const id = nextId();

    setState(prev => {
      const next = { ...prev };

      switch (type) {
        case 'connected': {
          next.connected = true;
          break;
        }

        case 'status': {
          next.running = Boolean(data.running);
          next.sessionId = (data.session_id as string) ?? null;
          next.phase = ((data.phase as Phase) ?? 'idle');
          break;
        }

        case 'session_starting': {
          // Immediate ACK from server — show spinner right away
          next.running = true;
          next.phase = 'starting';
          next.events = [];
          next.fileTree = null;
          next.approvalPending = false;
          next.clarificationPending = false;
          next.tokenInfo = { ...INITIAL_TOKEN_INFO };
          break;
        }

        case 'session_start': {
          next.running = true;
          next.sessionId = (data.session_id as string) ?? null;
          next.phase = 'consulting';
          // Reset per-session state but keep chat messages
          next.events = [];
          next.fileTree = null;
          next.approvalPending = false;
          next.tokenInfo = { ...INITIAL_TOKEN_INFO };
          next.chatMessages = [
            ...prev.chatMessages,
            {
              id,
              role: 'system',
              text: `Session ${data.session_id} started`,
              timestamp: now,
            } satisfies ChatMessage,
          ];
          break;
        }

        case 'phase_start': {
          const phase = (data.phase as Phase) ?? 'idle';
          next.phase = phase;
          const phaseEvent: AgentEvent = {
            id,
            kind: 'phase',
            phase,
            timestamp: now,
          };
          next.events = [...prev.events, phaseEvent];
          break;
        }

        case 'tool_call': {
          const toolEvent: AgentEvent = {
            id,
            kind: 'tool',
            timestamp: now,
            toolCall: {
              tool: (data.tool as string) ?? '',
              input: (data.input as Record<string, unknown>) ?? {},
              timestamp: now,
              status: 'pending',
            },
          };
          next.events = [...prev.events, toolEvent];
          break;
        }

        case 'tool_result': {
          // Update matching pending tool call
          const toolName = data.tool as string;
          const success = Boolean(data.success);
          const events = prev.events.map(e => {
            if (
              e.kind === 'tool' &&
              e.toolCall?.tool === toolName &&
              e.toolCall.status === 'pending'
            ) {
              return {
                ...e,
                toolCall: {
                  ...e.toolCall,
                  status: success ? ('success' as const) : ('error' as const),
                  result: data.data,
                  error: data.error as string | undefined,
                },
              };
            }
            return e;
          });
          next.events = events;
          break;
        }

        case 'llm_response': {
          if (data.text) {
            const llmEvent: AgentEvent = {
              id,
              kind: 'llm',
              timestamp: now,
              llmResponse: {
                turn: (data.turn as number) ?? 0,
                text: data.text as string,
                timestamp: now,
              },
            };
            next.events = [...prev.events, llmEvent];
          }
          break;
        }

        case 'agent_done': {
          const d = data ?? {};
          next.tokenInfo = {
            inputTokens: prev.tokenInfo.inputTokens + ((d.total_input_tokens as number) ?? 0),
            outputTokens: prev.tokenInfo.outputTokens + ((d.total_output_tokens as number) ?? 0),
            costUsd: prev.tokenInfo.costUsd + ((d.total_cost_usd as number) ?? 0),
            turns: prev.tokenInfo.turns + ((d.turns as number) ?? 0),
            contextPct: (d.context_utilization_pct as number) ?? prev.tokenInfo.contextPct,
          };
          break;
        }

        case 'session_complete': {
          next.running = false;
          next.phase = 'complete';
          next.chatMessages = [
            ...prev.chatMessages,
            {
              id,
              role: 'system',
              text: 'Simulation complete.',
              timestamp: now,
            } satisfies ChatMessage,
          ];
          break;
        }

        case 'session_error': {
          next.running = false;
          next.phase = 'error';
          next.chatMessages = [
            ...prev.chatMessages,
            {
              id,
              role: 'system',
              text: `Error: ${(data.error as string) ?? message ?? 'Unknown error'}`,
              timestamp: now,
            } satisfies ChatMessage,
          ];
          break;
        }

        case 'approval_required': {
          // Deduplicate: only add a new card if one isn't already showing
          if (prev.approvalPending) break;
          next.approvalPending = true;
          next.chatMessages = [
            ...prev.chatMessages,
            {
              id,
              role: 'approval',
              text: `Permission needed to run \`${data.tool}\``,
              timestamp: now,
              resolved: false,
              approvalTool: data.tool as string,
              approvalInput: (data.input as Record<string, unknown>) ?? {},
            } satisfies ChatMessage,
          ];
          break;
        }

        case 'clarification_question': {
          next.clarificationPending = true;
          const qd = (data.question_data as ClarificationData) ?? null;
          next.chatMessages = [
            ...prev.chatMessages,
            {
              id,
              role: 'clarification',
              text: (data.text as string) ?? '',
              timestamp: now,
              clarificationData: qd,
              clarificationParams: (data.params as Record<string, unknown>) ?? null,
              answered: false,
            } satisfies ChatMessage,
          ];
          break;
        }

        case 'clarification_done': {
          next.clarificationPending = false;
          break;
        }

        case 'session_stopped': {
          next.running = false;
          next.phase = 'idle';
          next.approvalPending = false;
          next.clarificationPending = false;
          next.chatMessages = [
            ...prev.chatMessages,
            {
              id,
              role: 'system',
              text: 'Session stopped.',
              timestamp: now,
            } satisfies ChatMessage,
          ];
          break;
        }

        case 'auto_approved': {
          next.chatMessages = [
            ...prev.chatMessages,
            {
              id,
              role: 'system',
              text: `Auto-approved: \`${data.tool}\``,
              timestamp: now,
            } satisfies ChatMessage,
          ];
          break;
        }

        case 'file_tree': {
          next.fileTree = (data.tree as FileNode) ?? null;
          break;
        }

        case 'error': {
          next.chatMessages = [
            ...prev.chatMessages,
            {
              id,
              role: 'system',
              text: `Error: ${message ?? 'Unknown'}`,
              timestamp: now,
            } satisfies ChatMessage,
          ];
          break;
        }
      }

      return next;
    });
  }, []);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setState(prev => ({ ...prev, connected: true }));
    };

    ws.onclose = () => {
      setState(prev => ({ ...prev, connected: false }));
      timerRef.current = setTimeout(connect, RECONNECT_DELAY_MS);
    };

    ws.onerror = () => ws.close();

    ws.onmessage = evt => processMessage(evt.data as string);
  }, [url, processMessage]);

  useEffect(() => {
    connect();
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      wsRef.current?.close();
    };
  }, [connect]);

  const send = useCallback((msg: object) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg));
    }
  }, []);

  const startSimulation = useCallback(
    (prompt: string) => {
      const cur = stateRef.current;
      if (cur.clarificationPending) {
        // Mark the last unanswered clarification card as answered
        setState(prev => {
          const msgs = [...prev.chatMessages];
          for (let i = msgs.length - 1; i >= 0; i--) {
            if (msgs[i].role === 'clarification' && !msgs[i].answered) {
              msgs[i] = { ...msgs[i], answered: true, answeredWith: prompt };
              break;
            }
          }
          return {
            ...prev,
            chatMessages: [
              ...msgs,
              { id: nextId(), role: 'user', text: prompt, timestamp: ts() } satisfies ChatMessage,
            ],
          };
        });
        send({ type: 'clarify_reply', text: prompt });
      } else {
        setState(prev => ({
          ...prev,
          chatMessages: [
            ...prev.chatMessages,
            { id: nextId(), role: 'user', text: prompt, timestamp: ts() } satisfies ChatMessage,
          ],
        }));
        send({ type: 'start', prompt, auto_approve: cur.autoApprove });
      }
    },
    [send],
  );

  const stopSimulation = useCallback(() => {
    send({ type: 'stop' });
  }, [send]);

  const sendClarifyReply = useCallback(
    (text: string) => {
      setState(prev => ({
        ...prev,
        chatMessages: [
          ...prev.chatMessages,
          {
            id: nextId(),
            role: 'user',
            text,
            timestamp: ts(),
          } satisfies ChatMessage,
        ],
      }));
      send({ type: 'clarify_reply', text });
    },
    [send],
  );

  const resolveApproval = useCallback(
    (approved: boolean) => {
      send({ type: 'approval', approved });
      setState(prev => ({
        ...prev,
        approvalPending: false,
        chatMessages: prev.chatMessages.map(m =>
          m.role === 'approval' && !m.resolved ? { ...m, resolved: true, approved } : m,
        ),
      }));
    },
    [send],
  );

  const setAutoApprove = useCallback(
    (enabled: boolean) => {
      send({ type: 'set_auto_approve', enabled });
      setState(prev => ({ ...prev, autoApprove: enabled }));
    },
    [send],
  );

  const requestFileTree = useCallback(() => {
    send({ type: 'get_files' });
  }, [send]);

  const resetSession = useCallback(() => {
    setState(prev => ({
      ...INITIAL_STATE,
      connected: prev.connected,
      autoApprove: prev.autoApprove,
    }));
  }, []);

  return { state, startSimulation, stopSimulation, sendClarifyReply, resolveApproval, setAutoApprove, requestFileTree, resetSession };
}
