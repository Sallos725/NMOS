// Shapes of PocketRisu data the adapter reads (see PocketRisu src/ts/storage/database.svelte.ts).

export interface HostMessage {
  role: 'user' | 'char';
  data: string;
  chatId?: string;
  saying?: string;
  name?: string;
  otherUser?: boolean;
  isComment?: boolean;
  disabled?: boolean | 'allBefore';
  swipes?: string[];
  swipeId?: number;
  generationInfo?: { generationId?: string };
}

export interface HostChat {
  id?: string;
  name?: string;
  /** Id of the persona bound to this chat, if any (the host then uses it instead of the selected one). */
  bindedPersona?: string;
  message: HostMessage[];
}

/** The host's personas and the selected one (`getDatabase(['personas', 'selectedPersona'])`). */
export interface HostPersonas {
  personas: { id?: string; name?: string }[];
  selected: number;
}

export interface PromptMessage {
  role: string;
  content: unknown;
  [key: string]: unknown;
}

export interface ManifestMessage {
  host_logical_id: string;
  revision_hash: string;
  role: 'user' | 'char';
  name: string | null;
  disabled: boolean | 'allBefore' | null;
  is_comment: boolean | null;
  swipe_id: number | null;
  swipe_count: number;
  generation_id: string | null;
  special_comments: string[];
}

export interface Body {
  host_logical_id: string;
  revision_hash: string;
  content: string;
  metadata: Record<string, unknown>;
}

export interface ReconcileRequest {
  host: 'pocketrisu';
  chat_id: string;
  character_ref: string | null;
  /** Display labels for the inspector (bot and chat names); never identity. */
  character_name?: string;
  chat_name?: string;
  /** The user's persona name in this chat (ADR 0023): the sidecar resolves it as `{{user}}`. */
  persona_name?: string;
  hash_version: 1;
  messages: ManifestMessage[];
}
