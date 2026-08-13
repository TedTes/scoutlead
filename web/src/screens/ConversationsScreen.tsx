import { useEffect, useMemo, useState } from "react";
import { useAppData } from "../state/app-data";
import { Card, ConversationStat, PageHeader, StatusPill } from "../shared-ui";
import type { Conversation } from "../types/domain";
import { formatDate } from "../utils/format";
import { statusTone } from "../utils/status";

export function ConversationsScreen() {
  const { snapshot, recordResponse, manuallyClassifyResponse } = useAppData();
  const conversations = snapshot.conversations;
  const [selectedConversationId, setSelectedConversationId] = useState("");
  const [responseBody, setResponseBody] = useState("");
  const selectedConversation =
    conversations.find((conversation) => conversation.id === selectedConversationId) || conversations[0];

  useEffect(() => {
    if (!selectedConversationId && conversations[0]) {
      setSelectedConversationId(conversations[0].id);
    }
  }, [conversations, selectedConversationId]);

  const intentCounts = useMemo(() => countIntents(conversations), [conversations]);

  return (
    <>
      <PageHeader
        title="Conversations"
        subtitle="Replies captured and auto-classified. Confirm or reclassify to train targeting."
      />

      <div className="stat-grid six">
        <ConversationStat label="Interview" value={String(intentCounts.interview_request)} tone="green" />
        <ConversationStat label="Interested" value={String(intentCounts.interested)} tone="green" />
        <ConversationStat label="Question" value={String(intentCounts.question)} tone="blue" />
        <ConversationStat label="Not interested" value={String(intentCounts.not_interested)} tone="red" />
        <ConversationStat label="Trial" value={String(intentCounts.product_trial_interest)} tone="green" />
        <ConversationStat label="Unknown" value={String(intentCounts.unknown)} tone="gray" />
      </div>

      <div className="conversation-grid">
        <Card title="Threads">
          {conversations.length === 0 ? (
            <p className="empty-copy">No conversations yet. Send an approved message first.</p>
          ) : (
            <div className="thread-list">
              {conversations.map((conversation) => {
                const lead = snapshot.leads.find((item) => item.id === conversation.lead_id);
                const latest = conversation.events[conversation.events.length - 1];
                return (
                  <button
                    className={conversation.id === selectedConversation?.id ? "thread active" : "thread"}
                    key={conversation.id}
                    onClick={() => setSelectedConversationId(conversation.id)}
                  >
                    <strong>
                      {lead?.company_name || "Unknown lead"}
                      <span>{conversation.events.length} msgs</span>
                    </strong>
                    <StatusPill tone={statusTone(conversation.status)}>{conversation.status}</StatusPill>
                    <time>{formatDate(latest?.created_at)}</time>
                  </button>
                );
              })}
            </div>
          )}
        </Card>

        <Card
          title={snapshot.leads.find((lead) => lead.id === selectedConversation?.lead_id)?.company_name || "Conversation"}
          meta={
            selectedConversation ? (
              <>
                <StatusPill tone={statusTone(selectedConversation.status)}>{selectedConversation.status}</StatusPill>
                <button
                  className="link-button"
                  onClick={() =>
                    manuallyClassifyResponse(selectedConversation.id, {
                      intent: "interested",
                      confidence: 100,
                      rationale: "Manually marked as interested by operator.",
                      follow_up_action: "reply",
                    })
                  }
                >
                  Mark interested
                </button>
              </>
            ) : undefined
          }
        >
          {!selectedConversation ? (
            <p className="empty-copy">Select a conversation.</p>
          ) : (
            <>
              <div className="chat">
                {selectedConversation.events.map((event) => (
                  <p className={event.direction === "outbound" ? "bubble outbound" : "bubble inbound"} key={event.id}>
                    {event.body}
                    <span>
                      {event.direction} - {formatDate(event.created_at)}
                      {event.classification
                        ? ` - ${event.classification.intent} (${event.classification.confidence}%)`
                        : ""}
                    </span>
                  </p>
                ))}
              </div>
              <div className="reply-box">
                <input
                  placeholder="Paste or type an inbound reply..."
                  value={responseBody}
                  onChange={(event) => setResponseBody(event.target.value)}
                />
                <button
                  disabled={!responseBody.trim()}
                  onClick={() => {
                    void recordResponse(selectedConversation.id, responseBody);
                    setResponseBody("");
                  }}
                >
                  Classify
                </button>
              </div>
            </>
          )}
        </Card>
      </div>
    </>
  );
}

function countIntents(conversations: Conversation[]) {
  const counts = {
    interested: 0,
    not_interested: 0,
    question: 0,
    interview_request: 0,
    product_trial_interest: 0,
    unknown: 0,
  };
  for (const conversation of conversations) {
    for (const event of conversation.events) {
      const intent = event.classification?.intent;
      if (intent && intent in counts) {
        counts[intent as keyof typeof counts] += 1;
      } else if (event.direction === "inbound") {
        counts.unknown += 1;
      }
    }
  }
  return counts;
}
