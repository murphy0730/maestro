/**
 * Shared TypeScript types. Engine route classification mirrors the four
 * design-token families (see tailwind.config.ts). Extend as features land.
 *
 * These are the UI-facing types. Backend-aligned contract types live in
 * `./api` (re-exported below); map between the two at the feature boundary.
 */
export * from './api';

import type { PendingActionPayload } from './api';

export type RouteEngine = 'planning' | 'scheduling' | 'query' | 'uncertain' | 'skill';

export type AuthLevel = 'auto' | 'confirm';

export type StatusKind = 'success' | 'warning' | 'error' | 'info';

/** The engine currently driving the right context panel (null = idle). */
export type ActiveEngine = 'planning' | 'scheduling' | 'query' | null;

/* ============================================================
   Conversation model
   ============================================================ */
export type ChatRole = 'user' | 'agent' | 'system';

export interface ClarifyOption {
  id: string;
  label: string;
  desc?: string;
  route?: RouteEngine;
}

interface BaseMessage {
  id: string;
  time?: string;
}

export interface SystemMessage extends BaseMessage {
  kind: 'system';
  text: string;
}

export interface UserMessage extends BaseMessage {
  kind: 'user';
  text: string;
  author?: string;
}

export interface AgentMessage extends BaseMessage {
  kind: 'agent';
  text?: string;
  /** Route the agent classified this turn into. */
  route?: RouteEngine;
  /** Router confidence 0–1. Omitted for slash-direct turns. */
  confidence?: number;
  reason?: string;
  /** Slash-command / manual route → zero-ambiguity direct routing. */
  slash?: boolean;
  slashCmd?: string;
  /** Whether a plan was handed off to the context panel. */
  handoff?: boolean;
  /** True while this turn is still streaming in (live, uncommitted). */
  streaming?: boolean;
  /** Latest execution progress line (streaming turns only). */
  progress?: string;
  /** Full thinking/progress trace for this turn (rendered as a collapsible log). */
  thinking?: string[];
  /** Write actions awaiting human confirmation (rendered as confirm cards). */
  pendingActions?: PendingActionPayload[];
}

export interface ClarifyMessage extends BaseMessage {
  kind: 'clarify';
  confidence: number;
  reason: string;
  question: string;
  detail?: string;
  options: ClarifyOption[];
  /** The option the user picked (set once answered). */
  selectedOptionId?: string;
}

export type ChatMessageData = SystemMessage | UserMessage | AgentMessage | ClarifyMessage;

/* ============================================================
   Composer selectors
   ============================================================ */
export type ComposerRoute = 'auto' | 'planning' | 'scheduling' | 'query';
export type ComposerMode = 'plan' | 'auto';
