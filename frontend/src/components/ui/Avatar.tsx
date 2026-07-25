/**
 * Avatar — 设计系统 v2 的 `.u-av`：cyan → violet 渐变的操作员头像。
 * 侧栏底部、折叠轨与用户消息共用同一枚标识。
 */
interface AvatarProps {
  name: string;
  size?: number;
  /** 无障碍名称；作为纯装饰重复出现时传 false。 */
  labelled?: boolean;
  className?: string;
}

export function Avatar({ name, size = 28, labelled = true, className = '' }: AvatarProps) {
  const initial = name.trim().slice(0, 1) || '·';
  return (
    <span
      aria-label={labelled ? name : undefined}
      aria-hidden={labelled ? undefined : true}
      style={{ width: size, height: size, fontSize: Math.round(size * 0.39) }}
      className={`avatar-gradient grid flex-none place-items-center rounded-full font-medium leading-none ${className}`}
    >
      {initial}
    </span>
  );
}
