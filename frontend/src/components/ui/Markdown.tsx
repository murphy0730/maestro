import type { ComponentPropsWithoutRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

/**
 * Markdown — renders an agent reply (GFM: headings, bold, lists, tables, hr,
 * code) with the app's dark design tokens, so the chat bubble never shows raw
 * `#`, `*`, `|` symbols. Element styling is mapped inline (no Typography plugin).
 */
type Props = ComponentPropsWithoutRef<'div'>;

// react-markdown v9 passes a hast `node` prop to each override; strip it so it
// never lands on a DOM element (React would warn about an unknown attribute).
const components: React.ComponentProps<typeof ReactMarkdown>['components'] = {
  h1: ({ node, ...p }) => (
    <h1 className="mb-2 mt-3 text-h4 font-semibold text-text-primary first:mt-0" {...p} />
  ),
  h2: ({ node, ...p }) => (
    <h2 className="mb-2 mt-3 text-body-lg font-semibold text-text-primary first:mt-0" {...p} />
  ),
  h3: ({ node, ...p }) => (
    <h3 className="mb-1 mt-3 text-body font-semibold text-text-primary first:mt-0" {...p} />
  ),
  p: ({ node, ...p }) => <p className="my-2 leading-relaxed first:mt-0 last:mb-0" {...p} />,
  ul: ({ node, ...p }) => (
    <ul className="my-2 list-disc space-y-1 pl-5 marker:text-text-tertiary" {...p} />
  ),
  ol: ({ node, ...p }) => (
    <ol className="my-2 list-decimal space-y-1 pl-5 marker:text-text-tertiary" {...p} />
  ),
  li: ({ node, ...p }) => <li className="leading-relaxed" {...p} />,
  strong: ({ node, ...p }) => <strong className="font-semibold text-text-primary" {...p} />,
  em: ({ node, ...p }) => <em className="italic" {...p} />,
  a: ({ node, ...p }) => (
    <a
      className="text-accent-fg underline underline-offset-2"
      target="_blank"
      rel="noreferrer"
      {...p}
    />
  ),
  hr: () => <hr className="my-3 border-border-subtle" />,
  blockquote: ({ node, ...p }) => (
    <blockquote className="my-2 border-l-2 border-border-default pl-3 text-text-secondary" {...p} />
  ),
  code: ({ node, className, ...rest }) => {
    const inline = !className?.includes('language-');
    return inline ? (
      <code
        className="rounded-xs bg-surface-inset px-[5px] py-[1px] font-mono text-mono-sm text-accent-fg"
        {...rest}
      />
    ) : (
      <code className={`font-mono text-mono-sm ${className ?? ''}`} {...rest} />
    );
  },
  pre: ({ node, ...p }) => (
    <pre
      className="my-2 overflow-x-auto rounded-md border border-border-subtle bg-surface-inset p-3 text-mono-sm leading-relaxed"
      {...p}
    />
  ),
  table: ({ node, ...p }) => (
    <div className="my-2 overflow-x-auto rounded-md border border-border-default">
      <table className="w-full border-collapse text-body-sm" {...p} />
    </div>
  ),
  thead: ({ node, ...p }) => <thead className="bg-surface-3" {...p} />,
  th: ({ node, ...p }) => (
    <th
      className="border-b border-border-default px-[10px] py-[6px] text-left font-semibold text-text-primary"
      {...p}
    />
  ),
  td: ({ node, ...p }) => (
    <td className="border-b border-border-subtle px-[10px] py-[6px] align-top" {...p} />
  ),
};

export function Markdown({ children, className = '' }: Props & { children?: string }) {
  return (
    <div className={`text-body text-text-primary ${className}`}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {children ?? ''}
      </ReactMarkdown>
    </div>
  );
}
