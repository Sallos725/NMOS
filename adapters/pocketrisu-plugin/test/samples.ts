// Revision-hash vector inputs, shared by the vector tests (keep the exact bytes: one is NFD).
import type { HostMessage } from '../src/types';

export const samples: HostMessage[] = [
  { role: 'user', data: 'plain ascii', chatId: 'u1' },
  { role: 'user', data: 'windows\r\nline\r\nendings  ', chatId: 'u2' },
  { role: 'char', data: '한국어 메시지와 이모지 🎐', chatId: 'c1', generationInfo: { generationId: 'c1' }, saying: 'char-1' },
  { role: 'char', data: 'Café NFD → NFC', chatId: 'c2', name: 'Hinata', disabled: true },
  { role: 'char', data: 'B', swipes: ['A', 'B'], swipeId: 0, chatId: 'c3', generationInfo: { generationId: 'g3' } },
  { role: 'user', data: 'quote " backslash \\ tab\t ctrl del', chatId: 'u3', disabled: 'allBefore', otherUser: false },
  { role: 'char', data: '{{specialcomment::branchedfrom::o::Name::m::}}', chatId: 'c4', isComment: true, disabled: true },
  { role: 'user', data: 'lone surrogate \ud800 here', chatId: 'u4' },
];
