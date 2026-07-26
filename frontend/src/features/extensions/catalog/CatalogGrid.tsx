import { Check, SearchX } from 'lucide-react';
import { Badge } from '@/components/ui/Badge';
import { EmptyState, ExtensionIcon } from '../shared';

export interface CatalogCard {
  key: string;
  title: string;
  subtitle: string;
  description: string;
  tags: string[];
  /** 已经装在本机的条目，只显示状态，不给安装入口。 */
  installed?: boolean;
}

/**
 * 浏览目录的卡片矩阵。条目点击只打开详情——远程安装要等后端 SkillHub /
 * ConnectorCatalog 落地，这里不假装能装。
 */
export function CatalogGrid({
  items,
  onOpen,
  emptyTitle,
}: {
  items: CatalogCard[];
  onOpen: (key: string) => void;
  emptyTitle: string;
}) {
  if (items.length === 0) {
    return (
      <EmptyState
        icon={<SearchX size={34} />}
        title={emptyTitle}
        description="换个关键词或分类试试。"
      />
    );
  }
  return (
    <div className="grid grid-cols-[repeat(auto-fill,minmax(258px,1fr))] gap-[12px]">
      {items.map((item) => (
        <button
          key={item.key}
          type="button"
          onClick={() => onOpen(item.key)}
          className="rounded-lg border border-border-subtle bg-surface-2 p-[14px] text-left transition duration-fast ease-out hover:-translate-y-[2px] hover:border-border-strong hover:shadow-elev-2"
        >
          <span className="flex items-start gap-[11px]">
            <ExtensionIcon name={item.title} size={38} />
            <span className="min-w-0 flex-1">
              <span className="block text-[13px] font-semibold leading-[1.4] text-text-primary">
                {item.title}
              </span>
              <span className="mt-px block truncate text-[10.5px] text-text-tertiary">
                {item.subtitle}
              </span>
            </span>
            {item.installed && (
              <Badge tone="success" icon={<Check size={10} />}>
                已安装
              </Badge>
            )}
          </span>
          <span className="mt-[9px] line-clamp-2 block min-h-[37px] text-[12px] leading-[1.55] text-text-secondary">
            {item.description}
          </span>
          <span className="mt-[11px] flex flex-wrap items-center gap-[8px]">
            {item.tags.map((tag) => (
              <Badge key={tag}>{tag}</Badge>
            ))}
          </span>
        </button>
      ))}
    </div>
  );
}
