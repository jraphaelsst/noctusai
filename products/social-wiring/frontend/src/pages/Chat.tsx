/**
 * Chat page — standalone public `/chat` route wrapping the shared ChatPanel.
 *
 * The Agente UI itself now lives in `components/ChatPanel.tsx` so it can ALSO
 * render as the default "Chat" sub-tab of the YouTube → Upload page. This
 * route stays for direct / public access (the chat backend is unauthenticated
 * by current product direction).
 */
import ChatPanel from "@/components/ChatPanel";

export default function Chat() {
  return (
    <div className="container mx-auto py-6 max-w-4xl">
      <ChatPanel />
    </div>
  );
}
