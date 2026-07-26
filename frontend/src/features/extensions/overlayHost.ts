import { createContext, useContext } from 'react';

/**
 * Drawer 的挂载点：`<main>` 内的一个元素，让遮罩只盖扩展中心内容区，
 * 永远不盖左侧会话栏。由 ExtensionCenterLayout 填充。
 */
export const OverlayHostContext = createContext<HTMLElement | null>(null);

export const useExtensionOverlayHost = () => useContext(OverlayHostContext);
