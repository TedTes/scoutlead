import { Check, Send } from "lucide-react";
import { useEffect, useState } from "react";
import { useAppData } from "../state/app-data";
import { StatusPill, useToast } from "../shared-ui";
import type { Message } from "../types/domain";
import { statusTone } from "../utils/status";

type MessageDraft = Pick<Message, "subject" | "body" | "approach_tag">;

export function ApprovalsScreen() {
  const { gmailConnectionStatus, snapshot, updateMessage, approveMessage, sendMessage, cancelMessage } = useAppData();
  const { showToast } = useToast();
  const gmailConnected = Boolean(gmailConnectionStatus?.connected);
  const approvalMessages = snapshot.messages.filter((message) =>
    ["pending_approval", "approved"].includes(message.status),
  );
  const [drafts, setDrafts] = useState<Record<string, MessageDraft>>({});

  useEffect(() => {
    setDrafts(
      Object.fromEntries(
        approvalMessages.map((message) => [
          message.id,
          {
            subject: message.subject || "",
            body: message.body,
            approach_tag: message.approach_tag,
          },
        ]),
      ),
    );
  }, [snapshot.messages]);

  return (
    <>
      <div className="approval-list">
        {approvalMessages.length === 0 ? (
          <article className="approval-card">
            <div className="draft">
              <p className="empty-copy">No outreach drafts are waiting for approval.</p>
            </div>
          </article>
        ) : (
          approvalMessages.map((message) => {
            const contact = snapshot.results.find((item) => item.id === message.lead_id);
            const sendBlockedByGmail = message.status === "approved" && !gmailConnected;
            const draft = drafts[message.id] || {
              subject: message.subject || "",
              body: message.body,
              approach_tag: message.approach_tag,
            };
            return (
              <article className="approval-card" key={message.id}>
                <header>
                  <strong>{contact?.company_name || "Unknown contact"}</strong>
                  <span>{contact?.research?.contact_name || contact?.contact_email || "No contact captured"}</span>
                  <div>
                    <StatusPill tone="blue">Angle - {message.approach_tag}</StatusPill>
                    <StatusPill tone={statusTone(message.status)}>{message.status}</StatusPill>
                  </div>
                </header>
                <div className="draft editable-draft">
                  <label className="field">
                    <span>Subject</span>
                    <input
                      value={draft.subject || ""}
                      onChange={(event) =>
                        setDrafts((current) => ({
                          ...current,
                          [message.id]: { ...draft, subject: event.target.value },
                        }))
                      }
                    />
                  </label>
                  <label className="field">
                    <span>Body</span>
                    <textarea
                      rows={8}
                      value={draft.body}
                      onChange={(event) =>
                        setDrafts((current) => ({
                          ...current,
                          [message.id]: { ...draft, body: event.target.value },
                        }))
                      }
                    />
                  </label>
                </div>
                <footer>
                  <div>
                    <button className="secondary" onClick={() => updateMessage(message.id, draft)}>
                      Save
                    </button>
                    <button
                      className="success"
                      disabled={message.status === "approved"}
                      onClick={() => approveMessage(message.id)}
                    >
                      <Check size={14} />
                      Approve
                    </button>
                    <button
                      disabled={message.status !== "approved" || !gmailConnected}
                      onClick={() => {
                        if (!window.confirm("Send this approved message now?")) return;
                        void sendMessage(message.id)
                          .then(() => showToast({ title: "Email sent", tone: "green" }))
                          .catch((err) => {
                            const message = err instanceof Error ? err.message : String(err);
                            showToast({ title: "Send failed", message, tone: "red" });
                          });
                      }}
                    >
                      <Send size={14} />
                      Send
                    </button>
                    <button className="danger" onClick={() => cancelMessage(message.id)}>
                      Reject
                    </button>
                  </div>
                  {sendBlockedByGmail ? (
                    <p className="approval-send-warning">Connect Gmail in Integrations before sending.</p>
                  ) : null}
                  <span>Generated by ScoutLead - personalized from public contact context</span>
                </footer>
              </article>
            );
          })
        )}
      </div>
    </>
  );
}
