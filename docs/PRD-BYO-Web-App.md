# Pantheon Enhanced PRD: Bring Your Own Web App Labs

## 1. Enhancement Summary

Pantheon will support user-provided web applications as first-class lab targets. A user can import an app into a Kubernetes lab namespace, create safe custom attack scenarios against that internal service, run traffic and attack jobs inside the same namespace, and review visual indicators showing target containment, scenario scope, risk, defenses, and report output.

This enhancement keeps Pantheon aligned with the original idea of simulating attacks on a web page or web app while preserving the project's safety boundary: Pantheon must never attack arbitrary public URLs or third-party systems.

## 2. Product Goal

Allow a student, instructor, or evaluator to attach their own web app to a Pantheon lab and run controlled, internal-only simulations against it.

## 3. Safety Model

Pantheon does not accept external attack targets. Every custom scenario must target a Kubernetes service that belongs to the selected lab namespace.

Allowed target forms:

```text
http://service-name:port/path
service-name/path
```

Rejected target forms:

```text
https://public-site.example
192.168.1.50
external-domain.com
any URL outside the lab service registry
```

## 4. New Core Workflow

```text
1. User creates or opens a Pantheon lab.
2. User imports a web app as a Docker image, constrained Kubernetes YAML, or local-service metadata.
3. Pantheon registers the app as an internal lab service.
4. Pantheon deploys supported app imports inside the lab namespace.
5. User creates a custom scenario bound to that internal service.
6. Pantheon validates that every scenario target belongs to the lab.
7. Pantheon runs traffic and attack jobs from inside the namespace.
8. Dashboard shows containment, target, risk, path, AI, defense, and report indicators.
```

## 5. MVP Requirements

```text
BYO-001: The system shall allow a user to register a target web app for a lab.
BYO-002: The system shall support Docker image based app imports in real Kubernetes mode.
BYO-003: The system shall store Kubernetes YAML and local-service metadata for future import workflows.
BYO-004: The system shall create an internal service identity for each imported app.
BYO-005: The system shall prevent duplicate service names inside a lab.
BYO-006: The system shall reject custom scenario targets that are not lab services.
BYO-007: The system shall allow users to create custom scenarios from safe templates.
BYO-008: The system shall run simulations only against internal lab services.
BYO-009: The system shall include imported apps in reports.
BYO-010: The dashboard shall show visual indicators for containment, target status, attack scope, risk, and defense state.
```

## 6. Visual Indicators

The dashboard should clearly show:

```text
Contained: target is inside the lab namespace.
Internal-only: scenario target is a Kubernetes service, not an external URL.
Imported app: service came from user configuration.
Preset scenario: scenario came from Pantheon catalog.
Custom scenario: scenario was created by the user for the selected lab.
Blocked: defense stopped a step.
Protected: service was not reached after defense.
Risk: Low, Medium, High, Critical.
```

## 7. Data Model Additions

```text
TargetApplication
- id
- lab_id
- app_name
- service_name
- import_type
- image
- port
- health_path
- status
- internal_url
- safety_state
- manifest_json
- created_at
```

Custom scenarios use the existing `AttackScenario` table with scenario metadata:

```json
{
  "is_custom": true,
  "custom_lab_id": "lab uuid",
  "target_services": ["user-app-service"],
  "steps": []
}
```

## 8. Kubernetes Import Support

MVP support:

```text
Docker image import: deploys a locked-down Deployment and ClusterIP Service.
Kubernetes YAML import: accepts constrained Deployment/Service YAML for controlled apply.
Local-service config: stored as metadata unless an image is provided; external local URLs are not attack targets.
```

## 9. Acceptance Criteria

```text
AC-BYO-001: A running lab can register a user web app target.
AC-BYO-002: The target appears in the lab service list and target app panel.
AC-BYO-003: The dashboard marks the imported target as contained and internal-only.
AC-BYO-004: A user can create a custom scenario against that target.
AC-BYO-005: A custom scenario cannot target an external URL or non-lab service.
AC-BYO-006: The simulation result includes the imported app in logs and attack path data.
AC-BYO-007: The report includes imported app context.
```
