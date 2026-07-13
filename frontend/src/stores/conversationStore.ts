import { create } from 'zustand';
import type { ActiveEngine, ChatMessageData, SchedulingTraceStep } from '@/types';

/**
 * Orchestrator UI state: the committed conversation history, the engine
 * currently driving the right Context Panel, and the panel's open/close state.
 * The in-flight (streaming) assistant turn is NOT kept here — it lives in the
 * `useStreamingChat` hook and is committed to `messages` once finalized.
 */
export interface SkillContextData {
  steps: SchedulingTraceStep[];
  stopReason?: string;
  skillNames: string[];
}

interface ConversationState {
  messages: ChatMessageData[];
  activeEngine: ActiveEngine;
  contextPanelOpen: boolean;
  /** Latest scheduling ReAct 工具轨迹 (from the `context` event) for the panel. */
  schedulingSteps: SchedulingTraceStep[];
  /** Latest skill run trace (from the `context` event with engine "skill"). */
  skillContext: SkillContextData | null;

  /** Append a finalized message. */
  addMessage: (message: ChatMessageData) => void;
  /** Patch a message in place (e.g. record a clarification selection). */
  updateMessage: (id: string, patch: Partial<ChatMessageData>) => void;
  /** Activate an engine and open the panel (called on a `context` event). */
  activateEngine: (engine: ActiveEngine) => void;
  /** Store the scheduling trace carried by a `context` event. */
  setSchedulingSteps: (steps: SchedulingTraceStep[]) => void;
  /** Store the skill run context carried by a `context` event. */
  setSkillContext: (ctx: SkillContextData | null) => void;
  setContextPanelOpen: (open: boolean) => void;
  closeContextPanel: () => void;
  resetThread: (initialMessages?: ChatMessageData[]) => void;
}

const INITIAL_MESSAGES: ChatMessageData[] = [
  { id: 'sys-welcome', kind: 'system', text: '新会话 · 在下方描述排产 / 调度 / 查询需求开始' },
];

export const useConversationStore = create<ConversationState>((set) => ({
  messages: INITIAL_MESSAGES,
  activeEngine: null,
  contextPanelOpen: false,
  schedulingSteps: [],
  skillContext: null,

  addMessage: (message) => set((s) => ({ messages: [...s.messages, message] })),

  setSchedulingSteps: (steps) => set({ schedulingSteps: steps }),

  setSkillContext: (ctx) => set({ skillContext: ctx }),

  updateMessage: (id, patch) =>
    set((s) => ({
      messages: s.messages.map((m) => (m.id === id ? ({ ...m, ...patch } as ChatMessageData) : m)),
    })),

  activateEngine: (engine) => set({ activeEngine: engine, contextPanelOpen: engine !== null }),

  setContextPanelOpen: (open) => set({ contextPanelOpen: open }),

  closeContextPanel: () => set({ contextPanelOpen: false }),

  resetThread: (initialMessages) =>
    set({
      messages: initialMessages ?? INITIAL_MESSAGES,
      activeEngine: null,
      contextPanelOpen: false,
      schedulingSteps: [],
      skillContext: null,
    }),
}));
