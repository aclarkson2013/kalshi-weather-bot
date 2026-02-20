"use client";

/**
 * Client-side providers wrapper.
 *
 * This component is the "use client" boundary for context providers
 * that need to wrap the entire app. The root layout.tsx is a server
 * component, so client providers must be in a separate file.
 */

import { ToastProvider } from "@/components/ui/toast";
import { WebSocketProvider } from "@/lib/websocket";

export default function Providers({ children }: { children: React.ReactNode }) {
  return (
    <WebSocketProvider>
      <ToastProvider>{children}</ToastProvider>
    </WebSocketProvider>
  );
}
