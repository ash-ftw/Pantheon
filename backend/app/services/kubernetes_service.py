from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from app.config import Settings, settings


class KubernetesProvisioningError(RuntimeError):
    pass


@dataclass(frozen=True)
class ResourceResult:
    kind: str
    name: str
    status: str
    message: str | None = None


class KubernetesService:
    def __init__(self, app_settings: Settings = settings) -> None:
        self.settings = app_settings
        self.mode = app_settings.kubernetes_mode
        self._core = None
        self._apps = None
        self._networking = None
        self._batch = None

    @property
    def is_dry_run(self) -> bool:
        return self.mode != "real"

    def create_lab(self, namespace: str, services: list[dict[str, Any]]) -> list[ResourceResult]:
        self._validate_namespace(namespace)
        self._validate_services(services)
        if self.is_dry_run:
            return self._dry_run_create(namespace, services)

        self._connect()
        results: list[ResourceResult] = []
        results.append(self._create_namespace(namespace))
        results.append(self._create_resource_quota(namespace))
        results.append(self._create_limit_range(namespace))
        results.append(self._create_default_network_policy(namespace))
        for service in services:
            results.append(self._create_deployment(namespace, service))
            results.append(self._create_service(namespace, service))
        return results

    def delete_lab(self, namespace: str) -> list[ResourceResult]:
        self._validate_namespace(namespace)
        if self.is_dry_run:
            return [ResourceResult("Namespace", namespace, "Deleted", "Dry-run namespace deletion recorded.")]

        self._connect()
        try:
            self._core.delete_namespace(namespace)
            return [ResourceResult("Namespace", namespace, "Deleting", "Kubernetes namespace deletion requested.")]
        except Exception as exc:  # pragma: no cover - depends on cluster client
            raise KubernetesProvisioningError(f"Unable to delete namespace {namespace}: {exc}") from exc

    def set_lab_scale(self, namespace: str, services: list[dict[str, Any]], replicas: int) -> list[ResourceResult]:
        self._validate_namespace(namespace)
        if replicas < 0 or replicas > 3:
            raise KubernetesProvisioningError("Replica count must be between 0 and 3 for lab safety.")
        if self.is_dry_run:
            status = "Running" if replicas else "Stopped"
            return [ResourceResult("Deployment", item["name"], status, "Dry-run scale recorded.") for item in services]

        self._connect()
        results: list[ResourceResult] = []
        try:
            for service in services:
                body = {"spec": {"replicas": replicas}}
                self._apps.patch_namespaced_deployment_scale(service["name"], namespace, body)
                results.append(ResourceResult("Deployment", service["name"], "Scaled", f"Replicas set to {replicas}."))
        except Exception as exc:  # pragma: no cover - depends on cluster client
            raise KubernetesProvisioningError(f"Unable to scale lab deployments in {namespace}: {exc}") from exc
        return results


    def deploy_target_application(self, namespace: str, app: dict[str, Any]) -> list[ResourceResult]:
        self._validate_namespace(namespace)
        self._validate_services([app])
        import_type = str(app.get("import_type") or "docker-image")
        if self.is_dry_run:
            return [
                ResourceResult("Deployment", app["name"], "Created", f"Dry-run {import_type} target app deployment recorded."),
                ResourceResult("Service", app["name"], "Created", "Dry-run internal ClusterIP service recorded."),
            ]

        self._connect()
        if import_type == "kubernetes-yaml":
            return self._apply_target_manifest(namespace, app)
        if import_type == "local-service" and not app.get("image"):
            raise KubernetesProvisioningError(
                "Local-service targets must be containerized before real Kubernetes deployment. Provide an image or constrained YAML."
            )
        return [self._create_deployment(namespace, app), self._create_service(namespace, app)]

    def _connect(self) -> None:
        if self._core and self._apps and self._networking and self._batch:
            return
        try:
            from kubernetes import client, config
            from kubernetes.config.config_exception import ConfigException
        except ImportError as exc:
            raise KubernetesProvisioningError(
                "The kubernetes Python package is not installed. Install backend/requirements.txt first."
            ) from exc

        try:
            config.load_incluster_config()
        except ConfigException:
            config.load_kube_config(config_file=self.settings.kubeconfig)

        self._core = client.CoreV1Api()
        self._apps = client.AppsV1Api()
        self._networking = client.NetworkingV1Api()
        self._batch = client.BatchV1Api()

    def get_lab_status(self, namespace: str, services: list[dict[str, Any]]) -> dict[str, Any]:
        self._validate_namespace(namespace)
        self._validate_services(services)
        if self.is_dry_run:
            return self._dry_run_status(namespace, services)

        self._connect()
        try:
            namespace_obj = self._core.read_namespace(namespace)
            service_statuses = [self._deployment_service_status(namespace, service) for service in services]
            jobs = self._list_runner_jobs(namespace)
        except Exception as exc:  # pragma: no cover - depends on cluster client
            raise KubernetesProvisioningError(f"Unable to inspect Kubernetes status for {namespace}: {exc}") from exc

        failed = sum(1 for item in service_statuses if item["status"] in {"Failed", "Missing"})
        ready = sum(1 for item in service_statuses if item["status"] == "Running")
        pending = sum(1 for item in service_statuses if item["status"] == "Pending")
        return {
            "mode": self.mode,
            "namespace": {
                "name": namespace,
                "phase": getattr(namespace_obj.status, "phase", "Unknown"),
            },
            "summary": {
                "totalServices": len(service_statuses),
                "readyServices": ready,
                "pendingServices": pending,
                "failedServices": failed,
                "allReady": bool(service_statuses) and ready == len(service_statuses),
            },
            "services": service_statuses,
            "jobs": jobs,
            "observedAt": self._now_iso(),
        }

    def run_simulation_jobs(
        self,
        namespace: str,
        simulation_id: str,
        services: list[dict[str, Any]],
        scenario_config: dict[str, Any],
        normal_traffic: list[str],
    ) -> list[dict[str, Any]]:
        self._validate_namespace(namespace)
        self._validate_services(services)
        self._validate_scenario_targets(scenario_config, services)
        if self.is_dry_run:
            return []

        self._connect()
        run_id = uuid4().hex[:8]
        traffic_job = f"pantheon-traffic-{run_id}"
        attack_job = f"pantheon-attack-{run_id}"
        results: list[dict[str, Any]] = []
        try:
            results.extend(
                self._run_observed_job(
                    namespace=namespace,
                    simulation_id=simulation_id,
                    job_name=traffic_job,
                    command=["python", "traffic_generator.py"],
                    env={
                        "SIMULATION_ID_JSON": json.dumps(simulation_id),
                        "SERVICES_JSON": json.dumps(services),
                        "NORMAL_TRAFFIC_JSON": json.dumps(normal_traffic),
                    },
                )
            )
            results.extend(
                self._run_observed_job(
                    namespace=namespace,
                    simulation_id=simulation_id,
                    job_name=attack_job,
                    command=["python", "runner.py"],
                    env={
                        "SIMULATION_ID_JSON": json.dumps(simulation_id),
                        "SERVICES_JSON": json.dumps(services),
                        "SCENARIO_CONFIG_JSON": json.dumps(scenario_config),
                    },
                )
            )
        finally:
            self._delete_job(namespace, traffic_job)
            self._delete_job(namespace, attack_job)
        return results

    def apply_defense(self, namespace: str, action_type: str, services: list[dict[str, Any]]) -> list[ResourceResult]:
        self._validate_namespace(namespace)
        self._validate_services(services)
        if self.is_dry_run:
            return [ResourceResult("Defense", action_type, "Applied", "Dry-run defense recorded.")]
        self._connect()
        if action_type == "NETWORK_POLICY":
            return [self._create_restrictive_network_policy(namespace)]
        if action_type in {"INPUT_VALIDATION", "ENDPOINT_RESTRICTION"}:
            return self._patch_service_defense_env(namespace, action_type, services)
        if action_type in {"RATE_LIMIT", "RESOURCE_LIMIT"}:
            return [ResourceResult("Defense", action_type, "Applied", "Handled by simulation runner limits.")]
        return [ResourceResult("Defense", action_type, "Skipped", "No Kubernetes implementation for this defense.")]

    def _dry_run_create(self, namespace: str, services: list[dict[str, Any]]) -> list[ResourceResult]:
        results = [
            ResourceResult("Namespace", namespace, "Created", "Dry-run Kubernetes namespace recorded."),
            ResourceResult("ResourceQuota", "pantheon-lab-quota", "Created", "Dry-run resource limits recorded."),
            ResourceResult("NetworkPolicy", "pantheon-namespace-isolation", "Created", "Dry-run namespace isolation recorded."),
        ]
        for service in services:
            results.append(ResourceResult("Deployment", service["name"], "Created", "Dry-run deployment recorded."))
            results.append(ResourceResult("Service", service["name"], "Created", "Dry-run service recorded."))
        return results

    def _dry_run_status(self, namespace: str, services: list[dict[str, Any]]) -> dict[str, Any]:
        service_statuses = [
            {
                "name": service["name"],
                "type": service.get("type", "service"),
                "status": "Running",
                "replicas": 1,
                "readyReplicas": 1,
                "availableReplicas": 1,
                "pods": [
                    {
                        "name": f"{service['name']}-dry-run",
                        "phase": "Running",
                        "readyContainers": 1,
                        "totalContainers": 1,
                        "restartCount": 0,
                    }
                ],
                "conditions": [],
            }
            for service in services
        ]
        return {
            "mode": self.mode,
            "namespace": {"name": namespace, "phase": "DryRun"},
            "summary": {
                "totalServices": len(service_statuses),
                "readyServices": len(service_statuses),
                "pendingServices": 0,
                "failedServices": 0,
                "allReady": bool(service_statuses),
            },
            "services": service_statuses,
            "jobs": [],
            "observedAt": self._now_iso(),
        }

    def _create_namespace(self, namespace: str) -> ResourceResult:
        from kubernetes import client
        from kubernetes.client import ApiException

        body = client.V1Namespace(
            metadata=client.V1ObjectMeta(
                name=namespace,
                labels={
                    "app.kubernetes.io/name": "pantheon",
                    "pantheon.io/managed": "true",
                    "pantheon.io/lab": namespace,
                },
            )
        )
        try:
            self._core.create_namespace(body)
            return ResourceResult("Namespace", namespace, "Created")
        except ApiException as exc:
            if exc.status == 409:
                return ResourceResult("Namespace", namespace, "Exists")
            raise KubernetesProvisioningError(f"Unable to create namespace {namespace}: {exc}") from exc

    def _create_resource_quota(self, namespace: str) -> ResourceResult:
        from kubernetes import client
        from kubernetes.client import ApiException

        body = client.V1ResourceQuota(
            metadata=client.V1ObjectMeta(name="pantheon-lab-quota"),
            spec=client.V1ResourceQuotaSpec(
                hard={
                    "pods": "12",
                    "requests.cpu": "800m",
                    "requests.memory": "1Gi",
                    "limits.cpu": "2",
                    "limits.memory": "2Gi",
                }
            ),
        )
        try:
            self._core.create_namespaced_resource_quota(namespace, body)
            return ResourceResult("ResourceQuota", "pantheon-lab-quota", "Created")
        except ApiException as exc:
            if exc.status == 409:
                return ResourceResult("ResourceQuota", "pantheon-lab-quota", "Exists")
            raise KubernetesProvisioningError(f"Unable to create resource quota in {namespace}: {exc}") from exc

    def _create_limit_range(self, namespace: str) -> ResourceResult:
        from kubernetes import client
        from kubernetes.client import ApiException

        body = client.V1LimitRange(
            metadata=client.V1ObjectMeta(name="pantheon-default-limits"),
            spec=client.V1LimitRangeSpec(
                limits=[
                    client.V1LimitRangeItem(
                        type="Container",
                        default={"cpu": "250m", "memory": "256Mi"},
                        default_request={"cpu": "50m", "memory": "64Mi"},
                    )
                ]
            ),
        )
        try:
            self._core.create_namespaced_limit_range(namespace, body)
            return ResourceResult("LimitRange", "pantheon-default-limits", "Created")
        except ApiException as exc:
            if exc.status == 409:
                return ResourceResult("LimitRange", "pantheon-default-limits", "Exists")
            raise KubernetesProvisioningError(f"Unable to create limit range in {namespace}: {exc}") from exc

    def _create_default_network_policy(self, namespace: str) -> ResourceResult:
        from kubernetes import client
        from kubernetes.client import ApiException

        same_namespace_peer = client.V1NetworkPolicyPeer(pod_selector=client.V1LabelSelector())
        body = client.V1NetworkPolicy(
            metadata=client.V1ObjectMeta(name="pantheon-namespace-isolation"),
            spec=client.V1NetworkPolicySpec(
                pod_selector=client.V1LabelSelector(),
                policy_types=["Ingress", "Egress"],
                ingress=[client.V1NetworkPolicyIngressRule(_from=[same_namespace_peer])],
                egress=[client.V1NetworkPolicyEgressRule(to=[same_namespace_peer])],
            ),
        )
        try:
            self._networking.create_namespaced_network_policy(namespace, body)
            return ResourceResult("NetworkPolicy", "pantheon-namespace-isolation", "Created")
        except ApiException as exc:
            if exc.status == 409:
                return ResourceResult("NetworkPolicy", "pantheon-namespace-isolation", "Exists")
            raise KubernetesProvisioningError(f"Unable to create network policy in {namespace}: {exc}") from exc

    def _create_restrictive_network_policy(self, namespace: str) -> ResourceResult:
        from kubernetes import client
        from kubernetes.client import ApiException

        allowed_peer = client.V1NetworkPolicyPeer(
            pod_selector=client.V1LabelSelector(match_labels={"pantheon.io/allow-admin-db": "true"})
        )
        body = client.V1NetworkPolicy(
            metadata=client.V1ObjectMeta(name="pantheon-restrict-admin-db"),
            spec=client.V1NetworkPolicySpec(
                pod_selector=client.V1LabelSelector(
                    match_expressions=[
                        client.V1LabelSelectorRequirement(
                            key="pantheon.io/service-type",
                            operator="In",
                            values=["api", "database", "cache"],
                        )
                    ]
                ),
                policy_types=["Ingress"],
                ingress=[client.V1NetworkPolicyIngressRule(_from=[allowed_peer])],
            ),
        )
        try:
            self._networking.create_namespaced_network_policy(namespace, body)
            return ResourceResult("NetworkPolicy", "pantheon-restrict-admin-db", "Created")
        except ApiException as exc:
            if exc.status == 409:
                return ResourceResult("NetworkPolicy", "pantheon-restrict-admin-db", "Exists")
            raise KubernetesProvisioningError(f"Unable to create restrictive network policy in {namespace}: {exc}") from exc

    def _create_deployment(self, namespace: str, service: dict[str, Any]) -> ResourceResult:
        from kubernetes import client
        from kubernetes.client import ApiException

        service_name = service["name"]
        service_type = service["type"]
        image, container_port, env = self._container_spec_for(service)
        labels = {
            "app.kubernetes.io/name": "pantheon",
            "pantheon.io/service": service_name,
            "pantheon.io/service-type": service_type,
        }
        body = client.V1Deployment(
            metadata=client.V1ObjectMeta(name=service_name, labels=labels),
            spec=client.V1DeploymentSpec(
                replicas=1,
                selector=client.V1LabelSelector(match_labels={"pantheon.io/service": service_name}),
                template=client.V1PodTemplateSpec(
                    metadata=client.V1ObjectMeta(labels=labels),
                    spec=client.V1PodSpec(
                        automount_service_account_token=False,
                        security_context=client.V1PodSecurityContext(
                            run_as_non_root=True,
                            seccomp_profile=client.V1SeccompProfile(type="RuntimeDefault"),
                        ),
                        containers=[
                            client.V1Container(
                                name=service_name,
                                image=image,
                                image_pull_policy=self.settings.runner_image_pull_policy,
                                ports=[client.V1ContainerPort(container_port=container_port)],
                                env=env,
                                resources=client.V1ResourceRequirements(
                                    requests={"cpu": "50m", "memory": "64Mi"},
                                    limits={"cpu": "250m", "memory": "256Mi"},
                                ),
                                security_context=client.V1SecurityContext(
                                    allow_privilege_escalation=False,
                                    capabilities=client.V1Capabilities(drop=["ALL"]),
                                ),
                            )
                        ],
                    ),
                ),
            ),
        )
        try:
            self._apps.create_namespaced_deployment(namespace, body)
            return ResourceResult("Deployment", service_name, "Created")
        except ApiException as exc:
            if exc.status == 409:
                return ResourceResult("Deployment", service_name, "Exists")
            raise KubernetesProvisioningError(f"Unable to create deployment {service_name}: {exc}") from exc

    def _create_service(self, namespace: str, service: dict[str, Any]) -> ResourceResult:
        from kubernetes import client
        from kubernetes.client import ApiException

        service_name = service["name"]
        _, container_port, _ = self._container_spec_for(service)
        service_port = int(service.get("port") or container_port)
        body = client.V1Service(
            metadata=client.V1ObjectMeta(
                name=service_name,
                labels={"app.kubernetes.io/name": "pantheon", "pantheon.io/service": service_name},
            ),
            spec=client.V1ServiceSpec(
                type="ClusterIP",
                selector={"pantheon.io/service": service_name},
                ports=[client.V1ServicePort(port=service_port, target_port=container_port)],
            ),
        )
        try:
            self._core.create_namespaced_service(namespace, body)
            return ResourceResult("Service", service_name, "Created")
        except ApiException as exc:
            if exc.status == 409:
                return ResourceResult("Service", service_name, "Exists")
            raise KubernetesProvisioningError(f"Unable to create service {service_name}: {exc}") from exc

    def _container_spec_for(self, service: dict[str, Any]) -> tuple[str, int, list[Any]]:
        from kubernetes import client

        service_type = service["type"]
        service_name = service["name"]
        container_port = int(service.get("container_port") or service.get("port") or 8080)
        image = service.get("image") or self.settings.service_image
        env = [
            client.V1EnvVar(name="SERVICE_NAME", value=service_name),
            client.V1EnvVar(name="SERVICE_TYPE", value=service_type),
            client.V1EnvVar(name="PORT", value=str(container_port)),
            client.V1EnvVar(name="PANTHEON_INPUT_VALIDATION", value="false"),
            client.V1EnvVar(name="PANTHEON_ADMIN_RESTRICTED", value="false"),
        ]
        if service_type == "target-app":
            env.extend(
                [
                    client.V1EnvVar(name="PANTHEON_TARGET_APP", value="true"),
                    client.V1EnvVar(name="PANTHEON_HEALTH_PATH", value=str(service.get("health_path") or "/")),
                ]
            )
        return (image, container_port, env)

    def _apply_target_manifest(self, namespace: str, app: dict[str, Any]) -> list[ResourceResult]:
        from kubernetes import client, utils
        from kubernetes.client import ApiException
        import yaml

        manifest = app.get("manifest")
        if not manifest:
            raise KubernetesProvisioningError("Kubernetes YAML import requires a manifest.")
        try:
            documents = [item for item in yaml.safe_load_all(manifest) if item]
        except yaml.YAMLError as exc:
            raise KubernetesProvisioningError(f"Unable to parse target application YAML: {exc}") from exc
        if not documents:
            raise KubernetesProvisioningError("Kubernetes YAML import did not contain any resources.")

        results: list[ResourceResult] = []
        api_client = client.ApiClient()
        for document in documents:
            self._validate_target_manifest_document(document, app["name"])
            document.setdefault("metadata", {})["namespace"] = namespace
            try:
                utils.create_from_dict(api_client, document, namespace=namespace)
                results.append(ResourceResult(document["kind"], document["metadata"]["name"], "Created"))
            except ApiException as exc:
                if exc.status == 409:
                    results.append(ResourceResult(document["kind"], document["metadata"]["name"], "Exists"))
                    continue
                raise KubernetesProvisioningError(f"Unable to apply target manifest resource: {exc}") from exc
        return results

    def _validate_target_manifest_document(self, document: dict[str, Any], service_name: str) -> None:
        kind = document.get("kind")
        metadata = document.get("metadata") or {}
        name = metadata.get("name")
        if kind not in {"Deployment", "Service"}:
            raise KubernetesProvisioningError("Target app YAML may only contain Deployment and Service resources.")
        if name != service_name:
            raise KubernetesProvisioningError("Target app YAML resource names must match the registered service name.")
        if metadata.get("namespace"):
            raise KubernetesProvisioningError("Target app YAML must not force a namespace; Pantheon injects the lab namespace.")
        spec = document.get("spec") or {}
        if kind == "Service" and spec.get("type") in {"NodePort", "LoadBalancer", "ExternalName"}:
            raise KubernetesProvisioningError("Target app services must remain internal ClusterIP services.")
        if kind == "Deployment":
            template = (spec.get("template") or {}).get("spec") or {}
            if template.get("hostNetwork") or template.get("hostPID") or template.get("hostIPC"):
                raise KubernetesProvisioningError("Target app pods cannot use host namespaces.")
            for volume in template.get("volumes") or []:
                if "hostPath" in volume:
                    raise KubernetesProvisioningError("Target app pods cannot mount hostPath volumes.")
            for container in template.get("containers") or []:
                security = container.get("securityContext") or {}
                if security.get("privileged"):
                    raise KubernetesProvisioningError("Target app containers cannot be privileged.")

    def _create_runner_job(
        self,
        *,
        namespace: str,
        job_name: str,
        command: list[str],
        env: dict[str, str],
    ) -> ResourceResult:
        from kubernetes import client
        from kubernetes.client import ApiException

        env_vars = [client.V1EnvVar(name=name, value=value) for name, value in env.items()]
        body = client.V1Job(
            metadata=client.V1ObjectMeta(
                name=job_name,
                labels={"app.kubernetes.io/name": "pantheon", "pantheon.io/job-type": "simulation-runner"},
            ),
            spec=client.V1JobSpec(
                backoff_limit=0,
                ttl_seconds_after_finished=120,
                template=client.V1PodTemplateSpec(
                    metadata=client.V1ObjectMeta(
                        labels={"app.kubernetes.io/name": "pantheon", "pantheon.io/job-type": "simulation-runner"}
                    ),
                    spec=client.V1PodSpec(
                        restart_policy="Never",
                        automount_service_account_token=False,
                        security_context=client.V1PodSecurityContext(
                            run_as_non_root=True,
                            seccomp_profile=client.V1SeccompProfile(type="RuntimeDefault"),
                        ),
                        containers=[
                            client.V1Container(
                                name="runner",
                                image=self.settings.runner_image,
                                image_pull_policy=self.settings.runner_image_pull_policy,
                                command=command,
                                env=env_vars,
                                resources=client.V1ResourceRequirements(
                                    requests={"cpu": "50m", "memory": "64Mi"},
                                    limits={"cpu": "250m", "memory": "256Mi"},
                                ),
                                security_context=client.V1SecurityContext(
                                    allow_privilege_escalation=False,
                                    capabilities=client.V1Capabilities(drop=["ALL"]),
                                ),
                            )
                        ],
                    ),
                ),
            ),
        )
        try:
            self._batch.create_namespaced_job(namespace, body)
            return ResourceResult("Job", job_name, "Created")
        except ApiException as exc:
            raise KubernetesProvisioningError(f"Unable to create job {job_name}: {exc}") from exc

    def _run_observed_job(
        self,
        *,
        namespace: str,
        simulation_id: str,
        job_name: str,
        command: list[str],
        env: dict[str, str],
    ) -> list[dict[str, Any]]:
        records = [
            self._observed_log_record(
                simulation_id=simulation_id,
                job_name=job_name,
                event_type="kubernetes_job_starting",
                raw={"command": command, "env_keys": sorted(env)},
            )
        ]
        self._create_runner_job(namespace=namespace, job_name=job_name, command=command, env=env)
        records.append(
            self._observed_log_record(
                simulation_id=simulation_id,
                job_name=job_name,
                event_type="kubernetes_job_created",
                raw={"namespace": namespace},
            )
        )
        records.extend(self._wait_for_job(namespace, job_name, simulation_id))
        records.extend(self._read_job_observed_logs(namespace, job_name, simulation_id))
        return records

    def _wait_for_job(self, namespace: str, job_name: str, simulation_id: str) -> list[dict[str, Any]]:
        deadline = time.time() + self.settings.job_timeout_seconds
        last_phase: str | None = None
        records: list[dict[str, Any]] = []
        while time.time() < deadline:
            job = self._batch.read_namespaced_job(job_name, namespace)
            phase = self._job_phase(job)
            if phase != last_phase:
                records.append(
                    self._observed_log_record(
                        simulation_id=simulation_id,
                        job_name=job_name,
                        event_type=f"kubernetes_job_{phase.lower()}",
                        severity="Warning" if phase in {"Failed", "Pending"} else "Info",
                        raw=self._job_snapshot(job),
                    )
                )
                last_phase = phase
            status = job.status
            if status.succeeded and status.succeeded >= 1:
                records.append(
                    self._observed_log_record(
                        simulation_id=simulation_id,
                        job_name=job_name,
                        event_type="kubernetes_job_succeeded",
                        raw=self._job_snapshot(job),
                    )
                )
                return records
            if status.failed and status.failed >= 1:
                records.append(
                    self._observed_log_record(
                        simulation_id=simulation_id,
                        job_name=job_name,
                        event_type="kubernetes_job_failed",
                        severity="Critical",
                        raw=self._job_snapshot(job),
                    )
                )
                raise KubernetesProvisioningError(f"Simulation job failed: {job_name}")
            time.sleep(1)
        records.append(
            self._observed_log_record(
                simulation_id=simulation_id,
                job_name=job_name,
                event_type="kubernetes_job_timeout",
                severity="Critical",
                raw={"timeout_seconds": self.settings.job_timeout_seconds},
            )
        )
        raise KubernetesProvisioningError(f"Simulation job timed out: {job_name}")

    def _read_job_observed_logs(self, namespace: str, job_name: str, simulation_id: str) -> list[dict[str, Any]]:
        pods = self._core.list_namespaced_pod(
            namespace,
            label_selector=f"job-name={job_name}",
        ).items
        records: list[dict[str, Any]] = []
        for pod in pods:
            pod_name = pod.metadata.name
            records.append(
                self._observed_log_record(
                    simulation_id=simulation_id,
                    job_name=job_name,
                    event_type="kubernetes_pod_observed",
                    raw={"pod": self._pod_snapshot(pod)},
                    target=pod_name,
                )
            )
            try:
                logs = self._core.read_namespaced_pod_log(pod_name, namespace)
            except Exception as exc:  # pragma: no cover - depends on cluster client
                records.append(
                    self._observed_log_record(
                        simulation_id=simulation_id,
                        job_name=job_name,
                        event_type="kubernetes_pod_log_unavailable",
                        severity="Warning",
                        raw={"pod_name": pod_name, "error": str(exc)},
                        target=pod_name,
                    )
                )
                continue
            for line in logs.splitlines():
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    records.append(
                        self._observed_log_record(
                            simulation_id=simulation_id,
                            job_name=job_name,
                            event_type="container_log_line",
                            raw={"pod_name": pod_name, "line": line},
                            target=pod_name,
                        )
                    )
                    continue
                if self._is_runner_log_record(record):
                    raw_log = record.get("raw_log_json") if isinstance(record.get("raw_log_json"), dict) else {}
                    record["raw_log_json"] = {
                        **raw_log,
                        "observed_source": "kubernetes_job_log",
                        "job_name": job_name,
                        "pod_name": pod_name,
                    }
                    records.append(record)
                else:
                    records.append(
                        self._observed_log_record(
                            simulation_id=simulation_id,
                            job_name=job_name,
                            event_type="container_json_log_line",
                            raw={"pod_name": pod_name, "record": record},
                            target=pod_name,
                        )
                    )
        return records

    def _deployment_service_status(self, namespace: str, service: dict[str, Any]) -> dict[str, Any]:
        from kubernetes.client import ApiException

        service_name = service["name"]
        try:
            deployment = self._apps.read_namespaced_deployment(service_name, namespace)
        except ApiException as exc:
            if exc.status == 404:
                return {
                    "name": service_name,
                    "type": service.get("type", "service"),
                    "status": "Missing",
                    "replicas": 0,
                    "readyReplicas": 0,
                    "availableReplicas": 0,
                    "pods": [],
                    "conditions": [],
                    "message": "Deployment was not found in the lab namespace.",
                }
            raise
        status = deployment.status
        replicas = int(status.replicas or 0)
        ready = int(status.ready_replicas or 0)
        available = int(status.available_replicas or 0)
        conditions = self._conditions_snapshot(status.conditions or [])
        failed = any(item["type"] == "ReplicaFailure" and item["status"] == "True" for item in conditions)
        if failed:
            phase = "Failed"
        elif replicas == 0:
            phase = "Stopped"
        elif replicas > 0 and ready >= replicas and available >= 1:
            phase = "Running"
        else:
            phase = "Pending"
        pods = self._pods_for_selector(namespace, f"pantheon.io/service={service_name}")
        return {
            "name": service_name,
            "type": service.get("type", "service"),
            "status": phase,
            "replicas": replicas,
            "readyReplicas": ready,
            "availableReplicas": available,
            "pods": [self._pod_snapshot(pod) for pod in pods],
            "conditions": conditions,
        }

    def _pods_for_selector(self, namespace: str, selector: str) -> list[Any]:
        try:
            return self._core.list_namespaced_pod(namespace, label_selector=selector).items
        except Exception:  # pragma: no cover - depends on cluster client
            return []

    def _list_runner_jobs(self, namespace: str) -> list[dict[str, Any]]:
        try:
            jobs = self._batch.list_namespaced_job(
                namespace,
                label_selector="pantheon.io/job-type=simulation-runner",
            ).items
        except Exception:  # pragma: no cover - depends on cluster client
            return []
        return [self._job_snapshot(job) for job in jobs]

    def _job_phase(self, job: Any) -> str:
        status = job.status
        if status.failed and status.failed >= 1:
            return "Failed"
        if status.succeeded and status.succeeded >= 1:
            return "Succeeded"
        if status.active and status.active >= 1:
            return "Running"
        return "Pending"

    def _job_snapshot(self, job: Any) -> dict[str, Any]:
        status = job.status
        return {
            "name": job.metadata.name,
            "phase": self._job_phase(job),
            "active": int(status.active or 0),
            "succeeded": int(status.succeeded or 0),
            "failed": int(status.failed or 0),
            "startTime": status.start_time.isoformat() if status.start_time else None,
            "completionTime": status.completion_time.isoformat() if status.completion_time else None,
            "conditions": self._conditions_snapshot(status.conditions or []),
        }

    def _pod_snapshot(self, pod: Any) -> dict[str, Any]:
        container_statuses = pod.status.container_statuses or []
        ready = sum(1 for item in container_statuses if item.ready)
        restarts = sum(int(item.restart_count or 0) for item in container_statuses)
        return {
            "name": pod.metadata.name,
            "phase": pod.status.phase,
            "readyContainers": ready,
            "totalContainers": len(container_statuses),
            "restartCount": restarts,
            "nodeName": pod.spec.node_name,
            "reason": pod.status.reason,
            "message": pod.status.message,
        }

    def _conditions_snapshot(self, conditions: list[Any]) -> list[dict[str, Any]]:
        return [
            {
                "type": condition.type,
                "status": condition.status,
                "reason": condition.reason,
                "message": condition.message,
            }
            for condition in conditions
        ]

    def _observed_log_record(
        self,
        *,
        simulation_id: str,
        job_name: str,
        event_type: str,
        raw: dict[str, Any],
        severity: str = "Info",
        source: str = "kubernetes",
        target: str | None = None,
    ) -> dict[str, Any]:
        return {
            "timestamp": self._now_iso(),
            "source_service": source,
            "target_service": target or job_name,
            "method": "OBSERVE",
            "endpoint": f"k8s/jobs/{job_name}",
            "status_code": 0,
            "request_count": 1,
            "payload_category": "kubernetes_observation",
            "event_type": event_type,
            "severity": severity,
            "is_attack_simulation": False,
            "raw_log_json": {
                "observed_source": "kubernetes_api",
                "simulation_id": simulation_id,
                "job_name": job_name,
                **raw,
            },
        }

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def _delete_job(self, namespace: str, job_name: str) -> None:
        from kubernetes.client import ApiException

        try:
            self._batch.delete_namespaced_job(job_name, namespace, propagation_policy="Background")
        except ApiException as exc:
            if exc.status != 404:
                raise

    def _patch_service_defense_env(
        self,
        namespace: str,
        action_type: str,
        services: list[dict[str, Any]],
    ) -> list[ResourceResult]:
        env_name = "PANTHEON_INPUT_VALIDATION" if action_type == "INPUT_VALIDATION" else "PANTHEON_ADMIN_RESTRICTED"
        target_types = {"api", "frontend"}
        results: list[ResourceResult] = []
        for service in services:
            if service["type"] not in target_types:
                continue
            deployment = self._apps.read_namespaced_deployment(service["name"], namespace)
            container = deployment.spec.template.spec.containers[0]
            env = container.env or []
            for item in env:
                if item.name == env_name:
                    item.value = "true"
                    break
            else:
                from kubernetes import client

                env.append(client.V1EnvVar(name=env_name, value="true"))
            container.env = env
            self._apps.patch_namespaced_deployment(service["name"], namespace, deployment)
            results.append(ResourceResult("Deployment", service["name"], "Patched", f"{env_name}=true"))
        return results

    def _validate_namespace(self, namespace: str) -> None:
        if not namespace.startswith(f"{self.settings.namespace_prefix}-"):
            raise KubernetesProvisioningError("Lab namespace must use the configured Pantheon prefix.")
        if any(part in namespace for part in ("..", "/", "\\", ":", "*", "?")):
            raise KubernetesProvisioningError("Invalid namespace name.")

    def _validate_services(self, services: list[dict[str, Any]]) -> None:
        if not services:
            raise KubernetesProvisioningError("A lab must define at least one service.")
        for service in services:
            name = str(service.get("name", ""))
            if not name or any(part in name for part in ("..", "/", "\\", ":", "*", "?")):
                raise KubernetesProvisioningError(f"Invalid service name: {name}")
            if service.get("type") == "target-app" and service.get("import_type") in {"docker-image", "local-service"}:
                if not service.get("image") and service.get("import_type") != "local-service":
                    raise KubernetesProvisioningError(f"Target app {name} requires an image.")
                if not self.is_dry_run and not service.get("image") and service.get("import_type") == "local-service":
                    raise KubernetesProvisioningError(
                        f"Target app {name} is a local-service target and must be containerized before real deployment."
                    )

    def _validate_scenario_targets(self, scenario_config: dict[str, Any], services: list[dict[str, Any]]) -> None:
        service_names = {service["name"] for service in services}
        for step in scenario_config.get("steps", []):
            target = str(step.get("target", ""))
            if target not in service_names:
                raise KubernetesProvisioningError(f"Scenario target is outside the lab service list: {target}")

    def _is_runner_log_record(self, record: dict[str, Any]) -> bool:
        required = {
            "timestamp",
            "source_service",
            "target_service",
            "method",
            "endpoint",
            "status_code",
            "payload_category",
            "event_type",
            "is_attack_simulation",
        }
        return required.issubset(record)
