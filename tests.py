from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.cache import cache
from core.models import Tool
from unittest.mock import patch, MagicMock
import subprocess

User = get_user_model()

class MockMetadata:
    def __init__(self, name, namespace):
        self.name = name
        self.namespace = namespace
        self.creation_timestamp = None
        self.labels = {}

class MockStatus:
    def __init__(self, phase):
        self.phase = phase
        self.container_statuses = []

class MockPod:
    def __init__(self, name, namespace, phase):
        self.metadata = MockMetadata(name, namespace)
        self.status = MockStatus(phase)

class K8sModuleTest(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()
        self.user = User.objects.create_superuser(username='admin', password='password', email='admin@test.com')
        self.client.login(username='admin', password='password')
        self.tool = Tool.objects.create(name="k8s", status="installed")

    @patch('modules.k8s.module.K8S_AVAILABLE', True)
    @patch('kubernetes.config.load_kube_config')
    @patch('kubernetes.client.ApiClient')
    @patch('kubernetes.client.CoreV1Api')
    @patch('kubernetes.client.AppsV1Api')
    @patch('modules.k8s.module.run_command')
    @patch('django.core.cache.cache.set')
    def test_k8s_pods_partial(self, mock_cache_set, mock_run, mock_apps, mock_v1, mock_api_client, mock_config):
        mock_run.return_value = b"active"
        
        # Mock CoreV1Api
        mock_core_api = MagicMock()
        
        # Mock list_namespace for the connectivity check
        mock_ns = MagicMock()
        mock_ns.items = []
        mock_core_api.list_namespace.return_value = mock_ns
        
        # Mock pods list
        mock_pods = MagicMock()
        mock_pods.items = [MockPod("test-pod", "default", "Running")]
        mock_core_api.list_pod_for_all_namespaces.return_value = mock_pods
        
        mock_v1.return_value = mock_core_api
        
        # Mock AppsV1Api
        mock_apps_api = MagicMock()
        mock_apps_api.list_deployment_for_all_namespaces.return_value.items = []
        mock_apps.return_value = mock_apps_api
        
        response = self.client.get(reverse('tool_detail', kwargs={'tool_name': 'k8s'}) + "?tab=k8s_pods", HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "test-pod")

    @patch('modules.k8s.views.setup_k8s_client', return_value=True)
    @patch('kubernetes.client.CoreV1Api')
    def test_k8s_pod_logs(self, mock_v1, mock_setup):
        mock_api = MagicMock()
        mock_api.read_namespaced_pod_log.return_value = "pod logs"
        mock_v1.return_value = mock_api
        
        url = reverse('k8s_pod_logs', kwargs={'namespace': 'default', 'pod_name': 'test-pod'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), "pod logs")

    @patch('modules.k8s.views.setup_k8s_client', return_value=True)
    @patch('kubernetes.client.CoreV1Api')
    def test_k8s_pod_logs_download(self, mock_v1, mock_setup):
        mock_api = MagicMock()
        mock_api.read_namespaced_pod_log.return_value = "full pod logs"
        mock_v1.return_value = mock_api
        
        url = reverse('k8s_pod_logs_download', kwargs={'namespace': 'default', 'pod_name': 'test-pod'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"full pod logs", response.content)

    @patch('modules.k8s.views.setup_k8s_client', return_value=True)
    @patch('kubernetes.client.AppsV1Api')
    def test_k8s_deployment_scale(self, mock_apps, mock_setup):
        mock_api = MagicMock()
        mock_apps.return_value = mock_api
        
        url = reverse('k8s_deployment_scale', kwargs={'namespace': 'default', 'name': 'test-deploy', 'replicas': 3})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        mock_api.patch_namespaced_deployment_scale.assert_called_once()

    @patch('modules.k8s.views.setup_k8s_client', return_value=True)
    @patch('modules.k8s.views.run_command')
    def test_k8s_resource_describe(self, mock_run, mock_setup):
        mock_run.return_value = b"resource description"
        url = reverse('k8s_resource_describe', kwargs={'resource_type': 'pod', 'namespace': 'default', 'name': 'test-pod'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("resource description", response.content.decode())

    @patch('modules.k8s.views.setup_k8s_client', return_value=True)
    @patch('kubernetes.client.ApiClient')
    @patch('kubernetes.client.CoreV1Api')
    def test_k8s_resource_yaml_get(self, mock_v1, mock_api_client_class, mock_setup):
        mock_api = MagicMock()
        mock_pod = MagicMock()
        mock_pod.metadata.name = "test-pod"
        mock_api.read_namespaced_pod.return_value = mock_pod
        mock_v1.return_value = mock_api
        
        # Mock sanitize_for_serialization to return a real dict
        mock_api_client = MagicMock()
        mock_api_client.sanitize_for_serialization.return_value = {
            'apiVersion': 'v1',
            'kind': 'Pod',
            'metadata': {'name': 'test-pod'}
        }
        mock_api_client_class.return_value = mock_api_client
        
        url = reverse('k8s_resource_yaml', kwargs={'resource_type': 'pod', 'namespace': 'default', 'name': 'test-pod'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("test-pod", response.content.decode())

    @patch('modules.k8s.views.setup_k8s_client', return_value=True)
    @patch('kubernetes.client.AppsV1Api')
    def test_k8s_deployment_restart(self, mock_apps, mock_setup):
        mock_api = MagicMock()
        mock_apps.return_value = mock_api
        url = reverse('k8s_deployment_restart', kwargs={'namespace': 'default', 'name': 'test-deploy'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        mock_api.patch_namespaced_deployment.assert_called_once()

    @patch('modules.k8s.module.K8S_AVAILABLE', True)
    @patch('kubernetes.config.load_kube_config')
    @patch('kubernetes.client.CoreV1Api')
    @patch('kubernetes.client.AppsV1Api')
    def test_k8s_context_data_namespace(self, mock_apps, mock_v1, mock_config):
        from modules.k8s.module import Module
        module = Module()
        
        mock_core_api = MagicMock()
        mock_ns = MagicMock()
        mock_ns.items = []
        mock_core_api.list_namespace.return_value = mock_ns
        mock_v1.return_value = mock_core_api
        
        mock_apps_api = MagicMock()
        mock_apps.return_value = mock_apps_api
        
        request = MagicMock()
        request.GET = {'namespace': 'test-ns'}
        
        with patch('modules.k8s.module.get_kubeconfig', return_value='/tmp/config'):
            context = module.get_context_data(request, self.tool)
            self.assertEqual(context['current_namespace'], 'test-ns')
            mock_core_api.list_namespaced_pod.assert_called()

    @patch('modules.k8s.module.K8S_AVAILABLE', False)
    @patch('modules.k8s.module.run_command')
    def test_k8s_module_logic(self, mock_run):
        from modules.k8s.module import Module
        module = Module()
        
        mock_run.return_value = b"Client Version: v1.29.1"
        self.assertIn("v1.29", module.get_service_version())
        
        mock_run.return_value = b"active"
        self.assertEqual(module.get_service_status(self.tool), "running")
        
        module.service_start(self.tool)
        mock_run.assert_called_with(["systemctl", "start", "kubelet"])
        
        module.service_stop(self.tool)
        mock_run.assert_called_with(["systemctl", "stop", "kubelet"])
        
        module.service_restart(self.tool)
        mock_run.assert_called_with(["systemctl", "restart", "kubelet"])
        
        self.assertEqual(module.get_logs_url(self.tool), '/k8s/service/logs/')
        
        # Test version with newer format
        mock_run.return_value = b'GitVersion:"v1.29.15"'
        self.assertEqual(module.get_service_version(), "v1.29.15")

        # Test version with fallback
        mock_run.side_effect = None
        mock_run.return_value = b"Some Version 1.2.3"
        self.assertEqual(module.get_service_version(), "Some Version 1.2.3")

        # Test version exception
        mock_run.side_effect = Exception("version error")
        self.assertIsNone(module.get_service_version())
        mock_run.side_effect = None

        # Test status exception
        mock_run.side_effect = Exception("status error")
        self.assertEqual(module.get_service_status(self.tool), "stopped")
        mock_run.side_effect = None

    @patch('modules.k8s.module.K8S_AVAILABLE', True)
    @patch('kubernetes.config.load_kube_config')
    @patch('kubernetes.client.VersionApi')
    def test_k8s_module_version_api(self, mock_version, mock_config):
        from modules.k8s.module import Module
        module = Module()
        
        mock_api = MagicMock()
        mock_api.get_code.return_value.git_version = "v1.29.2"
        mock_version.return_value = mock_api
        
        with patch('modules.k8s.module.get_kubeconfig', return_value='/tmp/config'):
            self.assertEqual(module.get_service_version(), "v1.29.2")

    @patch('modules.k8s.views.setup_k8s_client', return_value=True)
    @patch('kubernetes.client.CoreV1Api')
    def test_k8s_pod_action_delete(self, mock_v1, mock_setup):
        mock_api = MagicMock()
        mock_v1.return_value = mock_api
        url = reverse('k8s_pod_action', kwargs={'namespace': 'default', 'pod_name': 'test-pod', 'action': 'delete'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        mock_api.delete_namespaced_pod.assert_called_once()

    @patch('modules.k8s.views.run_command')
    def test_k8s_terminal_run(self, mock_run):
        mock_run.return_value = b"cmd output"
        url = reverse('k8s_terminal_run')
        response = self.client.post(url, {'command': 'ls', 'namespace': 'default', 'pod': 'test-pod'})
        self.assertEqual(response.status_code, 200)
        self.assertIn("cmd output", response.content.decode())

    @patch('modules.k8s.views.run_command')
    def test_k8s_service_logs_loop(self, mock_run):
        # First service fails, second succeeds
        import subprocess
        mock_run.side_effect = [subprocess.CalledProcessError(1, 'journalctl'), b"k3s logs"]
        url = reverse('k8s_service_logs')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("k3s logs", response.content.decode())

    @patch('modules.k8s.views.run_command')
    def test_k8s_service_logs_download(self, mock_run):
        mock_run.return_value = b"k8s logs download"
        url = reverse('k8s_service_logs_download')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("k8s logs download", response.content.decode())

    @patch('modules.k8s.views.setup_k8s_client', return_value=True)
    @patch('kubernetes.client.CoreV1Api')
    def test_k8s_resource_yaml_post(self, mock_v1, mock_setup):
        mock_api = MagicMock()
        mock_pod = MagicMock()
        mock_pod.metadata.name = "test-pod"
        mock_api.read_namespaced_pod.return_value = mock_pod
        mock_v1.return_value = mock_api
        
        # Mock run_command for kubectl apply
        with patch('modules.k8s.views.run_command') as mock_run:
            url = reverse('k8s_resource_yaml', kwargs={'resource_type': 'pod', 'namespace': 'default', 'name': 'test-pod'})
            response = self.client.post(url, {'yaml': 'apiVersion: v1\nkind: Pod\nmetadata:\n  name: test-pod'})
            self.assertEqual(response.status_code, 200)
            mock_run.assert_called()
            
            # Test failure
            mock_run.side_effect = Exception("apply error")
            response = self.client.post(url, {'yaml': 'invalid'})
            self.assertEqual(response.status_code, 500)
            self.assertIn(b"apply error", response.content)

    @patch('modules.k8s.module.run_command')
    def test_k8s_status_detection(self, mock_run):
        mock_run.return_value = b"active"
        from core.plugin_system import plugin_registry
        module = plugin_registry.get_module("k8s")
        status = module.get_service_status(self.tool)
        self.assertEqual(status, "running")

    @patch('modules.k8s.module.run_command')
    @patch('modules.k8s.module.threading.Thread')
    def test_k8s_install(self, mock_thread, mock_run):
        from modules.k8s.module import Module
        module = Module()
        self.tool.status = 'not_installed'
        self.tool.save()
        
        module.install(None, self.tool)
        self.assertEqual(self.tool.status, 'installing')
        mock_thread.assert_called_once()
        
        # Test the inner run_install function logic
        target_func = mock_thread.call_args[1]['target']
        
        # Reset tool status to test execution
        self.tool.status = 'installing'
        self.tool.save()
        
        target_func()
        self.tool.refresh_from_db()
        self.assertEqual(self.tool.status, 'installed')
        self.assertEqual(self.tool.current_stage, "Installation completed successfully")
        
        # Test failure
        mock_run.side_effect = Exception("install failed")
        target_func()
        self.tool.refresh_from_db()
        self.assertEqual(self.tool.status, 'error')
        self.assertIn("install failed", self.tool.config_data['error_log'])

    @patch('modules.k8s.module.K8S_AVAILABLE', True)
    @patch('modules.k8s.module.get_kubeconfig', return_value='/tmp/config')
    @patch('kubernetes.config.load_kube_config')
    @patch('kubernetes.stream.stream')
    def test_k8s_session(self, mock_stream_func, mock_config, mock_get_cfg):
        from modules.k8s.module import K8sSession
        import threading
        import time
        mock_stream = MagicMock()
        mock_stream.is_open.return_value = True
        mock_stream.peek_stdout.side_effect = [True, False]
        mock_stream.read_stdout.return_value = "output"
        mock_stream.peek_stderr.return_value = False
        mock_stream_func.return_value = mock_stream
        
        with patch('kubernetes.client.CoreV1Api'):
            session = K8sSession("default", "test-pod")
            
            # Start run in a way we can stop it
            def stop_session():
                time.sleep(0.1)
                session.keep_running = False
            
            threading.Thread(target=stop_session).start()
            session.run()
            
            self.assertTrue(any(b"output" in h for h in session.history))
            
            session.send_input("ls")
            mock_stream.write_stdin.assert_called_with("ls")

    @patch('modules.k8s.module.K8S_AVAILABLE', True)
    @patch('modules.k8s.module.get_kubeconfig', return_value='/tmp/config')
    @patch('kubernetes.config.load_kube_config')
    @patch('kubernetes.client.CoreV1Api')
    def test_k8s_connectivity_error_caching(self, mock_v1, mock_config, mock_get_cfg):
        from modules.k8s.module import Module
        module = Module()
        
        mock_api = MagicMock()
        mock_api.list_namespace.side_effect = Exception("Connection refused")
        mock_v1.return_value = mock_api
        
        request = MagicMock()
        request.GET = {}
        
        # First call - should set cache
        with self.assertLogs('modules.k8s.module', level='ERROR') as cm:
            context = module.get_context_data(request, self.tool)
            self.assertIn("Connection refused", context['k8s_error'])
        
        # Second call - should use cache
        mock_api.list_namespace.reset_mock()
        context = module.get_context_data(request, self.tool)
        self.assertIn("(cached)", context['k8s_error'])
        mock_api.list_namespace.assert_not_called()

    @patch('modules.k8s.module.K8S_AVAILABLE', True)
    @patch('modules.k8s.module.get_kubeconfig', return_value='/tmp/config')
    @patch('kubernetes.config.load_kube_config')
    @patch('kubernetes.client.CoreV1Api')
    def test_k8s_probing_flag(self, mock_v1, mock_config, mock_get_cfg):
        from modules.k8s.module import Module
        module = Module()
        
        cache.set(f'k8s_probing_{self.tool.id}', True)
        context = module.get_context_data(MagicMock(), self.tool)
        self.assertTrue(context.get('is_probing'))
        
        response = module.handle_hx_request(MagicMock(), self.tool, 'k8s_pods')
        self.assertEqual(response.status_code, 204)

    @patch('modules.k8s.module.K8S_AVAILABLE', False)
    def test_k8s_not_available(self):
        from modules.k8s.module import Module
        module = Module()
        context = module.get_context_data(MagicMock(), self.tool)
        self.assertIn("not installed", context['k8s_error'])

    @patch('modules.k8s.module.get_kubeconfig', return_value=None)
    @patch('modules.k8s.module.K8S_AVAILABLE', True)
    def test_k8s_no_config(self, mock_get_cfg):
        from modules.k8s.module import Module
        module = Module()
        context = module.get_context_data(MagicMock(), self.tool)
        self.assertIn("No readable kubeconfig", context['k8s_error'])

    @patch('modules.k8s.views.K8S_AVAILABLE', False)
    def test_k8s_views_no_k8s(self):
        url = reverse('k8s_pod_logs', kwargs={'namespace': 'default', 'pod_name': 'test'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 500)
        self.assertIn(b"K8s not available", response.content)

    @patch('modules.k8s.views.setup_k8s_client', return_value=True)
    @patch('kubernetes.client.CoreV1Api')
    def test_k8s_pod_logs_error(self, mock_v1, mock_setup):
        mock_api = MagicMock()
        mock_api.read_namespaced_pod_log.side_effect = Exception("API error")
        mock_v1.return_value = mock_api
        url = reverse('k8s_pod_logs', kwargs={'namespace': 'default', 'pod_name': 'test'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 500)
        self.assertIn(b"API error", response.content)

    @patch('modules.k8s.views.setup_k8s_client', return_value=True)
    @patch('kubernetes.client.AppsV1Api')
    def test_k8s_deployment_scale_error(self, mock_apps, mock_setup):
        mock_api = MagicMock()
        mock_api.patch_namespaced_deployment_scale.side_effect = Exception("Scale error")
        mock_apps.return_value = mock_api
        url = reverse('k8s_deployment_scale', kwargs={'namespace': 'default', 'name': 'test', 'replicas': 1})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 500)
        self.assertIn(b"Scale error", response.content)

    @patch('modules.k8s.views.setup_k8s_client', return_value=True)
    def test_k8s_resource_yaml_invalid_type(self, mock_setup):
        url = reverse('k8s_resource_yaml', kwargs={'resource_type': 'invalid', 'namespace': 'default', 'name': 'test'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 400)

    @patch('modules.k8s.views.run_command')
    def test_k8s_terminal_run_error(self, mock_run):
        import subprocess
        mock_run.side_effect = subprocess.CalledProcessError(1, 'kubectl', output=b"Execution error")
        url = reverse('k8s_terminal_run')
        response = self.client.post(url, {'command': 'ls', 'namespace': 'default', 'pod': 'test'})
        self.assertEqual(response.status_code, 200)
        self.assertIn("Execution error", response.content.decode())

    def test_k8s_pod_shell_view(self):
        url = reverse('k8s_pod_shell', kwargs={'namespace': 'default', 'pod_name': 'test'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), "Shell initialised")

    @patch('modules.k8s.views.run_command')
    def test_k8s_service_logs_no_entries(self, mock_run):
        mock_run.return_value = b"No entries"
        url = reverse('k8s_service_logs')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"No log entries found", response.content)

    @patch('modules.k8s.views.run_command')
    def test_k8s_service_logs_error(self, mock_run):
        # We need to trigger the outer exception in views.py
        # The inner loop catches exceptions, so we make it fail after the loop or make the loop fail fundamentally
        mock_run.side_effect = Exception("General error")
        url = reverse('k8s_service_logs')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 500)
        self.assertIn(b"Error fetching system logs", response.content)

    @patch('modules.k8s.views.setup_k8s_client', return_value=True)
    @patch('kubernetes.client.ApiClient')
    @patch('kubernetes.client.CoreV1Api')
    @patch('kubernetes.client.AppsV1Api')
    def test_k8s_resource_yaml_types(self, mock_apps, mock_v1, mock_api_client_class, mock_setup):
        mock_api_client = MagicMock()
        mock_api_client.sanitize_for_serialization.return_value = {'kind': 'Test'}
        mock_api_client_class.return_value = mock_api_client
        
        mock_v1_api = MagicMock()
        mock_v1.return_value = mock_v1_api
        mock_apps_api = MagicMock()
        mock_apps.return_value = mock_apps_api
        
        types = ['deployment', 'service', 'configmap', 'secret']
        for t in types:
            url = reverse('k8s_resource_yaml', kwargs={'resource_type': t, 'namespace': 'default', 'name': 'test'})
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)

    @patch('modules.k8s.views.run_command')
    def test_k8s_terminal_run_direct(self, mock_run):
        mock_run.return_value = b"direct output"
        url = reverse('k8s_terminal_run')
        # Test direct command (no pod)
        response = self.client.post(url, {'command': 'get pods'})
        self.assertEqual(response.status_code, 200)
        self.assertIn("kubectl get pods -A", response.content.decode())
        
        # Test command already starting with kubectl
        response = self.client.post(url, {'command': 'kubectl version'})
        self.assertEqual(response.status_code, 200)
        self.assertIn("$ kubectl version", response.content.decode())

    @patch('modules.k8s.views.run_command')
    def test_k8s_terminal_run_invalid(self, mock_run):
        url = reverse('k8s_terminal_run')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 400)
