import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen, fireEvent } from '@testing-library/react';
import { Sidebar } from './Sidebar';

const baseProps = {
  appName: 'Maestro',
  user: 'u',
  role: 'r',
  conversations: [],
  activeId: '',
  onSelect: () => {},
  onNewConversation: () => {},
  onRenameSession: () => {},
  onDeleteSession: () => {},
  onCollapse: () => {},
  theme: 'light' as const,
  onSetTheme: () => {},
};

function setElectron(on: boolean) {
  const w = window as unknown as { electronAPI?: unknown };
  if (on) {
    w.electronAPI = {
      isElectron: true,
      providers: {
        get: () => Promise.resolve(undefined),
        save: () => Promise.resolve({ ok: true }),
      },
      onBackendReconnecting: () => () => {},
    };
  } else {
    delete w.electronAPI;
  }
}

afterEach(cleanup);

describe('Sidebar settings menu', () => {
  it('shows the provider menu item in Electron', () => {
    setElectron(true);
    render(<Sidebar {...baseProps} />);
    fireEvent.click(screen.getByTitle('设置'));
    expect(screen.queryByText('LLM / Embedding 供应商…')).toBeTruthy();
  });

  it('hides the provider menu item in browser dev', () => {
    setElectron(false);
    render(<Sidebar {...baseProps} />);
    fireEvent.click(screen.getByTitle('设置'));
    expect(screen.queryByText('LLM / Embedding 供应商…')).toBeNull();
  });
});
