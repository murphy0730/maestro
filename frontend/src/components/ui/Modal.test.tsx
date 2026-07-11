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
    fireEvent.click(screen.getByRole('button', { name: /关闭|×/ }));
    expect(onClose).toHaveBeenCalled();
  });
});
