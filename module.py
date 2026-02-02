import subprocess
from django.shortcuts import render, redirect
from django.urls import path
from core.plugin_system import BaseModule
from core.terminal_manager import TerminalSession
try:
    from kubernetes import client, config, stream
    K8S_AVAILABLE = True
except ImportError:
    K8S_AVAILABLE = False

class K8sSession(TerminalSession):
    def __init__(self, namespace, pod_name):
        super().__init__()
        self.namespace = namespace
        self.pod_name = pod_name
        config.load_kube_config()
        self.api = client.CoreV1Api()
        self._setup_session()

    def _setup_session(self):
        self.stream = stream.stream(
            self.api.connect_get_namespaced_pod_exec, self.pod_name, self.namespace,
            command=['sh'], stderr=True, stdin=True, stdout=True, tty=True, _preload_content=False
        )

    def run(self):
        try:
            while self.keep_running and self.stream.is_open():
                self.stream.update(timeout=0.1)
                if self.stream.peek_stdout():
                    self.add_history(self.stream.read_stdout().encode())
                if self.stream.peek_stderr():
                    self.add_history(self.stream.read_stderr().encode())
        except:
            pass
        self.stream.close()

    def send_input(self, data):
        if self.stream.is_open():
            self.stream.write_stdin(data)

class Module(BaseModule):
    module_id = "k8s"
    module_name = "Kubernetes"
    description = "Manage Kubernetes clusters, pods, deployments and services."

    def get_context_data(self, request, tool):
        context = {}
        if tool.status == 'installed' and K8S_AVAILABLE:
            try:
                config.load_kube_config()
                v1 = client.CoreV1Api()
                apps_v1 = client.AppsV1Api()
                namespace = request.GET.get('namespace')
                
                if namespace:
                    context['k8s_pods'] = v1.list_namespaced_pod(namespace).items
                    context['current_namespace'] = namespace
                else:
                    context['k8s_pods'] = v1.list_pod_for_all_namespaces().items
                
                context['k8s_nodes'] = v1.list_node().items
                context['k8s_namespaces'] = v1.list_namespace().items
                context['k8s_available'] = True
            except Exception as e:
                context['k8s_error'] = str(e)
        return context

    def handle_hx_request(self, request, tool, target):
        context = self.get_context_data(request, tool)
        context['tool'] = tool
        if target == 'k8s_pods':
            return render(request, 'core/partials/k8s_pods.html', context)
        elif target == 'k8s_nodes':
            return render(request, 'core/partials/k8s_nodes.html', context)
        return None

    def get_terminal_session_types(self):
        return {'k8s': K8sSession}

    def get_urls(self):
        return []
