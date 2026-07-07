import type { ChatMessageData } from '@/types';
import type { StoredMessage } from '@/api/sessions';

const WELCOME: ChatMessageData = {
  id: 'sys-welcome',
  kind: 'system',
  text: '新会话 · 在下方描述排产 / 调度 / 查询需求开始',
};

/** 把后端 StoredMessage 列表转为前端 ChatMessageData。
 *  role=user→user；kind=system→system（居中细行）；其余→agent。 */
export function storedToThread(stored: StoredMessage[]): ChatMessageData[] {
  if (stored.length === 0) return [WELCOME];
  return [
    WELCOME,
    ...stored.map((m, i): ChatMessageData => {
      const time = m.ts
        ? new Date(m.ts).toLocaleTimeString('en-GB').slice(0, 5)
        : undefined;
      if (m.role === 'user') return { id: `hist-${i}`, kind: 'user', text: m.content, time };
      if (m.kind === 'system') return { id: `hist-${i}`, kind: 'system', text: m.content };
      return { id: `hist-${i}`, kind: 'agent', text: m.content, time };
    }),
  ];
}
