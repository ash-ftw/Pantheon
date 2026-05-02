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
  kubernetesStatus: null,
  kubernetesPolling: false,
  simulationEvents: [],
  simulationStreaming: false,
  loading: true,
  message: "",
  error: ""
};

const app = document.querySelector("#app");
let kubernetesPollTimer = null;

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
    throw new Error(data.detail || data.error || `Request failed with status ${response.status}`);
  }
  return data;
}

function setMessage(message, isError = false) {
  state.message = isError ? "" : message;
  state.error = isError ? message : "";
  render();
}

function stopKubernetesPolling() {
  if (kubernetesPollTimer) {
    clearInterval(kubernetesPollTimer);
    kubernetesPollTimer = null;
  }
  state.kubernetesPolling = false;
}

async function pollKubernetesStatus(labId, silent = false) {
  const result = await api(`/api/labs/${labId}/kubernetes-status`);
  state.kubernetesStatus = result.kubernetesStatus;
  state.labs = state.labs.map((lab) => (lab.id === result.lab.id ? result.lab : lab));
  if (!silent) state.message = "Kubernetes status refreshed.";
  state.error = "";
  render();
}

function startKubernetesPolling(labId) {
  stopKubernetesPolling();
  state.kubernetesPolling = true;
  pollKubernetesStatus(labId, false).catch((error) => setMessage(error.message, true));
  kubernetesPollTimer = setInterval(() => {
    pollKubernetesStatus(labId, true).catch((error) => {
      stopKubernetesPolling();
      setMessage(error.message, true);
    });
  }, 5000);
  render();
}

function simulationStreamUrl(labId, scenarioId) {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const params = new URLSearchParams({ token: state.token, scenario_id: scenarioId });
  return `${protocol}//${window.location.host}/api/labs/${encodeURIComponent(labId)}/simulations/stream?${params}`;
}

function canUseSimulationWebSocket() {
  return Boolean(window.WebSocket && state.token && window.location.port !== "8090");
}

async function runSimulationWithProgress(lab, scenarioId) {
  state.simulationEvents = [];
  state.simulationStreaming = true;
  state.message = "Simulation stream started.";
  state.error = "";
  state.report = null;
  render();

  if (!canUseSimulationWebSocket()) {
    return runSimulationRest(lab, scenarioId, "Simulation completed with normalized logs and AI classification.");
  }

  return new Promise((resolve, reject) => {
    const socket = new WebSocket(simulationStreamUrl(lab.id, scenarioId));
    let completed = false;
    let fallbackStarted = false;
    socket.onmessage = async (event) => {
      const payload = JSON.parse(event.data);
      if (payload.type === "simulation_completed") {
        completed = true;
        await loadDashboard();
        state.simulation = payload.simulation;
        state.simulationStreaming = false;
        state.message = "Simulation completed through WebSocket progress stream.";
        render();
        resolve(payload.simulation);
        return;
      }
      if (payload.type === "simulation_error") {
        completed = true;
        state.simulationStreaming = false;
        render();
        reject(new Error(payload.detail || "Simulation stream failed"));
        return;
      }
      state.simulationEvents = [...state.simulationEvents.slice(-23), payload];
      render();
    };
    socket.onerror = () => {
      if (!completed && !fallbackStarted) {
        fallbackStarted = true;
        socket.close();
        runSimulationRest(lab, scenarioId, "Simulation completed through REST fallback.")
          .then(resolve)
          .catch(reject);
      }
    };
    socket.onclose = () => {
      if (!completed && !fallbackStarted && state.simulationStreaming) {
        state.simulationStreaming = false;
        render();
      }
    };
  });
}

async function runSimulationRest(lab, scenarioId, message) {
  const result = await api(`/api/labs/${lab.id}/simulations`, {
    method: "POST",
    body: JSON.stringify({ scenario_id: scenarioId })
  });
  await loadDashboard();
  state.simulation = result.simulation;
  state.simulationStreaming = false;
  state.report = null;
  state.message = message;
  render();
  return result.simulation;
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
  const lab = selectedLab();
  const scenarios = compatibleScenarios(lab);
  if (scenarios.length && !scenarios.some((scenario) => scenario.id === state.selectedScenarioId)) {
    state.selectedScenarioId = scenarios[0].id;
  }
}

function selectedLab() {
  return state.labs.find((lab) => lab.id === state.selectedLabId) || null;
}

function compatibleScenarios(lab) {
  if (!lab) return [];
  return state.scenarios.filter((scenario) => {
    if (scenario.targetLabId) return scenario.targetLabId === lab.id;
    return scenario.allowedTemplateIds.includes(lab.templateId);
  });
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
          ${lab ? renderKubernetesStatus(lab) : ""}
          ${lab ? renderTargetApps(lab) : ""}
          ${lab ? renderScenarios(lab) : ""}
          ${renderSimulationProgress()}
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
  const targetApps = state.labs.reduce((total, lab) => total + (lab.targetApplications?.length || 0), 0);
  const critical = latest.filter((simulation) => simulation.riskLevel === "Critical").length;
  return `
    <section class="metric-grid">
      <div class="metric"><strong>${state.labs.length}</strong><span>Total labs</span></div>
      <div class="metric"><strong>${running}</strong><span>Running labs</span></div>
      <div class="metric"><strong>${targetApps}</strong><span>Imported apps</span></div>
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
          <span class="badge green">namespace isolated</span>
        </div>
      </div>
      ${renderSafetyStrip(lab)}
      <div class="service-grid">
        ${lab.services
          .map(
            (service) => `
              <div class="service ${service.serviceType === "target-app" ? "target-service" : ""}">
                <strong>${escapeHtml(service.serviceName)}</strong>
                <div class="muted tiny">${escapeHtml(service.serviceType)} - ${escapeHtml(service.status)}</div>
                <div class="badge-row">
                  ${service.serviceType === "target-app" ? `<span class="badge cyan">imported app</span>` : ""}
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

function renderSafetyStrip(lab) {
  return `
    <div class="indicator-track">
      <div class="indicator good"><span class="dot"></span><strong>Contained</strong><small>${escapeHtml(lab.namespace)}</small></div>
      <div class="indicator good"><span class="dot"></span><strong>Internal-only</strong><small>No external URLs accepted</small></div>
      <div class="indicator info"><span class="dot"></span><strong>${lab.services.length}</strong><small>lab services</small></div>
      <div class="indicator info"><span class="dot"></span><strong>${lab.targetApplications?.length || 0}</strong><small>imported apps</small></div>
    </div>
  `;
}

function renderKubernetesStatus(lab) {
  const status = state.kubernetesStatus?.labId === lab.id ? state.kubernetesStatus : null;
  const summary = status?.summary;
  const services = status?.services || [];
  const jobs = status?.jobs || [];
  return `
    <section class="panel">
      <div class="panel-header">
        <div>
          <h2>Live Kubernetes Status</h2>
          <p>${status ? `Last observed ${escapeHtml(new Date(status.observedAt).toLocaleTimeString())}` : "Poll the lab namespace for live service and job readiness."}</p>
        </div>
        <div class="button-row">
          <button class="btn ghost" data-action="poll-kubernetes" data-lab-id="${escapeHtml(lab.id)}">Refresh status</button>
          <button class="btn ${state.kubernetesPolling ? "danger" : "primary"}" data-action="toggle-kubernetes-poll" data-lab-id="${escapeHtml(lab.id)}">
            ${state.kubernetesPolling ? "Stop live poll" : "Start live poll"}
          </button>
        </div>
      </div>
      ${
        status
          ? `<div class="indicator-track k8s-track">
              <div class="indicator ${summary.allReady ? "good" : "info"}"><span class="dot"></span><strong>${summary.readyServices}/${summary.totalServices}</strong><small>ready services</small></div>
              <div class="indicator info"><span class="dot"></span><strong>${summary.pendingServices}</strong><small>pending services</small></div>
              <div class="indicator ${summary.failedServices ? "bad" : "good"}"><span class="dot"></span><strong>${summary.failedServices}</strong><small>failed services</small></div>
              <div class="indicator info"><span class="dot"></span><strong>${jobs.length}</strong><small>runner jobs</small></div>
            </div>
            <div class="table-wrap compact-table">
              <table>
                <thead><tr><th>Service</th><th>Status</th><th>Ready</th><th>Pods</th></tr></thead>
                <tbody>
                  ${services
                    .map(
                      (service) => `
                        <tr>
                          <td>${escapeHtml(service.name)}<div class="muted tiny">${escapeHtml(service.type)}</div></td>
                          <td>${statusBadge(service.status)}</td>
                          <td>${escapeHtml(service.readyReplicas ?? 0)} / ${escapeHtml(service.replicas ?? 0)}</td>
                          <td>${(service.pods || []).map((pod) => `<span class="badge ${pod.phase === "Running" ? "green" : "amber"}">${escapeHtml(pod.name)} ${escapeHtml(pod.phase)}</span>`).join(" ") || `<span class="badge amber">no pods</span>`}</td>
                        </tr>
                      `
                    )
                    .join("")}
                </tbody>
              </table>
            </div>
            ${jobs.length ? `<div class="badge-row k8s-jobs">${jobs.map((job) => `<span class="badge cyan">${escapeHtml(job.name)} ${escapeHtml(job.phase)}</span>`).join("")}</div>` : ""}`
          : `<div class="empty">No Kubernetes status has been polled for this lab yet.</div>`
      }
    </section>
  `;
}

function renderTargetApps(lab) {
  const serviceOptions = lab.services
    .map((service) => `<option value="${escapeHtml(service.serviceName)}">${escapeHtml(service.serviceName)} (${escapeHtml(service.serviceType)})</option>`)
    .join("");
  const targetCards = (lab.targetApplications || [])
    .map(
      (target) => `
        <article class="target-card">
          <div class="lab-title">
            <div>
              <h3>${escapeHtml(target.appName)}</h3>
              <div class="muted tiny">${escapeHtml(target.internalUrl)}${escapeHtml(target.healthPath)}</div>
            </div>
            ${statusBadge(target.status)}
          </div>
          <div class="badge-row">
            <span class="badge cyan">${escapeHtml(target.importType)}</span>
            <span class="badge green">${escapeHtml(target.safetyState)}</span>
            <span class="badge green">internal target</span>
            ${target.image ? `<span class="badge">${escapeHtml(target.image)}</span>` : ""}
          </div>
        </article>
      `
    )
    .join("");
  return `
    <section class="panel">
      <div class="panel-header">
        <div>
          <h2>Web App Targets</h2>
          <p>Import your app into this lab, then create custom internal-only scenarios against its service name.</p>
        </div>
        <span class="badge green">safe target registry</span>
      </div>
      <div class="two-col target-layout">
        <form id="target-app-form" class="subpanel">
          <h3>Add Web App</h3>
          <div class="form-grid">
            <div class="field">
              <label for="target-app-name">App name</label>
              <input id="target-app-name" name="app_name" value="My Web App" required />
            </div>
            <div class="field">
              <label for="target-service-name">Internal service name</label>
              <input id="target-service-name" name="service_name" value="my-web-app" required />
            </div>
            <div class="field">
              <label for="target-import-type">Import type</label>
              <select id="target-import-type" name="import_type">
                <option value="docker-image">Docker image</option>
                <option value="kubernetes-yaml">Kubernetes YAML</option>
                <option value="local-service">Local service config</option>
              </select>
            </div>
            <div class="field">
              <label for="target-port">Port</label>
              <input id="target-port" name="port" type="number" min="1" max="65535" value="8080" required />
            </div>
            <div class="field span-2">
              <label for="target-image">Image</label>
              <input id="target-image" name="image" placeholder="my-web-app:latest" />
            </div>
            <div class="field span-2">
              <label for="target-health-path">Health path</label>
              <input id="target-health-path" name="health_path" value="/" />
            </div>
            <div class="field span-2">
              <label for="target-manifest">Kubernetes YAML / local notes</label>
              <textarea id="target-manifest" name="manifest" rows="4" placeholder="Optional constrained Deployment + Service YAML"></textarea>
            </div>
          </div>
          <button class="btn primary" type="submit" ${lab.status === "Deleted" ? "disabled" : ""}>Import app</button>
        </form>
        <div class="subpanel">
          <div class="panel-header compact">
            <div>
              <h3>Registered Targets</h3>
              <p>${lab.targetApplications?.length || 0} imported app(s) in this namespace.</p>
            </div>
          </div>
          <div class="list">${targetCards || `<div class="empty">No imported web apps yet. Add one with a Docker image or constrained YAML.</div>`}</div>
        </div>
      </div>
      <form id="custom-scenario-form" class="subpanel custom-scenario-panel">
        <div class="panel-header compact">
          <div>
            <h3>Custom Scenario Builder</h3>
            <p>Targets are limited to services already inside this lab.</p>
          </div>
          <span class="badge green">scope locked</span>
        </div>
        <div class="form-grid wide">
          <div class="field">
            <label for="custom-name">Scenario name</label>
            <input id="custom-name" name="name" value="Custom App Probe" required />
          </div>
          <div class="field">
            <label for="custom-target">Target service</label>
            <select id="custom-target" name="target_service">${serviceOptions}</select>
          </div>
          <div class="field">
            <label for="custom-attack-type">Attack type</label>
            <select id="custom-attack-type" name="attack_type">
              <option>Custom Web App Probe</option>
              <option>SQL Injection</option>
              <option>Brute Force</option>
              <option>DDoS-Style Traffic</option>
              <option>Privilege Escalation</option>
            </select>
          </div>
          <div class="field">
            <label for="custom-method">Method</label>
            <select id="custom-method" name="method">
              <option>GET</option>
              <option>POST</option>
              <option>PUT</option>
              <option>PATCH</option>
              <option>DELETE</option>
            </select>
          </div>
          <div class="field">
            <label for="custom-endpoint">Endpoint path</label>
            <input id="custom-endpoint" name="endpoint" value="/login" required />
          </div>
          <div class="field">
            <label for="custom-payload">Payload category</label>
            <select id="custom-payload" name="payload_category">
              <option value="custom_probe">custom_probe</option>
              <option value="sql_meta_characters">sql_meta_characters</option>
              <option value="credential_attempt">credential_attempt</option>
              <option value="controlled_high_volume">controlled_high_volume</option>
              <option value="low_privilege_token">low_privilege_token</option>
            </select>
          </div>
          <div class="field">
            <label for="custom-count">Request count</label>
            <input id="custom-count" name="request_count" type="number" min="1" max="100" value="12" required />
          </div>
          <div class="field">
            <label for="custom-risk">Risk</label>
            <select id="custom-risk" name="risk_level">
              <option>Medium</option>
              <option>High</option>
              <option>Critical</option>
              <option>Low</option>
            </select>
          </div>
        </div>
        <button class="btn primary" type="submit" ${!lab.services.length ? "disabled" : ""}>Create custom scenario</button>
      </form>
    </section>
  `;
}


function renderScenarios(lab) {
  const scenarios = compatibleScenarios(lab);
  const selected = scenarios.some((scenario) => scenario.id === state.selectedScenarioId)
    ? state.selectedScenarioId
    : scenarios[0]?.id;
  if (selected && selected !== state.selectedScenarioId) state.selectedScenarioId = selected;
  return `
    <section class="panel">
      <div class="panel-header">
        <div>
          <h2>Attack Scenarios</h2>
          <p>Preset and custom internal-only simulations for the selected lab.</p>
        </div>
        <button class="btn primary" data-action="run-simulation" ${lab.status !== "Running" || !selected ? "disabled" : ""}>Run selected</button>
      </div>
      <div class="list">
        ${scenarios
          .map(
            (scenario) => `
              <article class="scenario-item ${scenario.id === state.selectedScenarioId ? "selected" : ""}" data-action="select-scenario" data-scenario-id="${escapeHtml(scenario.id)}">
                <div class="scenario-title">
                  <div>
                    <h3>${escapeHtml(scenario.name)}</h3>
                    <div class="muted tiny">${escapeHtml(scenario.attackType)} - ${escapeHtml(scenario.difficulty)}</div>
                  </div>
                  ${riskBadge(scenario.defaultRisk)}
                </div>
                <div class="badge-row">
                  <span class="badge ${scenario.isCustom ? "cyan" : "blue"}">${scenario.isCustom ? "custom" : "preset"}</span>
                  <span class="badge green">internal-only</span>
                  ${scenario.targetServices.slice(0, 5).map((service) => `<span class="badge">${escapeHtml(service)}</span>`).join("")}
                </div>
              </article>
            `
          )
          .join("") || `<div class="empty">No compatible scenarios yet. Create a custom scenario for this lab.</div>`}
      </div>
    </section>
  `;
}


function renderSimulationProgress() {
  if (!state.simulationStreaming && !state.simulationEvents.length) return "";
  const events = state.simulationEvents.slice(-8).reverse();
  return `
    <section class="panel progress-panel">
      <div class="panel-header">
        <div>
          <h2>Live Simulation Progress</h2>
          <p>${state.simulationStreaming ? "Streaming backend progress over WebSocket." : "Last streamed simulation events."}</p>
        </div>
        <span class="badge ${state.simulationStreaming ? "green" : "blue"}">${state.simulationStreaming ? "streaming" : "complete"}</span>
      </div>
      <div class="progress-list">
        ${events
          .map(
            (event) => `
              <div class="progress-event">
                <span class="progress-dot"></span>
                <div>
                  <strong>${escapeHtml(progressLabel(event.type))}</strong>
                  <p>${escapeHtml(progressDetail(event))}</p>
                </div>
                <small>${event.timestamp ? escapeHtml(new Date(event.timestamp).toLocaleTimeString()) : ""}</small>
              </div>
            `
          )
          .join("") || `<div class="empty">Waiting for stream events.</div>`}
      </div>
    </section>
  `;
}

function progressLabel(type) {
  return String(type || "progress").replaceAll("_", " ");
}

function progressDetail(event) {
  if (event.target) return `${event.source || event.jobName || "runner"} -> ${event.target} ${event.endpoint || ""}`.trim();
  if (event.jobName && event.phase) return `${event.jobName} is ${event.phase}`;
  if (event.serviceName) return `${event.serviceName}: ${event.eventCount || 0} container log event(s)`;
  if (event.eventCount !== undefined) return `${event.eventCount} event(s)`;
  if (event.riskLevel) return `risk ${event.riskLevel}`;
  return event.scenarioName || event.scenarioId || event.simulationId || "";
}

function renderSimulation(simulation) {
  const observedLogs = (simulation.logs || []).filter((log) => {
    const raw = log.rawLogJson || {};
    return raw.observed_source || raw.observedSource;
  });
  return `
    <section class="panel">
      <div class="panel-header">
        <div>
          <h2>Simulation Result</h2>
          <p>${escapeHtml(simulation.resultSummary)}</p>
        </div>
        <div class="button-row">
          ${riskBadge(simulation.riskLevel)}
          <span class="badge ${observedLogs.length ? "green" : "blue"}">${observedLogs.length} observed k8s logs</span>
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
    .map((log) => {
      const raw = log.rawLogJson || {};
      const observedSource = raw.observed_source || raw.observedSource || "generated";
      const latency = raw.latency_ms ?? raw.latencyMs;
      const routeFamily = raw.route_family || raw.routeFamily || "";
      return `
        <tr>
          <td>${escapeHtml(new Date(log.timestamp).toLocaleTimeString())}</td>
          <td>${escapeHtml(log.sourceService)} -> ${escapeHtml(log.targetService)}</td>
          <td>${escapeHtml(log.method)} ${escapeHtml(log.endpoint)}</td>
          <td>${escapeHtml(log.eventType)}</td>
          <td>${escapeHtml(log.statusCode)}</td>
          <td>${log.isAttackSimulation ? `<span class="badge amber">attack</span>` : `<span class="badge green">normal</span>`}</td>
          <td><span class="badge ${observedSource.includes("service") ? "cyan" : observedSource === "generated" ? "blue" : "green"}">${escapeHtml(observedSource)}</span></td>
          <td>${routeFamily ? `<span class="badge">${escapeHtml(routeFamily)}</span>` : ""}${latency !== undefined ? `<span class="badge cyan">${escapeHtml(latency)} ms</span>` : ""}</td>
        </tr>
      `;
    })
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
              <th>Observed From</th>
              <th>Access Detail</th>
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
    if (event.target.id === "target-app-form") {
      const lab = selectedLab();
      if (!lab) return;
      await api(`/api/labs/${lab.id}/target-apps`, {
        method: "POST",
        body: JSON.stringify({
          app_name: form.get("app_name"),
          service_name: form.get("service_name"),
          import_type: form.get("import_type"),
          image: form.get("image"),
          port: Number(form.get("port") || 8080),
          health_path: form.get("health_path"),
          manifest: form.get("manifest"),
          normal_paths: [`GET ${form.get("health_path") || "/"}`]
        })
      });
      await loadDashboard();
      state.message = "Web app target imported and locked to this lab namespace.";
      state.report = null;
      render();
    }
    if (event.target.id === "custom-scenario-form") {
      const lab = selectedLab();
      if (!lab) return;
      const result = await api(`/api/labs/${lab.id}/custom-scenarios`, {
        method: "POST",
        body: JSON.stringify({
          name: form.get("name"),
          attack_type: form.get("attack_type"),
          target_service: form.get("target_service"),
          method: form.get("method"),
          endpoint: form.get("endpoint"),
          payload_category: form.get("payload_category"),
          request_count: Number(form.get("request_count") || 12),
          risk_level: form.get("risk_level")
        })
      });
      state.selectedScenarioId = result.scenario.id;
      await loadDashboard();
      state.message = "Custom scenario created. It can only target services inside this lab.";
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
      stopKubernetesPolling();
      state.simulation = null;
      state.report = null;
      state.kubernetesStatus = null;
      state.simulationEvents = [];
      state.simulationStreaming = false;
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
      stopKubernetesPolling();
      state.simulation = null;
      state.report = null;
      state.kubernetesStatus = null;
      state.simulationEvents = [];
      state.simulationStreaming = false;
      render();
    }
    if (action === "start-lab" || action === "stop-lab") {
      const verb = action === "start-lab" ? "start" : "stop";
      await api(`/api/labs/${target.dataset.labId}/${verb}`, { method: "POST", body: "{}" });
      await loadDashboard();
      state.kubernetesStatus = null;
      state.message = `Lab ${verb === "start" ? "started" : "stopped"}.`;
      render();
    }
    if (action === "delete-lab") {
      await api(`/api/labs/${target.dataset.labId}`, { method: "DELETE" });
      await loadDashboard();
      stopKubernetesPolling();
      state.kubernetesStatus = null;
      state.message = "Lab deleted.";
      state.simulation = null;
      state.report = null;
      state.simulationEvents = [];
      state.simulationStreaming = false;
      render();
    }
    if (action === "select-scenario") {
      state.selectedScenarioId = target.dataset.scenarioId;
      render();
    }
    if (action === "poll-kubernetes") {
      await pollKubernetesStatus(target.dataset.labId);
    }
    if (action === "toggle-kubernetes-poll") {
      if (state.kubernetesPolling) {
        stopKubernetesPolling();
        state.message = "Kubernetes live polling stopped.";
        render();
      } else {
        startKubernetesPolling(target.dataset.labId);
      }
    }
    if (action === "run-simulation") {
      const lab = selectedLab();
      if (!lab) return;
      await runSimulationWithProgress(lab, state.selectedScenarioId);
    }
    if (action === "rerun-simulation") {
      const lab = selectedLab();
      if (!lab) return;
      const scenarioId = target.dataset.scenarioId || state.selectedScenarioId;
      await runSimulationWithProgress(lab, scenarioId);
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
