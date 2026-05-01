from __future__ import annotations

import json
import time
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
            self._create_runner_job(
                namespace=namespace,
                job_name=traffic_job,
                command=["python", "traffic_generator.py"],
                env={
                    "SIMULATION_ID_JSON": json.dumps(simulation_id),
                    "SERVICES_JSON": json.dumps(services),
                    "NORMAL_TRAFFIC_JSON": json.dumps(normal_traffic),
                },
            )
            self._wait_for_job(namespace, traffic_job)
            results.extend(self._read_job_json_logs(namespace, traffic_job))

            self._create_runner_job(
                namespace=namespace,
                job_name=attack_job,
                command=["python", "runner.py"],
                env={
                    "SIMULATION_ID_JSON": json.dumps(simulation_id),
                    "SERVICES_JSON": json.dumps(services),
                    "SCENARIO_CONFIG_JSON": json.dumps(scenario_config),
                },
            )
            self._wait_for_job(namespace, attack_job)
            results.extend(self._read_job_json_logs(namespace, attack_job))
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
        return (
            self.settings.service_image,
            8080,
            [
                client.V1EnvVar(name="SERVICE_NAME", value=service_name),
                client.V1EnvVar(name="SERVICE_TYPE", value=service_type),
                client.V1EnvVar(name="PORT", value="8080"),
                client.V1EnvVar(name="PANTHEON_INPUT_VALIDATION", value="false"),
                client.V1EnvVar(name="PANTHEON_ADMIN_RESTRICTED", value="false"),
            ],
        )

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

    def _wait_for_job(self, namespace: str, job_name: str) -> None:
        deadline = time.time() + self.settings.job_timeout_seconds
        while time.time() < deadline:
            job = self._batch.read_namespaced_job(job_name, namespace)
            status = job.status
            if status.succeeded and status.succeeded >= 1:
                return
            if status.failed and status.failed >= 1:
                raise KubernetesProvisioningError(f"Simulation job failed: {job_name}")
            time.sleep(1)
        raise KubernetesProvisioningError(f"Simulation job timed out: {job_name}")

    def _read_job_json_logs(self, namespace: str, job_name: str) -> list[dict[str, Any]]:
        pods = self._core.list_namespaced_pod(
            namespace,
            label_selector=f"job-name={job_name}",
        ).items
        records: list[dict[str, Any]] = []
        for pod in pods:
            logs = self._core.read_namespaced_pod_log(pod.metadata.name, namespace)
            for line in logs.splitlines():
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if self._is_runner_log_record(record):
                    records.append(record)
        return records

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
