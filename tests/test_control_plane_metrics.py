from src.ivp import api
from src.ivp.api_models import RegisterWorkerRequest, SubmitJobRequest
from src.ivp.heartbeat import HeartbeatMonitor
from src.ivp.inventory import DeviceInventory
from src.ivp.models import ArtifactSpec, Heartbeat
from src.ivp.store import SQLiteStore


def reset_api_state(monkeypatch, tmp_path):
    inventory = DeviceInventory()
    monkeypatch.setattr(api, "inventory", inventory)
    monkeypatch.setattr(api, "heartbeat_monitor", HeartbeatMonitor(inventory))
    monkeypatch.setattr(api, "store", SQLiteStore(tmp_path / "ivp.sqlite3"))
    monkeypatch.setattr(api, "REPORT_DIR", tmp_path / "reports")


def test_metrics_endpoint_empty_database(monkeypatch, tmp_path):
    reset_api_state(monkeypatch, tmp_path)

    response = api.prometheus_metrics()
    body = response.body.decode("utf-8")

    assert response.status_code == 200
    assert "text/plain; version=0.0.4" in response.headers["content-type"]
    assert "# HELP ivp_jobs_current Number of IVP jobs by status." in body
    assert "# TYPE ivp_jobs_current gauge" in body
    assert "# TYPE ivp_devices_current gauge" in body
    assert "# TYPE ivp_heartbeats_total counter" in body
    assert "# TYPE ivp_events_total counter" in body
    assert "# TYPE ivp_validation_results_total counter" in body


def test_metrics_endpoint_reports_devices_heartbeats_and_completed_jobs(
    monkeypatch,
    tmp_path,
):
    reset_api_state(monkeypatch, tmp_path)

    api.register_worker(
        RegisterWorkerRequest(
            device_id="mock-asic-worker-1",
            backend="mock_gpu",
            labels={"accelerator": "mock_asic"},
            resource_capacity={"slots": 4},
        )
    )
    api.heartbeat(
        Heartbeat(
            device_id="mock-asic-worker-1",
            backend="mock_gpu",
            healthy=True,
            utilization=0.35,
            last_latency_ms=2.2,
        )
    )
    submit = api.submit_job(
        SubmitJobRequest(
            job_id="metrics-job-001",
            max_retries=0,
            artifact=ArtifactSpec(
                artifact_id="cv_execution_plan_metrics",
                artifact_type="execution_plan",
                source_repo="ml-graph-compiler-runtime",
                artifact_path="../ml-graph-compiler-runtime/trace/cv_execution_plan_v2.json",
                required_backends=["mock_gpu"],
                latency_budget_ms=5.0,
                correctness_required=True,
            ),
        )
    )

    assert submit["status"] == "completed"

    response = api.prometheus_metrics()
    body = response.body.decode("utf-8")

    assert response.status_code == 200
    assert 'ivp_devices_current{status="healthy",backend="mock_gpu"} 1' in body
    assert 'ivp_heartbeats_total{backend="mock_gpu",healthy="true"} 1' in body
    assert 'ivp_jobs_current{status="passed"} 1' in body
    assert 'ivp_validation_results_total{result="pass"} 1' in body
    assert 'ivp_events_total{event_type="job.submitted"} 1' in body
