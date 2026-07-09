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
  defaultEngine: 'auto' as const,
  onSetDefaultEngine: () => {},
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
  it('opens the root settings menu with all entries in Electron', () => {
    setElectron(true);
    render(<Sidebar {...baseProps} />);
    fireEvent.click(screen.getByTitle('设置'));
    expect(screen.queryByText('外观')).toBeTruthy();
    expect(screen.queryByText('默认引擎')).toBeTruthy();
    expect(screen.queryByText('模型')).toBeTruthy();
    expect(screen.queryByText('个性化')).toBeTruthy();
  });

  it('opens the root settings menu with all entries in browser dev too', () => {
    setElectron(false);
    render(<Sidebar {...baseProps} />);
    fireEvent.click(screen.getByTitle('设置'));
    expect(screen.queryByText('模型')).toBeTruthy();
    expect(screen.queryByText('个性化')).toBeTruthy();
  });
});
