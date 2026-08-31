import { useState, useEffect, useMemo } from "react";
import { ConversationList } from "@/components/messaging/ConversationList";
import { ChatThread } from "@/components/messaging/ChatThread";
import { useConversations } from "@/hooks/useConversations";

export default function Messages() {
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(null);
  const [isMobile, setIsMobile] = useState(false);

  const { data: conversationsData, isPending } = useConversations();
  const conversations = conversationsData?.data ?? [];
  const showSkeleton = isPending && !conversationsData;

  const selectedConversation = useMemo(
    () => conversations.find((c) => c.id === selectedConversationId) ?? null,
    [conversations, selectedConversationId],
  );

  useEffect(() => {
    const check = () => setIsMobile(window.innerWidth < 768);
    check();
    window.addEventListener("resize", check);
    return () => window.removeEventListener("resize", check);
  }, []);

  const showList = !isMobile || !selectedConversationId;
  const showChat = !isMobile || !!selectedConversationId;

  return (
    <div className="flex h-[calc(100vh-64px)] overflow-hidden">
      {showList && (
        <div className={`${isMobile ? "w-full" : "w-[360px] border-r"} flex-shrink-0`}>
          <ConversationList
            conversations={conversations}
            selectedId={selectedConversationId ?? undefined}
            onSelect={(id) => setSelectedConversationId(id)}
            isLoading={showSkeleton}
          />
        </div>
      )}

      {showChat && (
        <div className="flex-1 min-w-0">
          <ChatThread
            conversation={selectedConversation}
            onBack={isMobile ? () => setSelectedConversationId(null) : undefined}
            showBackButton={isMobile}
          />
        </div>
      )}
    </div>
  );
}
