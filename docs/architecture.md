# Pantheon Architecture

## MVP Mode

```text
Browser Dashboard
       |
       v
Node.js HTTP Server
       |
       +-- Static frontend
       +-- Mock REST API
       +-- Simulation generator
       +-- Rule-based AI classifier
       +-- Defense recommendation engine
       +-- Local JSON persistence
```

## FastAPI Backend Architecture

```text
FastAPI
  |
  +-- Auth routes
  +-- Template routes
  +-- Scenario routes
  +-- Lab routes
  |
  v
SQLAlchemy
  |
  v
PostgreSQL

Lab routes
  |
  v
KubernetesService
  |
  +-- dry-run mode: records intended resources
  +-- real mode: creates Namespace, ResourceQuota, LimitRange,
      NetworkPolicy, Deployments, and ClusterIP Services
  +-- real simulation mode: creates traffic and attack Jobs,
      waits for completion, reads JSON pod logs, stores them
      as SimulationLog rows
```

## Target Production Architecture

```text
React Dashboard
       |
       v
FastAPI Backend
       |
       +-- PostgreSQL
       +-- Kubernetes Client
       +-- Attack Engine Jobs
       +-- AI Analyzer
       |
       v
Kubernetes Cluster
       |
       +-- Namespace per lab
       +-- Fake microservices
       +-- Traffic generator
       +-- Attack simulation job
       +-- NetworkPolicy defenses
```

## Safety Boundary

Pantheon attack scenarios must target only services defined in the selected lab template. In mock mode this is enforced by generated internal service names. In Kubernetes mode, the orchestrator should validate the namespace and service list before creating any attack job.
