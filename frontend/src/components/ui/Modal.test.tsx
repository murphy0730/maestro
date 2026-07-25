import { useState } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { Modal } from './Modal';

afterEach(cleanup);

describe('Modal', () => {
  it('renders children when open', () => {
    render(
      <Modal open onClose={() => {}} title="导入">
        内容
      </Modal>,
    );
    expect(screen.getByText('内容')).toBeTruthy();
    expect(screen.getByText('导入')).toBeTruthy();
    expect(screen.getByRole('dialog').className).toContain('max-w-[420px]');
    expect(screen.getByRole('dialog').className).toContain('sm:max-h-[min(80vh,760px)]');
  });

  it('does not render when closed', () => {
    render(
      <Modal open={false} onClose={() => {}} title="导入">
        内容
      </Modal>,
    );
    expect(screen.queryByText('内容')).toBeNull();
  });

  it('calls onClose on Escape and scrim click and X', () => {
    const onClose = vi.fn();
    render(
      <Modal open onClose={onClose} title="导入">
        x
      </Modal>,
    );
    fireEvent.keyDown(document.body, { key: 'Escape' });
    fireEvent.click(screen.getByRole('dialog').parentElement!);
    fireEvent.click(screen.getByRole('button', { name: /关闭|×/ }));
    expect(onClose).toHaveBeenCalledTimes(3);
  });

  it('does not close when the dialog interior is clicked', () => {
    const onClose = vi.fn();
    render(<Modal open onClose={onClose} title="导入"><button>内部操作</button></Modal>);
    fireEvent.click(screen.getByRole('dialog'));
    expect(onClose).not.toHaveBeenCalled();
  });

  it('keeps label, Escape and scrim behaviour when the caller draws its own chrome', () => {
    const onClose = vi.fn();
    render(<Modal open chrome={false} onClose={onClose} title="设置 · Settings"><button>内部操作</button></Modal>);
    const dialog = screen.getByRole('dialog', { name: '设置 · Settings' });
    expect(screen.queryByRole('button', { name: '关闭' })).toBeNull();
    fireEvent.click(dialog);
    fireEvent.keyDown(document.body, { key: 'Escape' });
    fireEvent.click(dialog.parentElement!);
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it('traps Tab focus and restores focus to the opener after close', () => {
    function Harness() {
      const [open, setOpen] = useState(false);
      return <><button onClick={() => setOpen(true)}>打开设置</button><Modal open={open} onClose={() => setOpen(false)} title="设置"><button>第一个</button><button>最后一个</button></Modal></>;
    }
    render(<Harness />);
    const opener = screen.getByRole('button', { name: '打开设置' });
    opener.focus();
    fireEvent.click(opener);
    const close = screen.getByRole('button', { name: '关闭' });
    const last = screen.getByRole('button', { name: '最后一个' });
    last.focus();
    fireEvent.keyDown(document, { key: 'Tab' });
    expect(document.activeElement).toBe(close);
    fireEvent.click(close);
    expect(document.activeElement).toBe(opener);
  });
});
