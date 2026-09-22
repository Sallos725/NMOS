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
  message: HostMessage[];
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
  hash_version: 1;
  messages: ManifestMessage[];
}
