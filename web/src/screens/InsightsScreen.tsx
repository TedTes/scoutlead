import { RefreshCw } from "lucide-react";
import { Card, StatusPill } from "../shared-ui";
import { useAppData } from "../state/app-data";
import { formatPercent } from "../utils/format";
import { statusTone } from "../utils/status";

export function InsightsScreen() {
  const { snapshot, selectedCampaign, generateCampaignInsight } = useAppData();
  const insight = snapshot.insight;
  const metrics = snapshot.metrics;

  return (
    <div className="insights-page">
      <Card
        title="Campaign insights"
        meta={
          <button
            className="secondary"
            type="button"
            disabled={!selectedCampaign}
            onClick={() => void generateCampaignInsight()}
          >
            <RefreshCw size={14} />
            Refresh
          </button>
        }
      >
        {!selectedCampaign ? (
          <p className="empty-copy">Select a campaign to see validation insights.</p>
        ) : !insight ? (
          <p className="empty-copy">No insight summary has been generated yet.</p>
        ) : (
          <div className="insight-summary">
            <div>
              <StatusPill tone={statusTone(insight.icp_verdict.verdict)}>
                {insight.icp_verdict.verdict.replace(/_/g, " ")}
              </StatusPill>
              <p>{insight.summary}</p>
            </div>
            <div>
              <span>Recommended action</span>
              <strong>{insight.icp_verdict.recommended_action}</strong>
              <em>{insight.icp_verdict.rationale}</em>
            </div>
          </div>
        )}
      </Card>

      <div className="stat-grid four">
        <div className="stat-card">
          <span>North star</span>
          <strong>{formatPercent(metrics?.north_star_value)}</strong>
          <em>{metrics?.north_star_metric?.replace(/_/g, " ") || "No metric"}</em>
        </div>
        <div className="stat-card">
          <span>Qualified leads</span>
          <strong>{metrics?.qualified_lead_count ?? 0}</strong>
        </div>
        <div className="stat-card">
          <span>Responses</span>
          <strong>{metrics?.response_count ?? 0}</strong>
        </div>
        <div className="stat-card">
          <span>Interviews</span>
          <strong>{metrics?.interview_request_count ?? 0}</strong>
        </div>
      </div>

      <Card title="Findings">
        {!insight?.findings.length ? (
          <p className="empty-copy">Findings appear after leads, replies, or disqualification patterns exist.</p>
        ) : (
          <div className="finding-list">
            {insight.findings.map((finding) => (
              <article className="finding-row" key={`${finding.theme}-${finding.summary}`}>
                <header>
                  <strong>{finding.theme}</strong>
                  <StatusPill tone={finding.confidence >= 70 ? "green" : "amber"}>
                    {finding.confidence}% confidence
                  </StatusPill>
                </header>
                <p>{finding.summary}</p>
                {finding.evidence.length ? (
                  <ul>
                    {finding.evidence.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                ) : null}
              </article>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
