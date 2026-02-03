import subprocess
from django.shortcuts import render, redirect
from django.urls import path, re_path
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
    @property
    def module_id(self):
        return "k8s"

    @property
    def module_name(self):
        return "Kubernetes"

    description = "Manage Kubernetes clusters, pods, deployments and services."
    version = "1.0.0"

    def get_icon_class(self):
        return "kubernetes"

    def get_extra_content_template_name(self):
        return "core/modules/k8s_scripts.html"

    def get_logs_url(self, tool):
        return '/k8s/service/logs/'

    def get_resource_header_template_name(self):
        return "core/modules/k8s_resource_header.html"

    def get_resource_tabs(self):
        return [
            {'id': 'pods', 'label': 'Pods', 'template': 'core/partials/k8s_pods.html', 'hx_get': '/tool/k8s/?tab=k8s_pods', 'hx_auto_refresh': 'every 5s'},
            {'id': 'deployments', 'label': 'Deployments', 'template': 'core/partials/k8s_deployments.html', 'hx_get': '/tool/k8s/?tab=k8s_deployments', 'hx_auto_refresh': 'every 5s'},
            {'id': 'services', 'label': 'Services', 'template': 'core/partials/k8s_services.html', 'hx_get': '/tool/k8s/?tab=k8s_services', 'hx_auto_refresh': 'every 5s'},
            {'id': 'nodes', 'label': 'Nodes', 'template': 'core/partials/k8s_nodes.html', 'hx_get': '/tool/k8s/?tab=k8s_nodes', 'hx_auto_refresh': 'every 5s'},
            {'id': 'configmaps', 'label': 'ConfigMaps', 'template': 'core/partials/k8s_configmaps.html', 'hx_get': '/tool/k8s/?tab=k8s_configmaps', 'hx_auto_refresh': 'every 5s'},
            {'id': 'secrets', 'label': 'Secrets', 'template': 'core/partials/k8s_secrets.html', 'hx_get': '/tool/k8s/?tab=k8s_secrets', 'hx_auto_refresh': 'every 5s'},
            {'id': 'events', 'label': 'Events', 'template': 'core/partials/k8s_events.html', 'hx_get': '/tool/k8s/?tab=k8s_events', 'hx_auto_refresh': 'every 5s'},
        ]

    def get_context_data(self, request, tool):
        context = {}
        if tool.status == 'installed' and K8S_AVAILABLE:
            try:
                config.load_kube_config()
                
                # Get current context
                try:
                    contexts, active_context = config.list_kube_config_contexts()
                    context['k8s_context'] = active_context['name'] if active_context else 'N/A'
                except:
                    context['k8s_context'] = 'Unknown'

                v1 = client.CoreV1Api()
                apps_v1 = client.AppsV1Api()
                namespace = request.GET.get('namespace')
                
                if namespace:
                    context['k8s_pods'] = v1.list_namespaced_pod(namespace).items
                    context['k8s_deployments'] = apps_v1.list_namespaced_deployment(namespace).items
                    context['k8s_services'] = v1.list_namespaced_service(namespace).items
                    context['k8s_configmaps'] = v1.list_namespaced_config_map(namespace).items
                    context['k8s_secrets'] = v1.list_namespaced_secret(namespace).items
                    context['k8s_events'] = v1.list_namespaced_event(namespace).items
                    context['current_namespace'] = namespace
                else:
                    context['k8s_pods'] = v1.list_pod_for_all_namespaces().items
                    context['k8s_deployments'] = apps_v1.list_deployment_for_all_namespaces().items
                    context['k8s_services'] = v1.list_service_for_all_namespaces().items
                    context['k8s_configmaps'] = v1.list_config_map_for_all_namespaces().items
                    context['k8s_secrets'] = v1.list_secret_for_all_namespaces().items
                    context['k8s_events'] = v1.list_event_for_all_namespaces().items
                
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
        elif target == 'k8s_deployments':
            return render(request, 'core/partials/k8s_deployments.html', context)
        elif target == 'k8s_services':
            return render(request, 'core/partials/k8s_services.html', context)
        elif target == 'k8s_nodes':
            return render(request, 'core/partials/k8s_nodes.html', context)
        elif target == 'k8s_configmaps':
            return render(request, 'core/partials/k8s_configmaps.html', context)
        elif target == 'k8s_secrets':
            return render(request, 'core/partials/k8s_secrets.html', context)
        elif target == 'k8s_events':
            return render(request, 'core/partials/k8s_events.html', context)
        return None

    def get_terminal_session_types(self):
        return {'k8s': K8sSession}

    def get_urls(self):
        from . import views
        return [
            path('k8s/pod/<str:namespace>/<str:pod_name>/logs/', views.k8s_pod_logs, name='k8s_pod_logs'),
            path('k8s/pod/<str:namespace>/<str:pod_name>/logs/download/', views.k8s_pod_logs_download, name='k8s_pod_logs_download'),
            path('k8s/service/logs/', views.k8s_service_logs, name='k8s_service_logs'),
            path('k8s/pod/<str:namespace>/<str:pod_name>/act/<str:action>/', views.k8s_pod_action, name='k8s_pod_action'),
            path('k8s/resource/yaml/<str:resource_type>/<str:namespace>/<str:name>/', views.k8s_resource_yaml, name='k8s_resource_yaml'),
            path('k8s/terminal/run/', views.k8s_terminal_run, name='k8s_terminal_run'),
            path('k8s/pod/<str:namespace>/<str:pod_name>/shell/', views.k8s_pod_shell, name='k8s_pod_shell'),
            path('k8s/deployment/<str:namespace>/<str:name>/scale/<int:replicas>/', views.k8s_deployment_scale, name='k8s_deployment_scale'),
            path('k8s/deployment/<str:namespace>/<str:name>/restart/', views.k8s_deployment_restart, name='k8s_deployment_restart'),
            path('k8s/resource/describe/<str:resource_type>/<str:name>/', views.k8s_resource_describe, {'namespace': ''}, name='k8s_resource_describe_cluster'),
            path('k8s/resource/describe/<str:resource_type>/<str:namespace>/<str:name>/', views.k8s_resource_describe, name='k8s_resource_describe'),
        ]

    def get_websocket_urls(self):
        from core import consumers
        return [
            re_path(r'ws/k8s/shell/(?P<namespace>[\w-]+)/(?P<pod_name>[\w-]+)/$', consumers.TerminalConsumer.as_asgi(), {'session_type': 'k8s'}),
        ]
