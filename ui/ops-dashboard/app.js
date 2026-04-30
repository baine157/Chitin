const fallback = {
  generated_at: new Date().toISOString(),
  overall: {
    state: "needs_attention",
    headline: "Embedded sample data is active until local observability state is available.",
    last_checked: "local fallback",
  },
  needs_baine: [
    {
      id: "external-autonomy-scope",
      need: "Phase 4+ autonomy",
      notes: "No standing external commit authority is assumed.",
      waiting_on: "principal",
      status: "waiting",
    },
  ],
  deadlines: [
    {
      id: "weekend-openclaw-health-lane",
      next_review: "each heartbeat cycle",
      notes: "Advance one bounded packet and escalate only on alert conditions.",
      owner: "CoS",
      status: "active",
    },
  ],
  in_motion: [
    {
      id: "control-surface",
      priority: "P2",
      owner: "Codex",
      status: "active",
      notes: "Local read-only executive dashboard for CoS observability.",
    },
  ],
  waiting_blocked: [],
  done_with_proof: [
    {
      title: "Dashboard fallback loaded",
      status: "DONE",
      proof: "ui/ops-dashboard/app.js",
    },
  ],
  risk_watch: [
    {
      title: "Data freshness",
      severity: "Watch",
      risk: ["state/observability/dashboard.json was not loaded."],
    },
  ],
  system_trust: {
    posture: "local-first, read-only, approval-bound for external effects",
    collector_boundaries: { reads: "local files only", external_effect: false },
  },
};

const DEFAULT_REFRESH_MS = 5000;
const MIN_REFRESH_MS = 5000;
const MAX_REFRESH_MS = 300000;

function refreshMsFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const seconds = Number(params.get("refreshSec"));
  if (Number.isFinite(seconds) && seconds > 0) {
    return Math.max(MIN_REFRESH_MS, Math.min(MAX_REFRESH_MS, Math.round(seconds * 1000)));
  }
  const ms = Number(params.get("refreshMs"));
  if (Number.isFinite(ms) && ms > 0) {
    return Math.max(MIN_REFRESH_MS, Math.min(MAX_REFRESH_MS, Math.round(ms)));
  }
  return DEFAULT_REFRESH_MS;
}

const AUTO_REFRESH_MS = refreshMsFromUrl();
let loadInFlight = false;

const statusLabel = {
  needs_attention: "Needs Attention",
  clear: "All Clear",
  risk: "Risk",
  blocked: "Blocked",
};

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[char]);
}

function tagClass(value) {
  const v = String(value || "").toLowerCase();
  if (v.includes("high") || v.includes("needs")) return "high";
  if (v.includes("medium") || v.includes("watch") || v.includes("waiting")) return "medium";
  if (v.includes("clear") || v.includes("done") || v.includes("ok")) return "clear";
  return "watch";
}

function titleOf(item) {
  return item.title || item.id || item.objective || item.need || item.needed_for || "Untitled item";
}

function detailOf(item) {
  const value = item.why_it_matters || item.notes || item.objective || item.next_step || item.next_best_action || item.proof || item.risk || item.verification;
  return compact(value);
}

function compact(value) {
  if (Array.isArray(value)) return value.map(compact).filter(Boolean).join(" · ");
  if (value && typeof value === "object") {
    if (value.verification) return compact(value.verification);
    if (value.evidence_required) return compact(value.evidence_required);
    return Object.entries(value)
      .map(([key, entry]) => `${key}: ${compact(entry)}`)
      .join(" · ");
  }
  return String(value ?? "");
}

function sourceOf(item) {
  return item.source_file || item.artifact || item.path || "";
}

function nextAction(data) {
  const primary = data.overall?.next_best_action || data.needs_baine?.[0]?.next_best_action || "Review today's highest-priority item.";
  const detail = data.overall?.next_action_detail || data.needs_baine?.[0]?.why_it_matters || "";
  const item = data.needs_baine?.[0] || {};
  return {
    primary,
    detail,
    deadline: item.deadline || data.deadlines?.[0]?.label || "today",
    title: item.title || data.deadlines?.[0]?.title || "CoS priority",
  };
}

function authorityState(data) {
  const trust = data.system_trust || {};
  const externalOff = trust.collector_boundaries?.external_effect === false;
  return {
    label: externalOff ? "External Actions Off" : "External Actions Review",
    detail: data.overall?.authority_state || trust.posture || "Approval-bound for external effects.",
    mode: externalOff ? "clear" : "medium",
  };
}

function taskCard(item) {
  const sev = tagClass(item.severity || item.level || item.status);
  return `
    <article class="task ${sev}">
      <div class="task-head">
        <h3>${esc(titleOf(item))}</h3>
        <span class="tag ${sev}">${esc(item.priority || item.deadline || item.level || item.status || item.severity || "watch")}</span>
      </div>
      <p>${esc(detailOf(item))}</p>
      <div class="meta">
        <span><b>Next:</b> ${esc(item.next_best_action || item.next_step || item.next_review || item.waiting_on || "Review")}</span>
        <span><b>Owner:</b> ${esc(item.owner || item.authority?.source || "CoS")}</span>
      </div>
      ${sourceOf(item) ? `<div class="source">${esc(sourceOf(item))}</div>` : ""}
    </article>
  `;
}

function trustMetric(label, value) {
  const display = value ?? "unknown";
  const cls = tagClass(value);
  return `
    <section class="panel metric ${cls}">
      <strong>${esc(label)}</strong>
      <span>${esc(display)}</span>
    </section>
  `;
}

function signalPill(label, value, tone = "") {
  return `
    <div class="signal ${tagClass(tone || value)}">
      <span>${esc(label)}</span>
      <strong>${esc(value ?? "unknown")}</strong>
    </div>
  `;
}

function packetExecutionMetrics(data) {
  const trust = data.system_trust || {};
  const summary = data.packet_execution?.summary;
  const hasPacketSummary = Boolean(
    summary &&
    typeof summary === "object" &&
    (
      summary.blocked_count !== undefined ||
      summary.closeout_count !== undefined ||
      summary.done_count !== undefined ||
      summary.partial_count !== undefined
    )
  );
  const fallbackQueue = trust.queue_supervisor?.last_snapshot || {};
  const source = hasPacketSummary ? summary : fallbackQueue;
  return {
    source_label: hasPacketSummary ? "packet_execution.summary" : "queue_supervisor.last_snapshot",
    blocked_count: source.blocked_count ?? 0,
    closeout_count: source.closeout_count ?? 0,
    done_count: source.done_count ?? 0,
    partial_count: source.partial_count ?? 0,
    queue_count: fallbackQueue.queue_count ?? 0,
  };
}

function deadlineRow(item) {
  return `
    <div class="row">
      <div class="date">${esc(item.label || item.next_review || item.deadline || item.status || "Next")}</div>
      <div>
        <div class="row-title">${esc(titleOf(item))}</div>
        <div class="sub">${esc(item.notes || item.urgency || item.owner || "watch")}</div>
      </div>
    </div>
  `;
}

function proofRow(item) {
  return `
    <div class="row">
      <div class="date">${esc(item.status || "done")}</div>
      <div>
        <div class="row-title">${esc(titleOf(item))}</div>
        <div class="sub">${esc(compact(item.proof || item.verification || item.artifacts || item.source_file || "Proof pending"))}</div>
      </div>
    </div>
  `;
}

function trustBar(data) {
  const trust = data.system_trust || {};
  const queue = trust.queue_supervisor?.last_snapshot || {};
  const packets = packetExecutionMetrics(data);
  const security = trust.security_baseline || {};
  const boundaries = trust.collector_boundaries || {};
  return `
    <section class="panel pad proof-boundary">
      <div class="panel-title">
        <div>
          <h2>Proof / Boundaries</h2>
          <p class="section-note">${esc(trust.posture || "Local-first, proof-bearing, approval-bound.")}</p>
        </div>
        <span class="count">${esc(trust.collector_boundaries?.external_effect === false ? "read-only" : "review")}</span>
      </div>
      <div class="trust-grid">
        ${trustMetric("Collector Boundary", `reads: ${compact(boundaries.reads || "unknown")}`)}
        ${trustMetric("Queue", `queued ${queue.queue_count ?? "?"}`)}
        ${trustMetric("Packet Truth", `blocked ${packets.blocked_count} · done ${packets.done_count} · closeouts ${packets.closeout_count}`)}
        ${trustMetric("Proof", `${packets.source_label}: done ${packets.done_count} · closeouts ${packets.closeout_count}`)}
        ${trustMetric("Security Watch", `${security.high_count ?? "?"} high · ${security.medium_count ?? "?"} medium`)}
      </div>
    </section>
  `;
}

function render(data) {
  const trust = data.system_trust || {};
  const action = nextAction(data);
  const authority = authorityState(data);
  const headline = data.overall?.headline || `Loaded ${data.generated_from || "local"} observability state.`;
  const state = data.overall?.state || (data.waiting_blocked?.length ? "needs_attention" : "clear");
  const lastChecked = data.overall?.last_checked || data.generated_at || trust.queue_supervisor?.last_run_at || "unknown";
  const refreshedAt = data.ui_refreshed_at || "unknown";
  const refreshSec = Math.round(AUTO_REFRESH_MS / 1000);
  const security = trust.security_baseline || {};
  const packets = packetExecutionMetrics(data);
  document.getElementById("app").innerHTML = `
    <header class="topbar">
      <div>
        <p class="eyebrow">BearClaw on Z420</p>
        <h1>Principal Control Panel</h1>
        <p class="headline">${esc(headline)}</p>
      </div>
      <div class="status-pill"><span class="dot"></span>${esc(statusLabel[state] || state)}</div>
    </header>

    <section class="command">
      <div class="mountain-mark" aria-hidden="true">
        <img src="./assets/boba-fun-bearclaw.png" alt="" />
      </div>
      <div class="next-card">
        <p class="eyebrow">Next Best Action</p>
        <h2>${esc(action.primary)}</h2>
        <p>${esc(action.detail)}</p>
        <div class="action-meta">
          ${signalPill("Item", action.title, "high")}
          ${signalPill("Deadline", action.deadline, "high")}
          ${signalPill("Freshness", lastChecked, "clear")}
        </div>
      </div>
      <div class="authority-card ${esc(authority.mode)}">
        <p class="eyebrow">Authority State</p>
        <h2>${esc(authority.label)}</h2>
        <p>${esc(authority.detail)}</p>
      </div>
    </section>

    <section class="strip">
      ${signalPill("Closeouts", packets.closeout_count, "watch")}
      ${signalPill("Blocked Packets", packets.blocked_count, packets.blocked_count > 0 ? "high" : "clear")}
      ${signalPill("Done Packets", packets.done_count, "clear")}
      ${signalPill("Security", `${security.high_count ?? "?"} high / ${security.medium_count ?? "?"} medium`, (security.high_count ?? 0) > 0 ? "high" : "watch")}
      ${signalPill("External Effects", trust.collector_boundaries?.external_effect === false ? "off" : "review", "clear")}
      ${signalPill("Sources", `${Object.keys(trust.source_health || {}).length || "fallback"} checked`, "clear")}
    </section>

    ${trustBar(data)}

    <section class="grid">
      <section class="panel pad">
        <div class="panel-title"><h2>Needs Baine</h2><span class="count">${data.needs_baine?.length || 0} items</span></div>
        <div class="cards">${(data.needs_baine || []).map(taskCard).join("") || "<p>No human-action items.</p>"}</div>
      </section>

      <section class="panel pad">
        <div class="panel-title"><h2>Deadline Ladder</h2><span class="count">actionable only</span></div>
        <div class="deadline-list">${(data.deadlines || []).map(deadlineRow).join("")}</div>
      </section>
    </section>

    <section class="two-col">
      <section class="panel pad">
        <div class="panel-title"><h2>In Motion</h2><span class="count">${data.in_motion?.length || 0}</span></div>
        <div class="cards">${(data.in_motion || []).map(taskCard).join("") || "<p>No active delegated work.</p>"}</div>
      </section>
      <section class="panel pad">
        <div class="panel-title"><h2>Waiting / Blocked</h2><span class="count">${data.waiting_blocked?.length || 0}</span></div>
        <div class="cards">${(data.waiting_blocked || []).map(taskCard).join("") || "<p>No blocked packets recorded.</p>"}</div>
      </section>
    </section>

    <section class="two-col">
      <section class="panel pad">
        <div class="panel-title"><h2>Done With Proof</h2><span class="count">latest evidence</span></div>
        <div class="proof-list">${(data.done_with_proof || []).map(proofRow).join("")}</div>
      </section>
      <section class="panel pad">
        <div class="panel-title"><h2>Risk Watch</h2><span class="count">${data.risk_watch?.length || 0}</span></div>
        <div class="cards">${(data.risk_watch || []).map(taskCard).join("")}</div>
      </section>
    </section>

    <footer>Last generated ${esc(lastChecked)} · Refreshed ${esc(refreshedAt)} · Auto-refresh ${esc(refreshSec)}s · Local read-only dashboard · Source: state/observability/dashboard.json</footer>
  `;
}

async function load() {
  if (loadInFlight) return;
  loadInFlight = true;

  const paths = [
    "/state/observability/dashboard.json",
    "../../state/observability/dashboard.json",
  ];

  try {
    for (const path of paths) {
      try {
        const res = await fetch(path, { cache: "no-store" });
        if (res.ok) {
          const payload = await res.json();
          payload.ui_refreshed_at = new Date().toLocaleTimeString();
          render(payload);
          return;
        }
      } catch (_) {
        // Try next path.
      }
    }
    const fallbackView = { ...fallback, ui_refreshed_at: new Date().toLocaleTimeString() };
    render(fallbackView);
  } finally {
    loadInFlight = false;
  }
}

load();
setInterval(load, AUTO_REFRESH_MS);
