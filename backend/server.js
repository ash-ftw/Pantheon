const http = require("node:http");
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");

const ROOT = path.resolve(__dirname, "..");
const FRONTEND_DIR = path.join(ROOT, "frontend");
const DATA_DIR = path.join(__dirname, "data");
const STORE_PATH = path.join(DATA_DIR, "store.json");
const PORT = Number(process.env.PORT || 8090);

const tokens = new Map();

const templateCatalog = [
  {
    id: "small-company",
    name: "Small Company",
    description: "A compact enterprise network with frontend, auth, employee, admin, and database services.",
    services: [
      { name: "frontend-service", type: "frontend", port: 8080, exposed: true, vulnerabilities: [] },
      { name: "auth-service", type: "api", port: 8081, exposed: false, vulnerabilities: ["weak_login_rate_limit"] },
      { name: "employee-api", type: "api", port: 8082, exposed: false, vulnerabilities: ["demo_search_input"] },
      { name: "admin-api", type: "api", port: 8083, exposed: false, vulnerabilities: ["restricted_endpoint_demo"] },
      { name: "postgres-db", type: "database", port: 5432, exposed: false, vulnerabilities: [] },
      { name: "traffic-generator", type: "worker", port: null, exposed: false, vulnerabilities: [] }
    ],
    normalTraffic: ["GET /home", "POST /login", "GET /profile", "GET /employees", "GET /search?q=alice"]
  },
  {
    id: "e-commerce",
    name: "E-Commerce",
    description: "A storefront template with products, cart, payment, orders, cache, and database components.",
    services: [
      { name: "frontend-service", type: "frontend", port: 8080, exposed: true, vulnerabilities: [] },
      { name: "auth-service", type: "api", port: 8081, exposed: false, vulnerabilities: ["weak_login_rate_limit"] },
      { name: "product-service", type: "api", port: 8082, exposed: false, vulnerabilities: ["demo_search_input"] },
      { name: "cart-service", type: "api", port: 8083, exposed: false, vulnerabilities: [] },
      { name: "payment-service", type: "api", port: 8084, exposed: false, vulnerabilities: ["restricted_endpoint_demo"] },
      { name: "order-service", type: "api", port: 8085, exposed: false, vulnerabilities: [] },
      { name: "postgres-db", type: "database", port: 5432, exposed: false, vulnerabilities: [] },
      { name: "redis-cache", type: "cache", port: 6379, exposed: false, vulnerabilities: [] },
      { name: "traffic-generator", type: "worker", port: null, exposed: false, vulnerabilities: [] }
    ],
    normalTraffic: ["GET /home", "POST /login", "GET /products", "POST /cart/add", "GET /orders"]
  },
  {
    id: "university",
    name: "University",
    description: "A campus system with student portal, auth, marks, fees, admin, and database services.",
    services: [
      { name: "student-portal", type: "frontend", port: 8080, exposed: true, vulnerabilities: [] },
      { name: "auth-service", type: "api", port: 8081, exposed: false, vulnerabilities: ["weak_login_rate_limit"] },
      { name: "marks-api", type: "api", port: 8082, exposed: false, vulnerabilities: ["demo_search_input"] },
      { name: "fees-api", type: "api", port: 8083, exposed: false, vulnerabilities: [] },
      { name: "admin-api", type: "api", port: 8084, exposed: false, vulnerabilities: ["restricted_endpoint_demo"] },
      { name: "postgres-db", type: "database", port: 5432, exposed: false, vulnerabilities: [] },
      { name: "traffic-generator", type: "worker", port: null, exposed: false, vulnerabilities: [] }
    ],
    normalTraffic: ["GET /portal", "POST /login", "GET /marks", "GET /fees", "GET /profile"]
  }
];

const scenarioCatalog = [
  {
    id: "brute-force-login",
    name: "Brute Force Login Simulation",
    difficulty: "Beginner",
    attackType: "Brute Force",
    allowedTemplateIds: ["small-company", "e-commerce", "university"],
    targetServices: ["auth-service"],
    defaultRisk: "High",
    steps: [
      {
        order: 1,
        actionType: "HTTP_REQUEST_PATTERN",
        source: "attack-pod",
        target: "auth-service",
        method: "POST",
        endpoint: "/login",
        eventType: "failed_login",
        payloadCategory: "credential_attempt",
        statusCode: 401,
        count: 34
      }
    ]
  },
  {
    id: "sql-injection",
    name: "SQL Injection Simulation",
    difficulty: "Intermediate",
    attackType: "SQL Injection",
    allowedTemplateIds: ["small-company", "e-commerce", "university"],
    targetServices: ["employee-api", "product-service", "marks-api"],
    defaultRisk: "High",
    steps: [
      {
        order: 1,
        actionType: "HTTP_REQUEST_PATTERN",
        source: "attack-pod",
        target: "employee-api",
        method: "GET",
        endpoint: "/search",
        eventType: "suspicious_input_pattern",
        payloadCategory: "sql_meta_characters",
        statusCode: 200,
        count: 18
      }
    ]
  },
  {
    id: "privilege-escalation",
    name: "Privilege Escalation Attempt",
    difficulty: "Intermediate",
    attackType: "Privilege Escalation",
    allowedTemplateIds: ["small-company", "e-commerce", "university"],
    targetServices: ["admin-api", "payment-service"],
    defaultRisk: "High",
    steps: [
      {
        order: 1,
        actionType: "UNAUTHORIZED_ACCESS_ATTEMPT",
        source: "attack-pod",
        target: "admin-api",
        method: "GET",
        endpoint: "/admin/users",
        eventType: "restricted_endpoint_access",
        payloadCategory: "low_privilege_token",
        statusCode: 403,
        count: 12
      }
    ]
  },
  {
    id: "lateral-movement",
    name: "Lateral Movement Simulation",
    difficulty: "Advanced",
    attackType: "Lateral Movement",
    allowedTemplateIds: ["small-company", "university"],
    targetServices: ["frontend-service", "auth-service", "employee-api", "admin-api", "postgres-db"],
    defaultRisk: "Critical",
    steps: [
      {
        order: 1,
        actionType: "HTTP_REQUEST_PATTERN",
        source: "attack-pod",
        target: "frontend-service",
        method: "GET",
        endpoint: "/home",
        eventType: "initial_probe",
        payloadCategory: "service_probe",
        statusCode: 200,
        count: 8
      },
      {
        order: 2,
        actionType: "AUTHENTICATION_SEQUENCE",
        source: "frontend-service",
        target: "auth-service",
        method: "POST",
        endpoint: "/login",
        eventType: "credential_reuse_attempt",
        payloadCategory: "credential_attempt",
        statusCode: 401,
        count: 10
      },
      {
        order: 3,
        actionType: "INTERNAL_API_ACCESS",
        source: "auth-service",
        target: "employee-api",
        method: "GET",
        endpoint: "/employees",
        eventType: "internal_service_hop",
        payloadCategory: "service_discovery",
        statusCode: 200,
        count: 7
      },
      {
        order: 4,
        actionType: "UNAUTHORIZED_ACCESS_ATTEMPT",
        source: "employee-api",
        target: "admin-api",
        method: "GET",
        endpoint: "/admin/users",
        eventType: "restricted_endpoint_access",
        payloadCategory: "low_privilege_token",
        statusCode: 403,
        count: 6
      },
      {
        order: 5,
        actionType: "DATABASE_ACCESS_ATTEMPT",
        source: "admin-api",
        target: "postgres-db",
        method: "CONNECT",
        endpoint: "tcp/5432",
        eventType: "database_reachability_attempt",
        payloadCategory: "db_probe",
        statusCode: 0,
        count: 4
      }
    ]
  },
  {
    id: "multi-stage-chain",
    name: "SQL Injection to Lateral Movement",
    difficulty: "Advanced",
    attackType: "Multi-Stage Attack",
    allowedTemplateIds: ["small-company", "university"],
    targetServices: ["employee-api", "admin-api", "postgres-db"],
    defaultRisk: "Critical",
    steps: [
      {
        order: 1,
        actionType: "HTTP_REQUEST_PATTERN",
        source: "attack-pod",
        target: "employee-api",
        method: "GET",
        endpoint: "/search",
        eventType: "suspicious_input_pattern",
        payloadCategory: "sql_meta_characters",
        statusCode: 200,
        count: 16
      },
      {
        order: 2,
        actionType: "SIMULATED_CREDENTIAL_DISCOVERY",
        source: "employee-api",
        target: "admin-api",
        method: "SIMULATE",
        endpoint: "/artifact/fake-credential",
        eventType: "credential_artifact_generated",
        payloadCategory: "credential_artifact",
        statusCode: 200,
        count: 2
      },
      {
        order: 3,
        actionType: "UNAUTHORIZED_ACCESS_ATTEMPT",
        source: "attack-pod",
        target: "admin-api",
        method: "GET",
        endpoint: "/admin/users",
        eventType: "restricted_endpoint_access",
        payloadCategory: "low_privilege_token",
        statusCode: 403,
        count: 8
      },
      {
        order: 4,
        actionType: "DATABASE_ACCESS_ATTEMPT",
        source: "admin-api",
        target: "postgres-db",
        method: "CONNECT",
        endpoint: "tcp/5432",
        eventType: "database_reachability_attempt",
        payloadCategory: "db_probe",
        statusCode: 0,
        count: 4
      }
    ]
  },
  {
    id: "ddos-style",
    name: "DDoS-Style Traffic Simulation",
    difficulty: "Intermediate",
    attackType: "DDoS-Style Traffic",
    allowedTemplateIds: ["small-company", "e-commerce", "university"],
    targetServices: ["frontend-service", "auth-service", "student-portal"],
    defaultRisk: "High",
    steps: [
      {
        order: 1,
        actionType: "CONTROLLED_HIGH_VOLUME_REQUESTS",
        source: "attack-pod",
        target: "frontend-service",
        method: "GET",
        endpoint: "/home",
        eventType: "resource_exhaustion_pattern",
        payloadCategory: "controlled_high_volume",
        statusCode: 429,
        count: 72
      }
    ]
  }
];

const defenseCatalog = [
  {
    id: "rate-limit-login",
    name: "Rate limiting for login endpoints",
    recommendationType: "Rate Limiting",
    actionType: "RATE_LIMIT",
    attackTypes: ["Brute Force", "DDoS-Style Traffic"],
    description: "Throttle repeated authentication attempts and high-volume requests from the same simulated source.",
    defenseLevel: "Application",
    priority: "High"
  },
  {
    id: "input-validation",
    name: "Input validation toggle",
    recommendationType: "Input Validation",
    actionType: "INPUT_VALIDATION",
    attackTypes: ["SQL Injection", "Multi-Stage Attack"],
    description: "Reject suspicious search input patterns before they reach vulnerable demo handlers.",
    defenseLevel: "Application",
    priority: "High"
  },
  {
    id: "endpoint-restriction",
    name: "Admin endpoint access restriction",
    recommendationType: "Access Control",
    actionType: "ENDPOINT_RESTRICTION",
    attackTypes: ["Privilege Escalation", "Lateral Movement", "Multi-Stage Attack"],
    description: "Restrict sensitive admin routes to trusted services and expected roles only.",
    defenseLevel: "Application",
    priority: "High"
  },
  {
    id: "network-policy",
    name: "Kubernetes NetworkPolicy",
    recommendationType: "NetworkPolicy",
    actionType: "NETWORK_POLICY",
    attackTypes: ["Lateral Movement", "Multi-Stage Attack"],
    description: "Limit service-to-service communication so compromised demo components cannot freely reach admin or database services.",
    defenseLevel: "Kubernetes",
    priority: "Critical"
  },
  {
    id: "resource-limits",
    name: "Resource limit adjustment",
    recommendationType: "Resource Limits",
    actionType: "RESOURCE_LIMIT",
    attackTypes: ["DDoS-Style Traffic"],
    description: "Apply CPU and memory limits so noisy traffic simulations cannot exhaust the local cluster.",
    defenseLevel: "Kubernetes",
    priority: "Medium"
  }
];

function nowIso() {
  return new Date().toISOString();
}

function shortId(prefix) {
  return `${prefix}_${crypto.randomBytes(4).toString("hex")}`;
}

function hashPassword(password) {
  return crypto.createHash("sha256").update(String(password)).digest("hex");
}

function ensureStore() {
  if (!fs.existsSync(DATA_DIR)) fs.mkdirSync(DATA_DIR, { recursive: true });
  if (!fs.existsSync(STORE_PATH)) {
    const createdAt = nowIso();
    const seed = {
      users: [
        {
          id: "user_demo_student",
          name: "Student Analyst",
          email: "demo@pantheon.local",
          passwordHash: hashPassword("pantheon123"),
          role: "Student",
          createdAt,
          updatedAt: createdAt
        },
        {
          id: "user_demo_admin",
          name: "Platform Admin",
          email: "admin@pantheon.local",
          passwordHash: hashPassword("admin123"),
          role: "Admin",
          createdAt,
          updatedAt: createdAt
        }
      ],
      labs: [],
      simulations: [],
      defenseActions: [],
      reports: []
    };
    fs.writeFileSync(STORE_PATH, JSON.stringify(seed, null, 2));
  }
}

function loadStore() {
  ensureStore();
  return JSON.parse(fs.readFileSync(STORE_PATH, "utf8"));
}

let store = loadStore();
store.customScenarios ||= [];
for (const lab of store.labs) {
  lab.targetApplications ||= [];
}
saveStore();

function saveStore() {
  fs.writeFileSync(STORE_PATH, JSON.stringify(store, null, 2));
}

function send(res, status, data, extraHeaders = {}) {
  const body = JSON.stringify(data, null, 2);
  res.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": Buffer.byteLength(body),
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
    "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
    ...extraHeaders
  });
  res.end(body);
}

function sendError(res, status, message, details = undefined) {
  send(res, status, { error: message, details });
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    let body = "";
    req.on("data", (chunk) => {
      body += chunk;
      if (body.length > 1_000_000) {
        req.destroy();
        reject(new Error("Request body too large"));
      }
    });
    req.on("end", () => {
      if (!body) return resolve({});
      try {
        resolve(JSON.parse(body));
      } catch (error) {
        reject(error);
      }
    });
    req.on("error", reject);
  });
}

function publicUser(user) {
  if (!user) return null;
  const { passwordHash, ...safe } = user;
  return safe;
}

function authenticate(req) {
  const auth = req.headers.authorization || "";
  const token = auth.startsWith("Bearer ") ? auth.slice(7) : "";
  const userId = tokens.get(token);
  return store.users.find((user) => user.id === userId) || null;
}

function requireUser(req, res) {
  const user = authenticate(req);
  if (!user) {
    sendError(res, 401, "Authentication required");
    return null;
  }
  return user;
}

function canAccessLab(user, lab) {
  return user.role === "Admin" || user.role === "Instructor" || lab.userId === user.id;
}

function findTemplate(id) {
  return templateCatalog.find((template) => template.id === id);
}

function findScenario(id) {
  return [...scenarioCatalog, ...(store.customScenarios || [])].find((scenario) => scenario.id === id);
}

function visibleScenariosForUser(user) {
  const accessibleLabs = new Set(listLabsForUser(user).map((lab) => lab.id));
  return [...scenarioCatalog, ...(store.customScenarios || [])].filter((scenario) => {
    return !scenario.targetLabId || accessibleLabs.has(scenario.targetLabId);
  });
}

function assertSafeServiceName(serviceName) {
  return /^[a-z0-9]([-a-z0-9]*[a-z0-9])?$/.test(serviceName) && serviceName.length <= 63;
}

function serviceNamesForLab(lab) {
  return new Set((lab.services || []).map((service) => service.serviceName));
}

function normalizeTargetForTemplate(step, template) {
  const serviceNames = new Set(template.services.map((service) => service.name));
  if (serviceNames.has(step.target)) return step.target;

  const fallbackMap = {
    "employee-api": ["employee-api", "marks-api", "product-service"],
    "frontend-service": ["frontend-service", "student-portal"],
    "admin-api": ["admin-api", "payment-service"]
  };

  const candidates = fallbackMap[step.target] || [step.target];
  return candidates.find((candidate) => serviceNames.has(candidate)) || step.target;
}

function normalizeSourceForTemplate(source, template) {
  const serviceNames = new Set(template.services.map((service) => service.name));
  if (serviceNames.has(source) || source === "attack-pod") return source;
  if (source === "frontend-service" && serviceNames.has("student-portal")) return "student-portal";
  if (source === "employee-api" && serviceNames.has("marks-api")) return "marks-api";
  if (source === "employee-api" && serviceNames.has("product-service")) return "product-service";
  return source;
}

function appliedDefensesForLab(labId) {
  return store.defenseActions.filter((action) => action.labId === labId && action.status === "Applied");
}

function defenseBlocksStep(scenario, step, activeActionTypes) {
  if (activeActionTypes.has("RATE_LIMIT") && ["Brute Force", "DDoS-Style Traffic"].includes(scenario.attackType)) {
    return step.eventType === "failed_login" || step.eventType === "resource_exhaustion_pattern";
  }
  if (activeActionTypes.has("INPUT_VALIDATION") && ["SQL Injection", "Multi-Stage Attack"].includes(scenario.attackType)) {
    return step.eventType === "suspicious_input_pattern";
  }
  if (activeActionTypes.has("ENDPOINT_RESTRICTION") && ["Privilege Escalation", "Lateral Movement", "Multi-Stage Attack"].includes(scenario.attackType)) {
    return step.eventType === "restricted_endpoint_access";
  }
  if (activeActionTypes.has("NETWORK_POLICY") && ["Lateral Movement", "Multi-Stage Attack"].includes(scenario.attackType)) {
    return ["admin-api", "postgres-db", "payment-service"].includes(step.target) || step.eventType === "database_reachability_attempt";
  }
  if (activeActionTypes.has("RESOURCE_LIMIT") && scenario.attackType === "DDoS-Style Traffic") {
    return step.eventType === "resource_exhaustion_pattern";
  }
  return false;
}

function riskAfterDefense(defaultRisk, blocked) {
  if (!blocked) return defaultRisk;
  if (defaultRisk === "Critical") return "Medium";
  if (defaultRisk === "High") return "Low";
  return "Low";
}

function riskRank(risk) {
  return { Low: 1, Medium: 2, High: 3, Critical: 4 }[risk] || 0;
}

function normalLogsForSimulation(lab, template, simulationId, startedAt) {
  return template.normalTraffic.slice(0, 8).map((entry, index) => {
    const [method, endpoint] = entry.split(" ");
    const target = template.services[index % template.services.length].name;
    return {
      id: shortId("log"),
      timestamp: new Date(new Date(startedAt).getTime() + index * 400).toISOString(),
      labId: lab.id,
      simulationId,
      sourceService: "traffic-generator",
      targetService: target,
      method,
      endpoint,
      statusCode: 200,
      requestCount: 1,
      payloadCategory: "normal_user_behavior",
      eventType: "normal_request",
      severity: "Info",
      isAttackSimulation: false,
      rawLogJson: { generated_by: "pantheon-normal-traffic" }
    };
  });
}

function createAttackPath(template, steps, blockedTarget) {
  const nodeIds = new Set(["attack-pod"]);
  steps.forEach((step) => {
    nodeIds.add(step.source);
    nodeIds.add(step.target);
  });

  const nodes = Array.from(nodeIds).map((id) => {
    let state = "normal";
    if (id === "attack-pod") state = "targeted";
    if (steps.some((step) => step.target === id)) state = "suspicious";
    if (!blockedTarget && steps.length && id === steps[steps.length - 1].target) state = "compromised";
    if (blockedTarget && id === blockedTarget) state = "blocked";
    if (blockedTarget && template.services.some((service) => service.name === id) && !steps.some((step) => step.target === id)) state = "protected";
    return { id, label: id.replace(/-/g, " "), state };
  });

  const edges = steps.map((step) => ({
    from: step.source,
    to: step.target,
    eventCount: step.count,
    blocked: blockedTarget === step.target && step.blocked
  }));

  return { nodes, edges };
}

function createRecommendations(simulation, activeActionTypes) {
  return defenseCatalog
    .filter((defense) => defense.attackTypes.includes(simulation.attackType))
    .map((defense) => ({
      id: shortId("rec"),
      catalogId: defense.id,
      simulationId: simulation.id,
      recommendationType: defense.recommendationType,
      actionType: defense.actionType,
      title: defense.name,
      description: defense.description,
      defenseLevel: defense.defenseLevel,
      priority: defense.priority,
      isApplicable: !activeActionTypes.has(defense.actionType),
      alreadyApplied: activeActionTypes.has(defense.actionType),
      createdAt: nowIso()
    }));
}

function analyzeSimulation(scenario, reachedTargets, blocked, suspiciousEvents) {
  const confidence = Math.min(0.98, Math.max(0.72, 0.82 + reachedTargets.length * 0.025 + suspiciousEvents / 500));
  const riskLevel = riskAfterDefense(scenario.defaultRisk, blocked);
  const movementText = reachedTargets.length > 1 ? ` across ${reachedTargets.join(", ")}` : ` against ${reachedTargets[0] || "the lab"}`;
  const blockText = blocked ? " A configured defense blocked the sequence before it reached its original depth." : "";

  return {
    classification: scenario.attackType,
    confidenceScore: Number(confidence.toFixed(2)),
    riskLevel,
    explanation: `The request sequence matches ${scenario.attackType.toLowerCase()} behavior${movementText}, with ${suspiciousEvents} suspicious event(s).${blockText}`,
    recommendedDefenseCategories: defenseCatalog
      .filter((defense) => defense.attackTypes.includes(scenario.attackType))
      .map((defense) => defense.recommendationType)
  };
}

function buildComparison(lab, simulation) {
  const baselines = store.simulations
    .filter((candidate) => candidate.labId === lab.id && candidate.scenarioId === simulation.scenarioId && candidate.id !== simulation.id && candidate.appliedDefenseCount === 0)
    .sort((a, b) => new Date(b.completedAt) - new Date(a.completedAt));

  const baseline = baselines[0];
  if (!baseline || simulation.appliedDefenseCount === 0) return null;

  const baselineDepth = baseline.reachedServices.length;
  const currentDepth = simulation.reachedServices.length;
  const depthReduction = baselineDepth ? Math.max(0, Math.round(((baselineDepth - currentDepth) / baselineDepth) * 100)) : 0;

  return {
    baselineSimulationId: baseline.id,
    postDefenseSimulationId: simulation.id,
    before: {
      reachedServices: baseline.reachedServices,
      riskLevel: baseline.riskLevel,
      suspiciousEvents: baseline.suspiciousEventCount
    },
    after: {
      reachedServices: simulation.reachedServices,
      riskLevel: simulation.riskLevel,
      suspiciousEvents: simulation.suspiciousEventCount
    },
    improvement: {
      attackDepthReducedPercent: depthReduction,
      suspiciousEventsReducedBy: Math.max(0, baseline.suspiciousEventCount - simulation.suspiciousEventCount),
      blockedEarlier: simulation.blocked && currentDepth <= baselineDepth
    }
  };
}

function runSimulation(lab, scenario) {
  const template = findTemplate(lab.templateId);
  const simulationId = shortId("sim");
  const startedAt = nowIso();
  const activeDefenses = appliedDefensesForLab(lab.id);
  const activeActionTypes = new Set(activeDefenses.map((action) => action.actionType));
  const logs = normalLogsForSimulation(lab, template, simulationId, startedAt);
  const reachedServices = [];
  const pathSteps = [];
  let blocked = false;
  let blockedAt = null;
  let suspiciousEventCount = 0;

  for (const rawStep of scenario.steps) {
    const step = {
      ...rawStep,
      source: normalizeSourceForTemplate(rawStep.source, template),
      target: normalizeTargetForTemplate(rawStep, template)
    };
    const shouldBlock = defenseBlocksStep(scenario, step, activeActionTypes);
    const eventCount = shouldBlock ? Math.max(1, Math.ceil(step.count * 0.35)) : step.count;
    const normalizedStep = { ...step, count: eventCount, blocked: shouldBlock };
    pathSteps.push(normalizedStep);
    reachedServices.push(step.target);
    suspiciousEventCount += eventCount;

    for (let index = 0; index < eventCount; index += 1) {
      logs.push({
        id: shortId("log"),
        timestamp: new Date(new Date(startedAt).getTime() + logs.length * 550).toISOString(),
        labId: lab.id,
        simulationId,
        sourceService: step.source,
        targetService: step.target,
        method: step.method,
        endpoint: step.endpoint,
        statusCode: shouldBlock ? 403 : step.statusCode,
        requestCount: 1,
        payloadCategory: step.payloadCategory,
        eventType: shouldBlock ? "blocked_by_defense" : step.eventType,
        severity: shouldBlock ? "Warning" : riskRank(scenario.defaultRisk) >= 4 ? "Critical" : "High",
        isAttackSimulation: true,
        rawLogJson: {
          action_type: step.actionType,
          expected_signal: step.eventType,
          safe_simulation: true
        }
      });
    }

    if (shouldBlock) {
      blocked = true;
      blockedAt = step.target;
      break;
    }
  }

  const attackPath = createAttackPath(template, pathSteps, blockedAt);
  const analysis = analyzeSimulation(scenario, reachedServices, blocked, suspiciousEventCount);
  const recommendations = createRecommendations({ id: simulationId, attackType: scenario.attackType }, activeActionTypes);
  const completedAt = nowIso();
  const simulation = {
    id: simulationId,
    labId: lab.id,
    scenarioId: scenario.id,
    scenarioName: scenario.name,
    attackType: scenario.attackType,
    status: "Completed",
    startedAt,
    completedAt,
    riskLevel: analysis.riskLevel,
    resultSummary: blocked
      ? `Attack was blocked at ${blockedAt} after ${suspiciousEventCount} suspicious event(s).`
      : `Attack completed its simulated path through ${reachedServices.join(" -> ")}.`,
    blocked,
    blockedAt,
    reachedServices,
    suspiciousEventCount,
    appliedDefenseCount: activeDefenses.length,
    appliedDefenses: activeDefenses.map((action) => action.actionType),
    logs,
    attackPath,
    aiAnalysis: { id: shortId("ai"), simulationId, createdAt: completedAt, ...analysis },
    recommendations,
    comparison: null
  };

  simulation.comparison = buildComparison(lab, simulation);
  store.simulations.push(simulation);
  saveStore();
  return simulation;
}

function createReport(simulation) {
  const lab = store.labs.find((item) => item.id === simulation.labId);
  const template = findTemplate(lab.templateId);
  const scenario = findScenario(simulation.scenarioId);
  const existing = store.reports.find((report) => report.simulationId === simulation.id);
  if (existing) return existing;

  const report = {
    id: shortId("report"),
    simulationId: simulation.id,
    labId: lab.id,
    title: `${scenario.name} Report`,
    summary: simulation.resultSummary,
    createdAt: nowIso(),
    reportJson: {
      labInformation: {
        labId: lab.id,
        labName: lab.labName,
        namespace: lab.namespace,
        status: lab.status
      },
      organizationTemplate: template.name,
      targetApplications: (lab.targetApplications || []).map((target) => ({
        appName: target.appName,
        serviceName: target.serviceName,
        internalUrl: target.internalUrl,
        status: target.status,
        safetyState: target.safetyState
      })),
      attackScenario: {
        id: scenario.id,
        name: scenario.name,
        attackType: scenario.attackType,
        difficulty: scenario.difficulty
      },
      timelineOfEvents: simulation.logs.slice(0, 25),
      attackPath: simulation.attackPath,
      aiClassification: simulation.aiAnalysis,
      riskLevel: simulation.riskLevel,
      defenseRecommendations: simulation.recommendations,
      appliedDefenses: appliedDefensesForLab(lab.id),
      beforeAfterComparison: simulation.comparison,
      conclusion: simulation.blocked
        ? "The selected defensive controls reduced the simulated attack path."
        : "The simulation completed without an active control blocking the attack path."
    }
  };
  store.reports.push(report);
  saveStore();
  return report;
}

function listLabsForUser(user) {
  return store.labs.filter((lab) => canAccessLab(user, lab));
}

function labResponse(lab) {
  const template = findTemplate(lab.templateId);
  return {
    ...lab,
    template,
    services: lab.services,
    targetApplications: lab.targetApplications || [],
    activeDefenses: appliedDefensesForLab(lab.id),
    latestSimulation: store.simulations.filter((simulation) => simulation.labId === lab.id).at(-1) || null
  };
}

function mockKubernetesStatus(lab) {
  const services = (lab.services || []).map((service) => ({
    name: service.serviceName,
    type: service.serviceType,
    status: service.status === "Deleted" ? "Missing" : service.status || "Running",
    replicas: service.status === "Stopped" ? 0 : 1,
    readyReplicas: service.status === "Stopped" ? 0 : 1,
    availableReplicas: service.status === "Stopped" ? 0 : 1,
    pods: [
      {
        name: `${service.serviceName}-mock`,
        phase: service.status === "Stopped" ? "Succeeded" : "Running",
        readyContainers: service.status === "Stopped" ? 0 : 1,
        totalContainers: 1,
        restartCount: 0
      }
    ],
    conditions: []
  }));
  const ready = services.filter((service) => service.status === "Running").length;
  const failed = services.filter((service) => service.status === "Failed" || service.status === "Missing").length;
  return {
    labId: lab.id,
    mode: "mock",
    namespace: { name: lab.namespace, phase: "Mock" },
    summary: {
      totalServices: services.length,
      readyServices: ready,
      pendingServices: Math.max(0, services.length - ready - failed),
      failedServices: failed,
      allReady: services.length > 0 && ready === services.length
    },
    services,
    jobs: [],
    observedAt: nowIso()
  };
}

function contentTypeFor(filePath) {
  const ext = path.extname(filePath).toLowerCase();
  const types = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".json": "application/json; charset=utf-8"
  };
  return types[ext] || "application/octet-stream";
}

function serveStatic(req, res, pathname) {
  const requested = pathname === "/" ? "/index.html" : pathname;
  const safePath = path.normalize(requested).replace(/^(\.\.[/\\])+/, "");
  const filePath = path.join(FRONTEND_DIR, safePath);
  if (!filePath.startsWith(FRONTEND_DIR)) {
    res.writeHead(403);
    res.end("Forbidden");
    return;
  }
  if (!fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) {
    const indexPath = path.join(FRONTEND_DIR, "index.html");
    res.writeHead(200, { "Content-Type": contentTypeFor(indexPath) });
    res.end(fs.readFileSync(indexPath));
    return;
  }
  res.writeHead(200, { "Content-Type": contentTypeFor(filePath) });
  res.end(fs.readFileSync(filePath));
}

async function handleApi(req, res, pathname) {
  if (req.method === "OPTIONS") {
    send(res, 204, {});
    return;
  }

  if (req.method === "GET" && pathname === "/api/health") {
    send(res, 200, {
      status: "ok",
      product: "Pantheon",
      mode: "safe-simulation",
      timestamp: nowIso()
    });
    return;
  }

  if (req.method === "POST" && pathname === "/api/auth/register") {
    const body = await readBody(req);
    if (!body.email || !body.password || !body.name) return sendError(res, 400, "name, email, and password are required");
    if (store.users.some((user) => user.email.toLowerCase() === String(body.email).toLowerCase())) {
      return sendError(res, 409, "A user with that email already exists");
    }
    const createdAt = nowIso();
    const user = {
      id: shortId("user"),
      name: body.name,
      email: body.email,
      passwordHash: hashPassword(body.password),
      role: ["Student", "Instructor", "Admin"].includes(body.role) ? body.role : "Student",
      createdAt,
      updatedAt: createdAt
    };
    store.users.push(user);
    saveStore();
    const token = shortId("token");
    tokens.set(token, user.id);
    send(res, 201, { token, user: publicUser(user) });
    return;
  }

  if (req.method === "POST" && pathname === "/api/auth/login") {
    const body = await readBody(req);
    const user = store.users.find((candidate) => candidate.email.toLowerCase() === String(body.email || "").toLowerCase());
    if (!user || user.passwordHash !== hashPassword(body.password || "")) return sendError(res, 401, "Invalid email or password");
    const token = shortId("token");
    tokens.set(token, user.id);
    send(res, 200, { token, user: publicUser(user) });
    return;
  }

  if (req.method === "GET" && pathname === "/api/auth/me") {
    const user = requireUser(req, res);
    if (!user) return;
    send(res, 200, { user: publicUser(user) });
    return;
  }

  if (req.method === "GET" && pathname === "/api/templates") {
    send(res, 200, { templates: templateCatalog });
    return;
  }

  const templateMatch = pathname.match(/^\/api\/templates\/([^/]+)$/);
  if (req.method === "GET" && templateMatch) {
    const template = findTemplate(templateMatch[1]);
    if (!template) return sendError(res, 404, "Template not found");
    send(res, 200, { template });
    return;
  }

  if (req.method === "GET" && pathname === "/api/scenarios") {
    const user = authenticate(req);
    send(res, 200, { scenarios: user ? visibleScenariosForUser(user) : scenarioCatalog });
    return;
  }

  const scenarioMatch = pathname.match(/^\/api\/scenarios\/([^/]+)$/);
  if (req.method === "GET" && scenarioMatch) {
    const scenario = findScenario(scenarioMatch[1]);
    const user = authenticate(req);
    if (!scenario || (scenario.targetLabId && (!user || !visibleScenariosForUser(user).some((item) => item.id === scenario.id)))) {
      return sendError(res, 404, "Scenario not found");
    }
    send(res, 200, { scenario });
    return;
  }

  if (pathname.startsWith("/api/")) {
    const user = requireUser(req, res);
    if (!user) return;

    if (req.method === "POST" && pathname === "/api/labs") {
      const body = await readBody(req);
      const template = findTemplate(body.template_id || body.templateId || "small-company");
      if (!template) return sendError(res, 400, "Unknown organization template");
      const createdAt = nowIso();
      const labId = shortId("lab");
      const lab = {
        id: labId,
        userId: user.id,
        templateId: template.id,
        labName: body.lab_name || body.labName || `${template.name} Lab`,
        namespace: `pantheon-${labId.replace("_", "-")}`,
        status: "Running",
        deploymentMode: "Mock Kubernetes",
        createdAt,
        deletedAt: null,
        targetApplications: [],
        services: template.services.map((service) => ({
          id: shortId("svc"),
          labId,
          serviceName: service.name,
          serviceType: service.type,
          kubernetesDeploymentName: `${service.name}-deployment`,
          kubernetesServiceName: service.name,
          status: "Running",
          port: service.port,
          exposed: service.exposed,
          createdAt
        }))
      };
      store.labs.push(lab);
      saveStore();
      send(res, 201, { lab: labResponse(lab) });
      return;
    }

    if (req.method === "GET" && pathname === "/api/labs") {
      send(res, 200, { labs: listLabsForUser(user).map(labResponse) });
      return;
    }

    const labMatch = pathname.match(/^\/api\/labs\/([^/]+)$/);
    if (labMatch) {
      const lab = store.labs.find((item) => item.id === labMatch[1]);
      if (!lab || !canAccessLab(user, lab)) return sendError(res, 404, "Lab not found");
      if (req.method === "GET") {
        send(res, 200, { lab: labResponse(lab) });
        return;
      }
      if (req.method === "DELETE") {
        lab.status = "Deleted";
        lab.deletedAt = nowIso();
        saveStore();
        send(res, 200, { lab: labResponse(lab) });
        return;
      }
    }

    const labStateMatch = pathname.match(/^\/api\/labs\/([^/]+)\/(start|stop)$/);
    if (req.method === "POST" && labStateMatch) {
      const lab = store.labs.find((item) => item.id === labStateMatch[1]);
      if (!lab || !canAccessLab(user, lab)) return sendError(res, 404, "Lab not found");
      lab.status = labStateMatch[2] === "start" ? "Running" : "Stopped";
      saveStore();
      send(res, 200, { lab: labResponse(lab) });
      return;
    }

    const targetAppsMatch = pathname.match(/^\/api\/labs\/([^/]+)\/target-apps$/);
    if (targetAppsMatch) {
      const lab = store.labs.find((item) => item.id === targetAppsMatch[1]);
      if (!lab || !canAccessLab(user, lab)) return sendError(res, 404, "Lab not found");
      lab.targetApplications ||= [];
      if (req.method === "GET") {
        send(res, 200, { targetApplications: lab.targetApplications });
        return;
      }
      if (req.method === "POST") {
        const body = await readBody(req);
        const appName = String(body.app_name || body.appName || "").trim();
        const serviceName = String(body.service_name || body.serviceName || appName.toLowerCase().replace(/[^a-z0-9-]+/g, "-")).replace(/^-+|-+$/g, "");
        const importType = String(body.import_type || body.importType || "docker-image").trim().toLowerCase();
        const port = Number(body.port || 8080);
        const healthPath = String(body.health_path || body.healthPath || "/").startsWith("/")
          ? String(body.health_path || body.healthPath || "/")
          : `/${body.health_path || body.healthPath}`;
        if (!appName) return sendError(res, 400, "appName is required");
        if (!assertSafeServiceName(serviceName)) return sendError(res, 400, "Service name must be a safe Kubernetes DNS label");
        if (!Number.isInteger(port) || port < 1 || port > 65535) return sendError(res, 400, "port must be between 1 and 65535");
        if (!new Set(["docker-image", "kubernetes-yaml", "local-service"]).has(importType)) return sendError(res, 400, "Unsupported import type");
        if (serviceNamesForLab(lab).has(serviceName)) return sendError(res, 409, "A service with this name already exists in the lab");
        if (importType === "docker-image" && !body.image) return sendError(res, 400, "Docker image import requires an image name");
        if (importType === "kubernetes-yaml" && !body.manifest) return sendError(res, 400, "Kubernetes YAML import requires a manifest");
        const createdAt = nowIso();
        const target = {
          id: shortId("target"),
          labId: lab.id,
          appName,
          serviceName,
          importType,
          image: body.image || null,
          port,
          healthPath,
          status: lab.status === "Running" ? "Running" : "Registered",
          internalUrl: `http://${serviceName}:${port}`,
          safetyState: "Contained",
          manifestJson: {
            manifest: body.manifest || null,
            local_url: body.local_url || body.localUrl || null,
            normal_paths: body.normal_paths || body.normalPaths || [`GET ${healthPath}`],
            safety_boundary: "lab-namespace-only"
          },
          createdAt
        };
        lab.targetApplications.push(target);
        lab.services.push({
          id: shortId("svc"),
          labId: lab.id,
          serviceName,
          serviceType: "target-app",
          kubernetesDeploymentName: serviceName,
          kubernetesServiceName: serviceName,
          status: target.status,
          port,
          exposed: false,
          createdAt
        });
        saveStore();
        send(res, 201, { targetApplication: target, lab: labResponse(lab) });
        return;
      }
    }

    const customScenarioMatch = pathname.match(/^\/api\/labs\/([^/]+)\/custom-scenarios$/);
    if (req.method === "POST" && customScenarioMatch) {
      const lab = store.labs.find((item) => item.id === customScenarioMatch[1]);
      if (!lab || !canAccessLab(user, lab)) return sendError(res, 404, "Lab not found");
      const body = await readBody(req);
      const targetService = String(body.target_service || body.targetService || "").trim();
      if (!targetService || targetService.includes("://") || targetService.includes("/") || !serviceNamesForLab(lab).has(targetService)) {
        return sendError(res, 400, "Custom scenario target must be an internal service in this lab");
      }
      let endpoint = String(body.endpoint || "/").trim() || "/";
      if (endpoint.includes("://")) return sendError(res, 400, "Endpoint must be a path, not a URL");
      if (!endpoint.startsWith("/")) endpoint = `/${endpoint}`;
      const method = String(body.method || "GET").toUpperCase();
      const allowedMethods = new Set(["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"]);
      if (!allowedMethods.has(method)) return sendError(res, 400, "Unsupported HTTP method for safe scenario template");
      const risk = ["Low", "Medium", "High", "Critical"].includes(body.risk_level || body.riskLevel) ? body.risk_level || body.riskLevel : "Medium";
      const count = Math.max(1, Math.min(100, Number(body.request_count || body.requestCount || 12)));
      const scenario = {
        id: `custom-${lab.id.replace(/[^a-z0-9]/g, "").slice(0, 8)}-${crypto.randomBytes(4).toString("hex")}`,
        name: body.name || "Custom Web App Probe",
        description: `User-defined safe scenario targeting ${targetService} inside ${lab.namespace}.`,
        difficulty: "Custom",
        attackType: body.attack_type || body.attackType || "Custom Web App Probe",
        allowedTemplateIds: [lab.templateId],
        targetServices: [targetService],
        defaultRisk: risk,
        isCustom: true,
        targetLabId: lab.id,
        steps: [
          {
            order: 1,
            actionType: "CUSTOM_WEB_APP_REQUEST_PATTERN",
            source: "attack-pod",
            target: targetService,
            method,
            endpoint,
            eventType: "custom_web_app_signal",
            payloadCategory: body.payload_category || body.payloadCategory || "custom_probe",
            statusCode: 200,
            count
          }
        ]
      };
      store.customScenarios.push(scenario);
      saveStore();
      send(res, 201, { scenario });
      return;
    }

    const labKubernetesStatusMatch = pathname.match(/^\/api\/labs\/([^/]+)\/kubernetes-status$/);
    if (req.method === "GET" && labKubernetesStatusMatch) {
      const lab = store.labs.find((item) => item.id === labKubernetesStatusMatch[1]);
      if (!lab || !canAccessLab(user, lab)) return sendError(res, 404, "Lab not found");
      const status = mockKubernetesStatus(lab);
      saveStore();
      send(res, 200, { kubernetesStatus: status, lab: labResponse(lab) });
      return;
    }

    const labSimulationMatch = pathname.match(/^\/api\/labs\/([^/]+)\/simulations$/);
    if (req.method === "POST" && labSimulationMatch) {
      const lab = store.labs.find((item) => item.id === labSimulationMatch[1]);
      if (!lab || !canAccessLab(user, lab)) return sendError(res, 404, "Lab not found");
      if (lab.status !== "Running") return sendError(res, 409, "Lab must be running before simulation");
      const body = await readBody(req);
      const scenario = findScenario(body.scenario_id || body.scenarioId);
      if (!scenario) return sendError(res, 400, "Unknown scenario");
      if (scenario.targetLabId) {
        if (scenario.targetLabId !== lab.id) return sendError(res, 400, "Custom scenario belongs to a different lab");
        const serviceNames = serviceNamesForLab(lab);
        if (scenario.steps.some((step) => !serviceNames.has(step.target))) {
          return sendError(res, 400, "Custom scenario target is outside this lab");
        }
      } else if (!scenario.allowedTemplateIds.includes(lab.templateId)) {
        return sendError(res, 400, "Scenario is not compatible with this lab template");
      }
      const simulation = runSimulation(lab, scenario);
      send(res, 201, { simulation });
      return;
    }

    const labLogsMatch = pathname.match(/^\/api\/labs\/([^/]+)\/logs$/);
    if (req.method === "GET" && labLogsMatch) {
      const lab = store.labs.find((item) => item.id === labLogsMatch[1]);
      if (!lab || !canAccessLab(user, lab)) return sendError(res, 404, "Lab not found");
      const logs = store.simulations.filter((simulation) => simulation.labId === lab.id).flatMap((simulation) => simulation.logs);
      send(res, 200, { logs });
      return;
    }

    const labDefensesMatch = pathname.match(/^\/api\/labs\/([^/]+)\/defenses$/);
    if (req.method === "GET" && labDefensesMatch) {
      const lab = store.labs.find((item) => item.id === labDefensesMatch[1]);
      if (!lab || !canAccessLab(user, lab)) return sendError(res, 404, "Lab not found");
      send(res, 200, { defenses: appliedDefensesForLab(lab.id), catalog: defenseCatalog });
      return;
    }

    const applyDefenseMatch = pathname.match(/^\/api\/labs\/([^/]+)\/defenses\/apply$/);
    if (req.method === "POST" && applyDefenseMatch) {
      const lab = store.labs.find((item) => item.id === applyDefenseMatch[1]);
      if (!lab || !canAccessLab(user, lab)) return sendError(res, 404, "Lab not found");
      const body = await readBody(req);
      const requested = Array.isArray(body.defense_ids) ? body.defense_ids : [body.defense_id || body.catalogId].filter(Boolean);
      if (!requested.length) return sendError(res, 400, "At least one defense_id is required");
      const applied = [];
      for (const defenseId of requested) {
        const defense = defenseCatalog.find((item) => item.id === defenseId);
        if (!defense) continue;
        const existing = store.defenseActions.find((action) => action.labId === lab.id && action.actionType === defense.actionType && action.status === "Applied");
        if (existing) {
          applied.push(existing);
          continue;
        }
        const action = {
          id: shortId("defense"),
          labId: lab.id,
          simulationId: body.simulation_id || body.simulationId || null,
          recommendationId: body.recommendation_id || body.recommendationId || null,
          catalogId: defense.id,
          actionType: defense.actionType,
          title: defense.name,
          status: "Applied",
          appliedAt: nowIso(),
          detailsJson: {
            mode: "safe_simulation",
            kubernetes_changes: defense.actionType === "NETWORK_POLICY" ? "mock-network-policy-applied" : "not-required"
          }
        };
        store.defenseActions.push(action);
        applied.push(action);
      }
      saveStore();
      send(res, 200, { applied, defenses: appliedDefensesForLab(lab.id) });
      return;
    }

    const simulationMatch = pathname.match(/^\/api\/simulations\/([^/]+)$/);
    if (simulationMatch) {
      const simulation = store.simulations.find((item) => item.id === simulationMatch[1]);
      if (!simulation) return sendError(res, 404, "Simulation not found");
      const lab = store.labs.find((item) => item.id === simulation.labId);
      if (!lab || !canAccessLab(user, lab)) return sendError(res, 404, "Simulation not found");
      if (req.method === "GET") {
        send(res, 200, { simulation });
        return;
      }
    }

    const simulationStopMatch = pathname.match(/^\/api\/simulations\/([^/]+)\/stop$/);
    if (req.method === "POST" && simulationStopMatch) {
      const simulation = store.simulations.find((item) => item.id === simulationStopMatch[1]);
      if (!simulation) return sendError(res, 404, "Simulation not found");
      const lab = store.labs.find((item) => item.id === simulation.labId);
      if (!lab || !canAccessLab(user, lab)) return sendError(res, 404, "Simulation not found");
      simulation.status = "Stopped";
      simulation.completedAt = nowIso();
      saveStore();
      send(res, 200, { simulation });
      return;
    }

    const simulationLogsMatch = pathname.match(/^\/api\/simulations\/([^/]+)\/logs$/);
    if (req.method === "GET" && simulationLogsMatch) {
      const simulation = store.simulations.find((item) => item.id === simulationLogsMatch[1]);
      if (!simulation) return sendError(res, 404, "Simulation not found");
      const lab = store.labs.find((item) => item.id === simulation.labId);
      if (!lab || !canAccessLab(user, lab)) return sendError(res, 404, "Simulation not found");
      send(res, 200, { logs: simulation.logs });
      return;
    }

    const analyzeMatch = pathname.match(/^\/api\/simulations\/([^/]+)\/analyze$/);
    if (req.method === "POST" && analyzeMatch) {
      const simulation = store.simulations.find((item) => item.id === analyzeMatch[1]);
      if (!simulation) return sendError(res, 404, "Simulation not found");
      const lab = store.labs.find((item) => item.id === simulation.labId);
      if (!lab || !canAccessLab(user, lab)) return sendError(res, 404, "Simulation not found");
      send(res, 200, { analysis: simulation.aiAnalysis });
      return;
    }

    const analysisMatch = pathname.match(/^\/api\/simulations\/([^/]+)\/analysis$/);
    if (req.method === "GET" && analysisMatch) {
      const simulation = store.simulations.find((item) => item.id === analysisMatch[1]);
      if (!simulation) return sendError(res, 404, "Simulation not found");
      const lab = store.labs.find((item) => item.id === simulation.labId);
      if (!lab || !canAccessLab(user, lab)) return sendError(res, 404, "Simulation not found");
      send(res, 200, { analysis: simulation.aiAnalysis });
      return;
    }

    const recommendationsMatch = pathname.match(/^\/api\/simulations\/([^/]+)\/recommendations$/);
    if (req.method === "GET" && recommendationsMatch) {
      const simulation = store.simulations.find((item) => item.id === recommendationsMatch[1]);
      if (!simulation) return sendError(res, 404, "Simulation not found");
      const lab = store.labs.find((item) => item.id === simulation.labId);
      if (!lab || !canAccessLab(user, lab)) return sendError(res, 404, "Simulation not found");
      send(res, 200, { recommendations: simulation.recommendations });
      return;
    }

    const reportCreateMatch = pathname.match(/^\/api\/simulations\/([^/]+)\/report$/);
    if (req.method === "POST" && reportCreateMatch) {
      const simulation = store.simulations.find((item) => item.id === reportCreateMatch[1]);
      if (!simulation) return sendError(res, 404, "Simulation not found");
      const lab = store.labs.find((item) => item.id === simulation.labId);
      if (!lab || !canAccessLab(user, lab)) return sendError(res, 404, "Simulation not found");
      const report = createReport(simulation);
      send(res, 201, { report });
      return;
    }

    const reportMatch = pathname.match(/^\/api\/reports\/([^/]+)$/);
    if (req.method === "GET" && reportMatch) {
      const report = store.reports.find((item) => item.id === reportMatch[1]);
      if (!report) return sendError(res, 404, "Report not found");
      const lab = store.labs.find((item) => item.id === report.labId);
      if (!lab || !canAccessLab(user, lab)) return sendError(res, 404, "Report not found");
      send(res, 200, { report });
      return;
    }

    const labReportsMatch = pathname.match(/^\/api\/labs\/([^/]+)\/reports$/);
    if (req.method === "GET" && labReportsMatch) {
      const lab = store.labs.find((item) => item.id === labReportsMatch[1]);
      if (!lab || !canAccessLab(user, lab)) return sendError(res, 404, "Lab not found");
      send(res, 200, { reports: store.reports.filter((report) => report.labId === lab.id) });
      return;
    }
  }

  sendError(res, 404, "Route not found");
}

const server = http.createServer(async (req, res) => {
  try {
    const requestUrl = new URL(req.url, `http://${req.headers.host || "localhost"}`);
    if (requestUrl.pathname.startsWith("/api/")) {
      await handleApi(req, res, requestUrl.pathname);
      return;
    }
    serveStatic(req, res, requestUrl.pathname);
  } catch (error) {
    sendError(res, 500, "Internal server error", error.message);
  }
});

server.listen(PORT, () => {
  console.log(`Pantheon MVP running at http://localhost:${PORT}`);
  console.log("Demo user: demo@pantheon.local / pantheon123");
});
