import subprocess
import threading
import os
from django.shortcuts import render, redirect
from django.urls import path, re_path
from core.plugin_system import BaseModule
from core.terminal_manager import TerminalSession
from core.utils import run_sudo_command
try:
    from kubernetes import client, config, stream
    K8S_AVAILABLE = True
except ImportError:
    K8S_AVAILABLE = False

def get_kubeconfig():
    """Returns the path to the kubeconfig file if it exists and is accessible by the current process."""
    paths = [
        '/etc/kubernetes/admin.conf',
        '/etc/rancher/k3s/k3s.yaml',
        '/var/snap/microk8s/current/credentials/client.config',
        os.path.expanduser('~/.kube/config'),
        '/root/.kube/config'
    ]
    for p in paths:
        if os.path.exists(p) and os.access(p, os.R_OK) and os.path.getsize(p) > 0:
            return p
    
    # If no directly readable file found, we can't load it in Python easily
    # unless we copy it to a readable location.
    return None

class K8sSession(TerminalSession):
    def __init__(self, namespace, pod_name):
        super().__init__()
        self.namespace = namespace
        self.pod_name = pod_name
        kconfig = get_kubeconfig()
        if kconfig:
            os.environ['KUBECONFIG'] = kconfig
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

    def get_service_version(self):
        try:
            kconfig = get_kubeconfig()
            env = os.environ.copy()
            if kconfig:
                env['KUBECONFIG'] = kconfig

            # Try to get server version via API
            if K8S_AVAILABLE:
                try:
                    config.load_kube_config(config_file=kconfig)
                    version_info = client.VersionApi().get_code()
                    return version_info.git_version
                except:
                    pass

            cmd = ['kubectl', 'version', '--client']
            process = run_sudo_command(cmd, capture_output=True, env=env, log_errors=False)
            if process:
                import re
                output = process.decode()
                # Try to find version in newer format (GitVersion:"v1.29.1") or older format (Client Version: v1.28.2)
                match = re.search(r'GitVersion:"(v[^"]+)"', output)
                if match:
                    return match.group(1)
                match = re.search(r'Client Version:\s+(v[0-9.]+)', output)
                if match:
                    return match.group(1)
                # Fallback: just return the first line if it looks like a version
                first_line = output.splitlines()[0]
                if 'Version' in first_line:
                    return first_line.strip()
        except Exception:
            pass
        return None

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
        if tool.status == 'installed':
            if not K8S_AVAILABLE:
                context['k8s_error'] = "The 'kubernetes' Python library is not installed. Please install it to manage Kubernetes clusters."
                return context
            
            try:
                kconfig = get_kubeconfig()
                if not kconfig:
                    context['k8s_error'] = "No readable kubeconfig found. Ensure Kubernetes is installed and the config file is readable."
                    return context

                config.load_kube_config(config_file=kconfig)
                
                # Get current context
                try:
                    contexts, active_context = config.list_kube_config_contexts(config_file=kconfig)
                    if active_context:
                        context['k8s_context'] = active_context['name']
                    else:
                        # Fallback to kubectl if python client fails to find active context
                        env = os.environ.copy()
                        env['KUBECONFIG'] = kconfig
                        cmd = ['kubectl', 'config', 'current-context']
                        out = run_sudo_command(cmd, capture_output=True, env=env, log_errors=False)
                        context['k8s_context'] = out.decode().strip() if out else 'N/A'
                except Exception as e:
                    context['k8s_context'] = f'Error: {str(e)}'

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

    def install(self, request, tool):
        if tool.status not in ['not_installed', 'error']:
            return

        tool.status = 'installing'
        tool.save()

        def run_install():
            stages = [
                ("Updating apt repositories...", "apt-get update"),
                ("Installing dependencies...", "apt-get install -y ca-certificates curl gnupg"),
                ("Setting up Kubernetes GPG key...", "bash -c 'curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.29/deb/Release.key | gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg --yes'"),
                ("Adding Kubernetes repository...", "bash -c 'echo \"deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.29/deb/ /\" | tee /etc/apt/sources.list.d/kubernetes.list'"),
                ("Updating package index...", "apt-get update"),
                ("Installing K8s components (kubeadm, kubelet, kubectl)...", "bash -c 'apt-get install -y kubelet kubeadm kubectl && apt-mark hold kubelet kubeadm kubectl'"),
                ("Disabling SWAP (Required for K8s)...", "bash -c 'swapoff -a && sed -i \"/ swap / s/^\\(.*\\)$/#\\1/g\" /etc/fstab'"),
                ("Loading kernel modules...", "bash -c 'modprobe overlay && modprobe br_netfilter'"),
                ("Configuring sysctl for K8s...", "bash -c 'echo -e \"net.bridge.bridge-nf-call-iptables = 1\\nnet.bridge.bridge-nf-call-ip6tables = 1\\nnet.ipv4.ip_forward = 1\" | tee /etc/sysctl.d/k8s.conf && sysctl --system'"),
                ("Configuring firewalld ports...", "bash -c 'if systemctl is-active --quiet firewalld; then firewall-cmd --permanent --add-port=6443/tcp && firewall-cmd --permanent --add-port=10250/tcp && firewall-cmd --reload; fi'"),
                ("Configuring containerd (CRI)...", "bash -c 'mkdir -p /etc/containerd && containerd config default | tee /etc/containerd/config.toml > /dev/null && sed -i \"s/SystemdCgroup = false/SystemdCgroup = true/g\" /etc/containerd/config.toml && systemctl restart containerd'"),
                ("Pulling Kubernetes images...", "kubeadm config images pull"),
                ("Initializing Kubernetes cluster...", "bash -c 'kubeadm init --pod-network-cidr=10.244.0.0/16 || true'"),
                ("Setting up kubeconfig...", "bash -c 'mkdir -p /root/.kube && cp -i /etc/kubernetes/admin.conf /root/.kube/config && chmod 644 /etc/kubernetes/admin.conf && chmod 644 /root/.kube/config'"),
                ("Installing Network Plugin (Flannel)...", "bash -c 'KUBECONFIG=/etc/kubernetes/admin.conf kubectl apply -f https://github.com/flannel-io/flannel/releases/latest/download/kube-flannel.yml'"),
                ("Allowing pods on control-plane...", "bash -c 'KUBECONFIG=/etc/kubernetes/admin.conf kubectl taint nodes --all node-role.kubernetes.io/control-plane- || true'"),
            ]
            try:
                for stage_name, command in stages:
                    tool.current_stage = stage_name
                    tool.save()
                    run_sudo_command(command, shell=True, capture_output=False, timeout=600)
                
                tool.status = 'installed'
                tool.current_stage = "Installation completed successfully"
            except Exception as e:
                tool.status = 'error'
                tool.config_data['error_log'] = str(e)
            tool.save()

        threading.Thread(target=run_install).start()

    def get_terminal_session_types(self):
        return {'k8s': K8sSession}

    def get_urls(self):
        from . import views
        return [
            path('k8s/pod/<str:namespace>/<str:pod_name>/logs/', views.k8s_pod_logs, name='k8s_pod_logs'),
            path('k8s/pod/<str:namespace>/<str:pod_name>/logs/download/', views.k8s_pod_logs_download, name='k8s_pod_logs_download'),
            path('k8s/service/logs/', views.k8s_service_logs, name='k8s_service_logs'),
            path('k8s/service/logs/download/', views.k8s_service_logs_download, name='k8s_service_logs_download'),
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
