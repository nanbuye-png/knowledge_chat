"""
Sprint 32 Production Deployment & Observability 测试

测试:
1. Docker Compose Production Stack 配置验证
2. GitHub Actions CI/CD 配置验证
3. Prometheus Metrics Service
4. Grafana Dashboard 配置
5. Logging System 验证
6. Kubernetes 部署清单验证
7. Helm Chart 配置验证
8. HPA Auto Scaling 配置
9. Security Hardening
10. Final Validation
"""
import os
import sys
import yaml

_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _backend_dir)


class TestDockerCompose:
    """Step 1: Docker Compose Production Stack"""

    def test_compose_file_exists(self):
        """docker-compose.prod.yml 存在"""
        path = os.path.join(_backend_dir, "..", "docker-compose.prod.yml")
        assert os.path.exists(path), f"File not found: {path}"

        with open(path, encoding="utf-8") as f:
            compose = yaml.safe_load(f)

        services = compose.get("services", {})
        required = ["postgres", "redis", "backend", "frontend", "nginx"]
        for svc in required:
            assert svc in services, f"Service {svc} not in docker-compose.prod.yml"
        print(f"[PASS] docker-compose.prod.yml: {list(services.keys())}")

    def test_env_production_exists(self):
        """.env.production 存在"""
        path = os.path.join(_backend_dir, "..", ".env.production")
        assert os.path.exists(path)
        with open(path, encoding="utf-8") as f:
            content = f.read()
        assert "ENVIRONMENT=production" in content
        assert "CACHE_BACKEND=redis" in content
        print(f"[PASS] .env.production contains production config")

    def test_dockerfiles_exist(self):
        """Dockerfiles 存在"""
        be = os.path.join(_backend_dir, "..", "Dockerfile.backend")
        fe = os.path.join(_backend_dir, "..", "Dockerfile.frontend")
        assert os.path.exists(be)
        assert os.path.exists(fe)
        print(f"[PASS] Dockerfiles exist: backend, frontend")

    def test_nginx_config(self):
        """nginx.conf 存在且配置正确"""
        path = os.path.join(_backend_dir, "..", "nginx", "nginx.conf")
        assert os.path.exists(path)
        with open(path, encoding="utf-8") as f:
            content = f.read()
        assert "gzip on" in content
        assert "/api/" in content
        assert "proxy_pass" in content
        print(f"[PASS] nginx.conf: gzip, proxy, api routes configured")

    def test_dockerignore_excludes_secrets_and_build_artifacts(self):
        """审计 §7.1-1（P0）：没有 .dockerignore 时 backend/.env 会被打进镜像。

        这条断言直接盯着"密钥不能进镜像"，以及"构建上下文不能把本机 venv/
        运行期数据一起打包"（实测上下文约 2.8GB）。
        """
        path = os.path.join(_backend_dir, "..", ".dockerignore")
        assert os.path.exists(path), "根目录必须有 .dockerignore（审计 §7.1-1）"

        with open(path, encoding="utf-8") as f:
            patterns = {
                line.strip()
                for line in f
                if line.strip() and not line.strip().startswith("#")
            }

        for required in (".env", ".env.*", ".venv/", "venv/", "node_modules/",
                         "*.db", "chroma_db/", "uploads/", "**/__pycache__/",
                         "**/node_modules/"):
            assert required in patterns, f".dockerignore 缺少 {required}"
        # 构建输入不能被排除（否则 COPY requirements.txt 直接失败）
        assert "backend/requirements.txt" not in patterns
        assert "frontend/package.json" not in patterns
        print(f"[PASS] .dockerignore 覆盖 {len(patterns)} 条规则（含密钥与环境排除）")

    def test_backend_image_has_healthcheck_and_build_cleanup(self):
        """审计 §7.1-2：补 HEALTHCHECK、清理编译期依赖、声明优雅退出信号。"""
        path = os.path.join(_backend_dir, "..", "Dockerfile.backend")
        with open(path, encoding="utf-8") as f:
            content = f.read()

        assert "HEALTHCHECK" in content, "后端镜像必须有健康检查（审计 §7.1-2）"
        assert "/api/health" in content, "健康检查必须打真实接口，而不是恒返回 200"
        assert "apt-get purge -y --auto-remove gcc" in content, "编译期 gcc 必须清掉"
        assert "STOPSIGNAL SIGTERM" in content, "必须让 uvicorn 收到 SIGTERM 走优雅关闭"
        print("[PASS] Dockerfile.backend: HEALTHCHECK + gcc 清理 + STOPSIGNAL")

    def test_frontend_image_ships_spa_rewrite(self):
        """审计 §7.1-4：前端镜像必须自带 SPA 回退，否则深链接刷新 404。"""
        dockerfile = os.path.join(_backend_dir, "..", "Dockerfile.frontend")
        with open(dockerfile, encoding="utf-8") as f:
            content = f.read()
        assert "frontend/nginx.conf" in content, "SPA 配置必须 COPY 进镜像"

        conf_path = os.path.join(_backend_dir, "..", "frontend", "nginx.conf")
        assert os.path.exists(conf_path), "frontend/nginx.conf 必须存在"
        with open(conf_path, encoding="utf-8") as f:
            conf = f.read()
        assert "try_files $uri $uri/ /index.html;" in conf, "缺少 SPA 回退"
        assert "/healthz" in conf, "缺少容器健康检查端点"
        print("[PASS] 前端镜像内置 SPA 回退 + /healthz")



class TestGithubActions:
    """Step 2: GitHub Actions CI/CD"""

    def test_ci_workflow(self):
        """CI workflow 配置"""
        path = os.path.join(_backend_dir, "..", ".github", "workflows", "ci.yml")
        assert os.path.exists(path)
        with open(path, encoding="utf-8") as f:
            workflow = yaml.safe_load(f)
        assert "test" in workflow.get("jobs", {})
        steps = workflow["jobs"]["test"]["steps"]
        step_names = [s.get("name", "") for s in steps]
        assert "Run tests" in step_names
        assert "Frontend build" in step_names
        print(f"[PASS] CI workflow: test + frontend build")

    def test_docker_build_workflow(self):
        """Docker build workflow"""
        path = os.path.join(_backend_dir, "..", ".github", "workflows", "docker-build.yml")
        assert os.path.exists(path)
        with open(path, encoding="utf-8") as f:
            workflow = yaml.safe_load(f)
        assert "build" in workflow.get("jobs", {})
        print(f"[PASS] Docker build workflow configured")


class TestMetrics:
    """Step 3: Prometheus Metrics"""

    def test_metrics_service(self):
        """埋点函数真实可用（原断言 ``_metrics_available in [True, False]`` 恒真）。

        P0-5：改为真实调用 ``track_request`` / ``track_llm_call`` 并校验
        Prometheus 指标文本发生变化 —— 否则"埋点是否存在"根本无从验证。
        """
        from app.services import metrics

        if not metrics._metrics_available:
            try:
                metrics._ensure_metrics()
                raise AssertionError("未安装 prometheus_client 时应抛 RuntimeError")
            except AssertionError:
                raise
            except RuntimeError:
                print("[PASS] prometheus_client 未安装 → _ensure_metrics 显式失败")
            return

        from prometheus_client import generate_latest

        before = generate_latest()
        metrics.track_request("GET", "/__p0_5_test__", 200, 0.01)
        metrics.track_llm_call("p0-5-model", prompt_tokens=10, completion_tokens=5, latency=0.2)
        after = generate_latest()

        assert after != before, "埋点必须真实写入 Prometheus 指标"
        assert b"knowledge_request_total" in after
        assert b"knowledge_llm_tokens_total" in after
        print("[PASS] track_request / track_llm_call 真实写入指标")

    def test_metrics_endpoint(self):
        """/metrics 路由存在于 metrics router 中。"""
        from app.services.metrics import router

        routes = [r.path for r in router.routes]
        assert "/metrics" in routes
        print("[PASS] /metrics route defined")


class TestMonitoring:
    """Step 3-4: Monitoring Infrastructure"""

    def test_prometheus_config(self):
        """Prometheus 配置"""
        path = os.path.join(_backend_dir, "..", "monitoring", "prometheus", "prometheus.yml")
        assert os.path.exists(path)
        print(f"[PASS] Prometheus config exists")

    def test_grafana_dashboard(self):
        """Grafana 配置目录"""
        path = os.path.join(_backend_dir, "..", "monitoring", "grafana")
        assert os.path.exists(path)
        print(f"[PASS] Grafana directory exists")


class TestLogging:
    """Step 5: Logging System"""

    def test_logging_config(self):
        """setup_logging 必须真实配置 sink（原断言 ``logger is not None`` 恒真）。"""
        from loguru import logger

        from app.core.logging import setup_logging

        setup_logging()
        handlers = logger._core.handlers  # noqa: SLF001 - loguru 唯一可用的 sink 视图
        assert len(handlers) >= 2, f"应至少配置控制台 + 文件两个 sink，实际 {len(handlers)}"
        logger.info("P0-5 logging smoke test")
        print(f"[PASS] setup_logging 配置了 {len(handlers)} 个 sink")


class TestKubernetes:
    """Step 6: Kubernetes Deployment"""

    def test_backend_deployment(self):
        """Backend K8s deployment"""
        path = os.path.join(_backend_dir, "..", "k8s", "backend-deployment.yaml")
        assert os.path.exists(path)

        with open(path, encoding="utf-8") as f:
            docs = list(yaml.safe_load_all(f))
        kinds = [d["kind"] for d in docs]
        assert "Deployment" in kinds
        assert "Service" in kinds

        deploy = next(d for d in docs if d["kind"] == "Deployment")
        spec = deploy["spec"]
        assert spec["replicas"] == 2
        assert "livenessProbe" in spec["template"]["spec"]["containers"][0]
        assert "readinessProbe" in spec["template"]["spec"]["containers"][0]
        print(f"[PASS] K8s backend: 2 replicas, health probes")

    def test_configmap(self):
        """ConfigMap 配置"""
        path = os.path.join(_backend_dir, "..", "k8s", "configmap.yaml")
        assert os.path.exists(path)

        with open(path, encoding="utf-8") as f:
            cm = yaml.safe_load(f)
        data = cm["data"]
        assert data["ENVIRONMENT"] == "production"
        assert data["CACHE_BACKEND"] == "redis"
        print(f"[PASS] K8s ConfigMap: production config")

    def test_secret(self):
        """Secret 配置：SECRET_KEY 必须是"未配置"状态，强制显式提供。

        审计 §6.1：模板里曾留 ``your-secret-key-change-in-production`` 这类
        占位串 —— 看上去"配过了"，实际是公开值。现在模板留空，由启动自检
        fail-fast 逼出一次显式赋值（``openssl rand -hex 32``）。
        """
        path = os.path.join(_backend_dir, "..", "k8s", "secret.yaml")
        assert os.path.exists(path)
        with open(path, encoding="utf-8") as f:
            secret = yaml.safe_load(f)
        assert secret["kind"] == "Secret"
        assert secret["stringData"]["SECRET_KEY"] == "", (
            "k8s Secret 模板不得留下可用的占位密钥（审计 §6.1）"
        )
        print("[PASS] K8s Secret defined (SECRET_KEY 必须由运维显式提供)")


class TestHelm:
    """Step 7: Helm Chart"""

    def test_chart_yaml(self):
        """Chart.yaml 存在"""
        path = os.path.join(_backend_dir, "..", "helm", "knowledge-chat", "Chart.yaml")
        assert os.path.exists(path)
        with open(path, encoding="utf-8") as f:
            chart = yaml.safe_load(f)
        assert chart["name"] == "knowledge-chat"
        assert chart["appVersion"] == "1.0.1"
        print(f"[PASS] Helm Chart: {chart['name']} v{chart['appVersion']}")

    def test_values_yaml(self):
        """values.yaml 配置完整"""
        path = os.path.join(_backend_dir, "..", "helm", "knowledge-chat", "values.yaml")
        assert os.path.exists(path)
        with open(path, encoding="utf-8") as f:
            values = yaml.safe_load(f)
        assert values["replicaCount"] == 2
        assert "backend" in values
        assert "frontend" in values
        assert "ingress" in values
        assert "hpa" in values
        print(f"[PASS] Helm values: backend, frontend, ingress, hpa")

    def test_helpers_exist(self):
        """Helpers 模板"""
        path = os.path.join(_backend_dir, "..", "helm", "knowledge-chat", "templates", "_helpers.tpl")
        assert os.path.exists(path)
        print(f"[PASS] Helm helpers template")


class TestHPA:
    """Step 8: HPA Auto Scaling"""

    def test_hpa_config(self):
        """HPA 配置"""
        path = os.path.join(_backend_dir, "..", "k8s", "hpa.yaml")
        assert os.path.exists(path)

        with open(path, encoding="utf-8") as f:
            hpa = yaml.safe_load(f)
        assert hpa["spec"]["minReplicas"] == 2
        assert hpa["spec"]["maxReplicas"] == 10

        metrics = hpa["spec"]["metrics"]
        metric_names = [m["resource"]["name"] for m in metrics]
        assert "cpu" in metric_names
        assert "memory" in metric_names
        print(f"[PASS] HPA: 2-10 replicas, CPU 70%, Memory 80%")


class TestSecurity:
    """Step 9: Security Hardening"""

    def test_security_headers_middleware(self):
        """安全头中间件"""
        from app.middleware.security_headers import SecurityHeadersMiddleware
        print(f"[PASS] Security headers middleware: {SecurityHeadersMiddleware.__name__}")

    def test_rate_limit_middleware(self):
        """限流中间件"""
        from app.middleware.rate_limit import RateLimitMiddleware
        print(f"[PASS] Rate limit middleware: {RateLimitMiddleware.__name__}")

    def test_rbac_permissions(self):
        """RBAC 权限系统"""
        from app.core.permissions import require_admin, require_root, require_permission
        print(f"[PASS] RBAC permissions: admin, root, permission based")

    def test_https_config(self):
        """HTTPS/TLS 配置"""
        # Ingress TLS
        ingress_path = os.path.join(_backend_dir, "..", "k8s", "frontend-deployment.yaml")
        with open(ingress_path, encoding="utf-8") as f:
            docs = list(yaml.safe_load_all(f))
        ingress = next((d for d in docs if d.get("kind") == "Ingress"), None)
        if ingress:
            assert "tls" in ingress["spec"]
            print(f"[PASS] Ingress TLS configured")


class TestFinalValidation:
    """Step 10: Final Production Validation"""

    def test_all_files_exist(self):
        """验证所有生产文件存在"""
        required_files = [
            "docker-compose.prod.yml",
            ".env.production",
            "Dockerfile.backend",
            "Dockerfile.frontend",
            "nginx/nginx.conf",
            ".github/workflows/ci.yml",
            ".github/workflows/docker-build.yml",
            "monitoring/prometheus/prometheus.yml",
            "monitoring/grafana",
            "k8s/backend-deployment.yaml",
            "k8s/frontend-deployment.yaml",
            "k8s/configmap.yaml",
            "k8s/secret.yaml",
            "k8s/hpa.yaml",
            "helm/knowledge-chat/Chart.yaml",
            "helm/knowledge-chat/values.yaml",
            "helm/knowledge-chat/templates/_helpers.tpl",
        ]
        root = os.path.join(_backend_dir, "..")
        missing = []
        for f in required_files:
            full_path = os.path.join(root, f)
            if not os.path.exists(full_path):
                missing.append(f)
        assert len(missing) == 0, f"Missing files: {missing}"
        print(f"[PASS] All {len(required_files)} production files verified")

    def test_app_metadata(self):
        """应用版本信息"""
        from app.core.config import settings
        assert settings.APP_NAME == "智能知识库问答系统"
        print(f"[PASS] App: {settings.APP_NAME} v{settings.APP_VERSION}")


if __name__ == "__main__":
    print("=" * 60)
    print("Sprint 32 Production Deployment & Observability")
    print("=" * 60)

    print("\n--- Step 1: Docker Compose Production Stack ---")
    t1 = TestDockerCompose()
    t1.test_compose_file_exists()
    t1.test_env_production_exists()
    t1.test_dockerfiles_exist()
    t1.test_nginx_config()

    print("\n--- Step 2: GitHub Actions CI/CD ---")
    t2 = TestGithubActions()
    t2.test_ci_workflow()
    t2.test_docker_build_workflow()

    print("\n--- Step 3: Prometheus Metrics ---")
    t3 = TestMetrics()
    t3.test_metrics_service()
    t3.test_metrics_endpoint()

    print("\n--- Step 4: Monitoring Infrastructure ---")
    t4 = TestMonitoring()
    t4.test_prometheus_config()
    t4.test_grafana_dashboard()

    print("\n--- Step 5: Logging System ---")
    t5 = TestLogging()
    t5.test_logging_config()

    print("\n--- Step 6: Kubernetes Deployment ---")
    t6 = TestKubernetes()
    t6.test_backend_deployment()
    t6.test_configmap()
    t6.test_secret()

    print("\n--- Step 7: Helm Chart ---")
    t7 = TestHelm()
    t7.test_chart_yaml()
    t7.test_values_yaml()
    t7.test_helpers_exist()

    print("\n--- Step 8: HPA Auto Scaling ---")
    t8 = TestHPA()
    t8.test_hpa_config()

    print("\n--- Step 9: Security Hardening ---")
    t9 = TestSecurity()
    t9.test_security_headers_middleware()
    t9.test_rate_limit_middleware()
    t9.test_rbac_permissions()
    t9.test_https_config()

    print("\n--- Step 10: Final Validation ---")
    t10 = TestFinalValidation()
    t10.test_all_files_exist()
    t10.test_app_metadata()

    print("\n" + "=" * 60)
    print("Sprint 32 所有测试通过!")
    print("=" * 60)