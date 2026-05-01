const state = {
  token: localStorage.getItem("pantheon_token") || "",
  user: null,
  authMode: "login",
  templates: [],
  scenarios: [],
  labs: [],
  selectedLabId: localStorage.getItem("pantheon_selected_lab") || "",
  selectedScenarioId: "multi-stage-chain",
  simulation: null,
  report: null,
  loading: true,
  message: "",
  error: ""
};

const app = document.querySelector("#app");

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function riskBadge(risk) {
  const color = risk === "Critical" ? "red" : risk === "High" ? "amber" : risk === "Medium" ? "blue" : "green";
  return `<span class="badge ${color}">${escapeHtml(risk || "Unknown")}</span>`;
}

function statusBadge(status) {
  const color = status === "Running" ? "green" : status === "Stopped" ? "amber" : status === "Deleted" ? "red" : "blue";
  return `<span class="badge ${color}">${escapeHtml(status)}</span>`;
}

async function api(path, options = {}) {
  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {})
  };
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  const response = await fetch(path, { ...options, headers });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || `Request failed with status ${response.status}`);
  }
  return data;
}

function setMessage(message, isError = false) {
  state.message = isError ? "" : message;
  state.error = isError ? message : "";
  render();
}

async function boot() {
  state.loading = true;
  render();
  if (state.token) {
    try {
      const { user } = await api("/api/auth/me");
      state.user = user;
      await loadDashboard();
    } catch (error) {
      localStorage.removeItem("pantheon_token");
      state.token = "";
      state.user = null;
    }
  }
  state.loading = false;
  render();
}

async function loadDashboard() {
  const [templatesResult, scenariosResult, labsResult] = await Promise.all([
    api("/api/templates"),
    api("/api/scenarios"),
    api("/api/labs")
  ]);
  state.templates = templatesResult.templates;
  state.scenarios = scenariosResult.scenarios;
  state.labs = labsResult.labs;
  if (!state.selectedLabId && state.labs[0]) {
    state.selectedLabId = state.labs[0].id;
    localStorage.setItem("pantheon_selected_lab", state.selectedLabId);
  }
  if (state.selectedLabId && !state.labs.some((lab) => lab.id === state.selectedLabId)) {
    state.selectedLabId = state.labs[0]?.id || "";
    localStorage.setItem("pantheon_selected_lab", state.selectedLabId);
  }
}

function selectedLab() {
  return state.labs.find((lab) => lab.id === state.selectedLabId) || null;
}

function compatibleScenarios(lab) {
  if (!lab) return [];
  return state.scenarios.filter((scenario) => scenario.allowedTemplateIds.includes(lab.templateId));
}

function latestSimulationForLab(lab) {
  if (state.simulation && state.simulation.labId === lab?.id) return state.simulation;
  return lab?.latestSimulation || null;
}

function renderAuth() {
  const isRegister = state.authMode === "register";
  app.innerHTML = `
    <main class="auth-page">
      <section class="auth-panel">
        <div class="brand"><span class="brand-mark">P</span><span>Pantheon</span></div>
        <h2>${isRegister ? "Create your lab account" : "Sign in to the cyber-range"}</h2>
        <p>Run safe attack simulations, study paths, apply defenses, and generate evaluation reports.</p>
        ${state.error ? `<div class="alert">${escapeHtml(state.error)}</div>` : ""}
        ${state.message ? `<div class="success">${escapeHtml(state.message)}</div>` : ""}
        <div class="tabs" role="tablist">
          <button class="tab ${!isRegister ? "active" : ""}" data-action="auth-mode" data-mode="login">Login</button>
          <button class="tab ${isRegister ? "active" : ""}" data-action="auth-mode" data-mode="register">Register</button>
        </div>
        <form id="auth-form">
          ${
            isRegister
              ? `<div class="field">
                  <label for="name">Name</label>
                  <input id="name" name="name" autocomplete="name" value="Student Analyst" required />
                </div>`
              : ""
          }
          <div class="field">
            <label for="email">Email</label>
            <input id="email" name="email" type="email" autocomplete="email" value="demo@pantheon.local" required />
          </div>
          <div class="field">
            <label for="password">Password</label>
            <input id="password" name="password" type="password" autocomplete="${isRegister ? "new-password" : "current-password"}" value="pantheon123" required />
          </div>
          ${
            isRegister
              ? `<div class="field">
                  <label for="role">Role</label>
                  <select id="role" name="role">
                    <option>Student</option>
                    <option>Instructor</option>
                    <option>Admin</option>
                  </select>
                </div>`
              : ""
          }
          <div class="button-row">
            <button class="btn primary" type="submit">${isRegister ? "Create account" : "Login"}</button>
            <button class="btn ghost" type="button" data-action="demo-login">Use demo login</button>
          </div>
        </form>
        <div class="demo-note">
          Demo credentials: <strong>demo@pantheon.local</strong> / <strong>pantheon123</strong>.
          Admin: <strong>admin@pantheon.local</strong> / <strong>admin123</strong>.
        </div>
      </section>
      <section class="auth-visual" aria-label="Pantheon attack path illustration">
        <div class="auth-visual-content">
          <h1>Pantheon</h1>
          <p>Simulate attacks. Study paths. Strengthen defenses.</p>
        </div>
      </section>
    </main>
  `;
}

function renderDashboard() {
  const lab = selectedLab();
  const simulation = latestSimulationForLab(lab);
  app.innerHTML = `
    <main class="shell">
      <header class="topbar">
        <div class="brand"><span class="brand-mark">P</span><span>Pantheon</span></div>
        <div class="button-row">
          <div class="user-pill"><span class="avatar">${escapeHtml((state.user?.name || "U").slice(0, 1))}</span><span>${escapeHtml(state.user?.name)} · ${escapeHtml(state.user?.role)}</span></div>
          <button class="btn ghost small" data-action="refresh">Refresh</button>
          <button class="btn ghost small" data-action="logout">Logout</button>
        </div>
      </header>
      <section class="workspace">
        <aside class="sidebar">
          ${renderCreateLab()}
          ${renderLabs()}
        </aside>
        <section class="main-stack">
          ${state.error ? `<div class="alert">${escapeHtml(state.error)}</div>` : ""}
          ${state.message ? `<div class="success">${escapeHtml(state.message)}</div>` : ""}
          ${renderMetrics()}
          ${lab ? renderLabDetail(lab, simulation) : renderNoLab()}
          ${lab ? renderScenarios(lab) : ""}
          ${simulation ? renderSimulation(simulation) : ""}
          ${state.report ? renderReport(state.report) : ""}
        </section>
      </section>
    </main>
  `;
}

function renderCreateLab() {
  const options = state.templates
    .map((template) => `<option value="${escapeHtml(template.id)}">${escapeHtml(template.name)}</option>`)
    .join("");
  return `
    <section class="panel">
      <div class="panel-header">
        <div>
          <h2>Create Lab</h2>
          <p>Deploy a mock Kubernetes namespace and services.</p>
        </div>
      </div>
      <form id="create-lab-form">
        <div class="field">
          <label for="lab-name">Lab name</label>
          <input id="lab-name" name="lab_name" value="Small Company Demo" required />
        </div>
        <div class="field">
          <label for="template-id">Organization template</label>
          <select id="template-id" name="template_id">${options}</select>
        </div>
        <button class="btn primary" type="submit">Create lab</button>
      </form>
    </section>
  `;
}

function renderLabs() {
  const labs = state.labs
    .map(
      (lab) => `
        <article class="lab-item ${lab.id === state.selectedLabId ? "selected" : ""}">
          <div class="lab-title">
            <div>
              <h3>${escapeHtml(lab.labName)}</h3>
              <div class="muted tiny">${escapeHtml(lab.namespace)}</div>
            </div>
            ${statusBadge(lab.status)}
          </div>
          <div class="badge-row">
            <span class="badge blue">${escapeHtml(lab.template?.name || lab.templateId)}</span>
            <span class="badge">${lab.services.length} services</span>
            <span class="badge cyan">${lab.activeDefenses.length} defenses</span>
          </div>
          <div class="button-row" style="margin-top:10px">
            <button class="btn small" data-action="select-lab" data-lab-id="${escapeHtml(lab.id)}">Open</button>
            ${
              lab.status === "Running"
                ? `<button class="btn small ghost" data-action="stop-lab" data-lab-id="${escapeHtml(lab.id)}">Stop</button>`
                : `<button class="btn small ghost" data-action="start-lab" data-lab-id="${escapeHtml(lab.id)}">Start</button>`
            }
            <button class="btn small danger" data-action="delete-lab" data-lab-id="${escapeHtml(lab.id)}">Delete</button>
          </div>
        </article>
      `
    )
    .join("");
  return `
    <section class="panel">
      <div class="panel-header">
        <div>
          <h2>Labs</h2>
          <p>${state.labs.length} lab(s) in this workspace.</p>
        </div>
      </div>
      <div class="list">${labs || `<div class="empty">No labs yet. Create one to start the demo flow.</div>`}</div>
    </section>
  `;
}

function renderMetrics() {
  const running = state.labs.filter((lab) => lab.status === "Running").length;
  const defenses = state.labs.reduce((total, lab) => total + lab.activeDefenses.length, 0);
  const latest = state.labs.map((lab) => lab.latestSimulation).filter(Boolean);
  const critical = latest.filter((simulation) => simulation.riskLevel === "Critical").length;
  return `
    <section class="metric-grid">
      <div class="metric"><strong>${state.labs.length}</strong><span>Total labs</span></div>
      <div class="metric"><strong>${running}</strong><span>Running labs</span></div>
      <div class="metric"><strong>${latest.length}</strong><span>Simulations</span></div>
      <div class="metric"><strong>${defenses}</strong><span>Applied defenses</span></div>
    </section>
    ${critical ? `<div class="alert">${critical} latest simulation(s) still show critical risk.</div>` : ""}
  `;
}

function renderNoLab() {
  return `
    <section class="panel">
      <div class="empty">Select or create a lab to run a safe simulation.</div>
    </section>
  `;
}

function renderLabDetail(lab, simulation) {
  return `
    <section class="panel">
      <div class="panel-header">
        <div>
          <h2>${escapeHtml(lab.labName)}</h2>
          <p>${escapeHtml(lab.template?.description || "")}</p>
        </div>
        <div class="badge-row">
          ${statusBadge(lab.status)}
          <span class="badge blue">${escapeHtml(lab.deploymentMode)}</span>
        </div>
      </div>
      <div class="service-grid">
        ${lab.services
          .map(
            (service) => `
              <div class="service">
                <strong>${escapeHtml(service.serviceName)}</strong>
                <div class="muted tiny">${escapeHtml(service.serviceType)} · ${escapeHtml(service.status)}</div>
                <div class="badge-row">
                  ${service.exposed ? `<span class="badge amber">exposed</span>` : `<span class="badge green">private</span>`}
                  ${service.port ? `<span class="badge">:${service.port}</span>` : ""}
                </div>
              </div>
            `
          )
          .join("")}
      </div>
      ${
        simulation
          ? `<div class="badge-row" style="margin-top:12px">
              <span class="badge cyan">Latest: ${escapeHtml(simulation.scenarioName)}</span>
              ${riskBadge(simulation.riskLevel)}
              <span class="badge">${escapeHtml(simulation.status)}</span>
            </div>`
          : ""
      }
    </section>
  `;
}

function renderScenarios(lab) {
  const scenarios = compatibleScenarios(lab);
  return `
    <section class="panel">
      <div class="panel-header">
        <div>
          <h2>Attack Scenarios</h2>
          <p>Preset internal-only simulations for the selected template.</p>
        </div>
        <button class="btn primary" data-action="run-simulation" ${lab.status !== "Running" ? "disabled" : ""}>Run selected</button>
      </div>
      <div class="list">
        ${scenarios
          .map(
            (scenario) => `
              <article class="scenario-item ${scenario.id === state.selectedScenarioId ? "selected" : ""}" data-action="select-scenario" data-scenario-id="${escapeHtml(scenario.id)}">
                <div class="scenario-title">
                  <div>
                    <h3>${escapeHtml(scenario.name)}</h3>
                    <div class="muted tiny">${escapeHtml(scenario.attackType)} · ${escapeHtml(scenario.difficulty)}</div>
                  </div>
                  ${riskBadge(scenario.defaultRisk)}
                </div>
                <div class="badge-row">
                  ${scenario.targetServices.slice(0, 5).map((service) => `<span class="badge">${escapeHtml(service)}</span>`).join("")}
                </div>
              </article>
            `
          )
          .join("")}
      </div>
    </section>
  `;
}

function renderSimulation(simulation) {
  return `
    <section class="panel">
      <div class="panel-header">
        <div>
          <h2>Simulation Result</h2>
          <p>${escapeHtml(simulation.resultSummary)}</p>
        </div>
        <div class="button-row">
          ${riskBadge(simulation.riskLevel)}
          <button class="btn ghost" data-action="rerun-simulation" data-scenario-id="${escapeHtml(simulation.scenarioId)}">Rerun</button>
          <button class="btn primary" data-action="create-report" data-simulation-id="${escapeHtml(simulation.id)}">Generate report</button>
        </div>
      </div>
      <div class="two-col">
        <div>
          <h3>Attack Path</h3>
          ${renderGraph(simulation.attackPath)}
        </div>
        <div>
          <h3>AI Classification</h3>
          <div class="defense-item">
            <div class="badge-row">
              <span class="badge red">${escapeHtml(simulation.aiAnalysis.classification)}</span>
              ${riskBadge(simulation.aiAnalysis.riskLevel)}
              <span class="badge cyan">${Math.round(simulation.aiAnalysis.confidenceScore * 100)}% confidence</span>
            </div>
            <p class="muted">${escapeHtml(simulation.aiAnalysis.explanation)}</p>
          </div>
          ${renderComparison(simulation)}
        </div>
      </div>
      ${renderRecommendations(simulation)}
      ${renderLogs(simulation.logs)}
    </section>
  `;
}

function renderGraph(path) {
  if (!path?.nodes?.length) return `<div class="empty">No attack path data available.</div>`;
  const width = 820;
  const height = 300;
  const gap = width / Math.max(path.nodes.length, 1);
  const positions = new Map();
  path.nodes.forEach((node, index) => {
    const x = Math.round(gap / 2 + index * gap);
    const y = index % 2 === 0 ? 118 : 188;
    positions.set(node.id, { x, y });
  });
  const edges = path.edges
    .map((edge) => {
      const from = positions.get(edge.from);
      const to = positions.get(edge.to);
      if (!from || !to) return "";
      return `<path class="edge ${edge.blocked ? "blocked" : ""}" d="M ${from.x} ${from.y} C ${from.x + 65} ${from.y}, ${to.x - 65} ${to.y}, ${to.x} ${to.y}" marker-end="url(#arrow)" />`;
    })
    .join("");
  const nodes = path.nodes
    .map((node) => {
      const pos = positions.get(node.id);
      return `
        <g class="node state-${escapeHtml(node.state)}" transform="translate(${pos.x} ${pos.y})">
          <circle r="24"></circle>
          <text y="48">${escapeHtml(node.label.length > 17 ? `${node.label.slice(0, 16)}.` : node.label)}</text>
          <text class="sub" y="64">${escapeHtml(node.state)}</text>
        </g>
      `;
    })
    .join("");
  return `
    <div class="graph-wrap">
      <svg class="attack-graph" viewBox="0 0 ${width} ${height}" role="img" aria-label="Attack path graph">
        <defs>
          <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="#8ea3bd"></path>
          </marker>
        </defs>
        ${edges}
        ${nodes}
      </svg>
    </div>
  `;
}

function renderRecommendations(simulation) {
  const items = simulation.recommendations
    .map(
      (rec) => `
        <article class="defense-item">
          <div class="lab-title">
            <div>
              <h3>${escapeHtml(rec.title)}</h3>
              <div class="muted tiny">${escapeHtml(rec.defenseLevel)} · ${escapeHtml(rec.recommendationType)}</div>
            </div>
            <span class="badge ${rec.priority === "Critical" ? "red" : rec.priority === "High" ? "amber" : "blue"}">${escapeHtml(rec.priority)}</span>
          </div>
          <p class="muted">${escapeHtml(rec.description)}</p>
          <div class="button-row">
            <button class="btn small primary" data-action="apply-defense" data-defense-id="${escapeHtml(rec.catalogId)}" data-simulation-id="${escapeHtml(simulation.id)}" ${!rec.isApplicable ? "disabled" : ""}>
              ${rec.alreadyApplied ? "Applied" : "Apply defense"}
            </button>
          </div>
        </article>
      `
    )
    .join("");
  return `
    <section style="margin-top:16px">
      <div class="panel-header">
        <div>
          <h3>Defense Recommendations</h3>
          <p>Apply one or more controls, then rerun the same scenario.</p>
        </div>
      </div>
      <div class="list">${items}</div>
    </section>
  `;
}

function renderComparison(simulation) {
  if (!simulation.comparison) {
    return `<div class="empty" style="margin-top:12px">Apply a defense and rerun the same scenario to see before/after comparison.</div>`;
  }
  const comparison = simulation.comparison;
  return `
    <div class="defense-item" style="margin-top:12px">
      <h3>Before / After</h3>
      <div class="badge-row">
        <span class="badge green">${comparison.improvement.attackDepthReducedPercent}% depth reduction</span>
        <span class="badge cyan">${comparison.improvement.suspiciousEventsReducedBy} fewer suspicious events</span>
      </div>
      <p class="muted">Before: ${escapeHtml(comparison.before.reachedServices.join(" -> "))} (${escapeHtml(comparison.before.riskLevel)}).</p>
      <p class="muted">After: ${escapeHtml(comparison.after.reachedServices.join(" -> "))} (${escapeHtml(comparison.after.riskLevel)}).</p>
    </div>
  `;
}

function renderLogs(logs) {
  const rows = logs
    .slice(-12)
    .reverse()
    .map(
      (log) => `
        <tr>
          <td>${escapeHtml(new Date(log.timestamp).toLocaleTimeString())}</td>
          <td>${escapeHtml(log.sourceService)} -> ${escapeHtml(log.targetService)}</td>
          <td>${escapeHtml(log.method)} ${escapeHtml(log.endpoint)}</td>
          <td>${escapeHtml(log.eventType)}</td>
          <td>${escapeHtml(log.statusCode)}</td>
          <td>${log.isAttackSimulation ? `<span class="badge amber">attack</span>` : `<span class="badge green">normal</span>`}</td>
        </tr>
      `
    )
    .join("");
  return `
    <section style="margin-top:16px">
      <div class="panel-header">
        <div>
          <h3>Recent Logs</h3>
          <p>${logs.length} normalized event(s) generated for this simulation.</p>
        </div>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Time</th>
              <th>Flow</th>
              <th>Request</th>
              <th>Event</th>
              <th>Status</th>
              <th>Label</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    </section>
  `;
}

function renderReport(report) {
  const body = report.reportJson;
  return `
    <section class="panel">
      <div class="panel-header">
        <div>
          <h2>${escapeHtml(report.title)}</h2>
          <p>${escapeHtml(report.summary)}</p>
        </div>
        <span class="badge cyan">${escapeHtml(new Date(report.createdAt).toLocaleString())}</span>
      </div>
      <div class="report-section">
        <h4>Lab Information</h4>
        <p>${escapeHtml(body.labInformation.labName)} · ${escapeHtml(body.labInformation.namespace)} · ${escapeHtml(body.organizationTemplate)}</p>
      </div>
      <div class="report-section">
        <h4>Attack Scenario</h4>
        <p>${escapeHtml(body.attackScenario.name)} · ${escapeHtml(body.attackScenario.attackType)} · ${escapeHtml(body.attackScenario.difficulty)}</p>
      </div>
      <div class="report-section">
        <h4>AI Classification</h4>
        <p>${escapeHtml(body.aiClassification.classification)} with ${Math.round(body.aiClassification.confidenceScore * 100)}% confidence. ${escapeHtml(body.aiClassification.explanation)}</p>
      </div>
      <div class="report-section">
        <h4>Conclusion</h4>
        <p>${escapeHtml(body.conclusion)}</p>
      </div>
    </section>
  `;
}

function render() {
  if (state.loading) {
    app.innerHTML = `<div class="loading">Loading Pantheon...</div>`;
    return;
  }
  if (!state.user) {
    renderAuth();
    return;
  }
  renderDashboard();
}

async function login(email, password) {
  const result = await api("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password })
  });
  state.token = result.token;
  state.user = result.user;
  localStorage.setItem("pantheon_token", state.token);
  await loadDashboard();
  state.message = "Logged in.";
  state.error = "";
  render();
}

async function register(form) {
  const result = await api("/api/auth/register", {
    method: "POST",
    body: JSON.stringify({
      name: form.get("name"),
      email: form.get("email"),
      password: form.get("password"),
      role: form.get("role")
    })
  });
  state.token = result.token;
  state.user = result.user;
  localStorage.setItem("pantheon_token", state.token);
  await loadDashboard();
  state.message = "Account created.";
  state.error = "";
  render();
}

app.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  try {
    state.error = "";
    if (event.target.id === "auth-form") {
      if (state.authMode === "register") {
        await register(form);
      } else {
        await login(form.get("email"), form.get("password"));
      }
    }
    if (event.target.id === "create-lab-form") {
      const result = await api("/api/labs", {
        method: "POST",
        body: JSON.stringify({
          lab_name: form.get("lab_name"),
          template_id: form.get("template_id")
        })
      });
      await loadDashboard();
      state.selectedLabId = result.lab.id;
      localStorage.setItem("pantheon_selected_lab", state.selectedLabId);
      state.message = "Lab created and marked running in mock Kubernetes mode.";
      state.report = null;
      state.simulation = null;
      render();
    }
  } catch (error) {
    setMessage(error.message, true);
  }
});

app.addEventListener("click", async (event) => {
  const target = event.target.closest("[data-action]");
  if (!target) return;
  const action = target.dataset.action;

  try {
    state.error = "";
    if (action === "auth-mode") {
      state.authMode = target.dataset.mode;
      render();
    }
    if (action === "demo-login") {
      await login("demo@pantheon.local", "pantheon123");
    }
    if (action === "logout") {
      localStorage.removeItem("pantheon_token");
      state.token = "";
      state.user = null;
      state.labs = [];
      state.simulation = null;
      state.report = null;
      render();
    }
    if (action === "refresh") {
      await loadDashboard();
      state.message = "Dashboard refreshed.";
      render();
    }
    if (action === "select-lab") {
      state.selectedLabId = target.dataset.labId;
      localStorage.setItem("pantheon_selected_lab", state.selectedLabId);
      state.simulation = null;
      state.report = null;
      render();
    }
    if (action === "start-lab" || action === "stop-lab") {
      const verb = action === "start-lab" ? "start" : "stop";
      await api(`/api/labs/${target.dataset.labId}/${verb}`, { method: "POST", body: "{}" });
      await loadDashboard();
      state.message = `Lab ${verb === "start" ? "started" : "stopped"}.`;
      render();
    }
    if (action === "delete-lab") {
      await api(`/api/labs/${target.dataset.labId}`, { method: "DELETE" });
      await loadDashboard();
      state.message = "Lab deleted.";
      state.simulation = null;
      state.report = null;
      render();
    }
    if (action === "select-scenario") {
      state.selectedScenarioId = target.dataset.scenarioId;
      render();
    }
    if (action === "run-simulation") {
      const lab = selectedLab();
      if (!lab) return;
      const result = await api(`/api/labs/${lab.id}/simulations`, {
        method: "POST",
        body: JSON.stringify({ scenario_id: state.selectedScenarioId })
      });
      await loadDashboard();
      state.simulation = result.simulation;
      state.report = null;
      state.message = "Simulation completed with normalized logs and AI classification.";
      render();
    }
    if (action === "rerun-simulation") {
      const lab = selectedLab();
      if (!lab) return;
      const scenarioId = target.dataset.scenarioId || state.selectedScenarioId;
      const result = await api(`/api/labs/${lab.id}/simulations`, {
        method: "POST",
        body: JSON.stringify({ scenario_id: scenarioId })
      });
      await loadDashboard();
      state.simulation = result.simulation;
      state.report = null;
      state.message = "Scenario rerun completed.";
      render();
    }
    if (action === "apply-defense") {
      const lab = selectedLab();
      if (!lab) return;
      await api(`/api/labs/${lab.id}/defenses/apply`, {
        method: "POST",
        body: JSON.stringify({
          defense_ids: [target.dataset.defenseId],
          simulation_id: target.dataset.simulationId
        })
      });
      await loadDashboard();
      state.message = "Defense applied. Rerun the scenario to measure improvement.";
      render();
    }
    if (action === "create-report") {
      const result = await api(`/api/simulations/${target.dataset.simulationId}/report`, {
        method: "POST",
        body: "{}"
      });
      state.report = result.report;
      state.message = "Report generated.";
      render();
    }
  } catch (error) {
    setMessage(error.message, true);
  }
});

boot();
