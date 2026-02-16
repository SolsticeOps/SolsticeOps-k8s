import subprocess
import os
import yaml
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from core.utils import run_command, get_primary_ip
from .module import get_kubeconfig
try:
    from kubernetes import client as k8s_client, config as k8s_config
    K8S_AVAILABLE = True
except ImportError:
    K8S_AVAILABLE = False

def setup_k8s_client():
    if not K8S_AVAILABLE: return False
    try:
        kconfig = get_kubeconfig()
        k8s_config.load_kube_config(config_file=kconfig)
        return True
    except:
        return False

@login_required
def k8s_pod_logs(request, namespace, pod_name):
    if not setup_k8s_client():
        return HttpResponse("K8s not available", status=500)
    try:
        v1 = k8s_client.CoreV1Api()
        logs = v1.read_namespaced_pod_log(name=pod_name, namespace=namespace, tail_lines=200)
        return HttpResponse(logs, content_type='text/plain')
    except Exception as e:
        return HttpResponse(f"Error: {str(e)}", status=500)

@login_required
def k8s_pod_logs_download(request, namespace, pod_name):
    if not setup_k8s_client():
        return HttpResponse("K8s not available", status=500)
    try:
        v1 = k8s_client.CoreV1Api()
        logs = v1.read_namespaced_pod_log(name=pod_name, namespace=namespace)
        response = HttpResponse(logs, content_type='text/plain')
        response['Content-Disposition'] = f'attachment; filename="pod_{pod_name}_logs.log"'
        return response
    except Exception as e:
        return HttpResponse(f"Error downloading pod logs: {str(e)}", status=500)

@login_required
def k8s_pod_action(request, namespace, pod_name, action):
    if not setup_k8s_client():
        return redirect('tool_detail', tool_name='k8s')
    try:
        v1 = k8s_client.CoreV1Api()
        if action == 'delete':
            v1.delete_namespaced_pod(name=pod_name, namespace=namespace)
    except Exception as e:
        pass
    
    return redirect('tool_detail', tool_name='k8s')

@login_required
def k8s_deployment_scale(request, namespace, name, replicas):
    if not setup_k8s_client():
        return HttpResponse("K8s not available", status=500)
    try:
        apps_v1 = k8s_client.AppsV1Api()
        body = {'spec': {'replicas': int(replicas)}}
        apps_v1.patch_namespaced_deployment_scale(name=name, namespace=namespace, body=body)
        return redirect('tool_detail', tool_name='k8s')
    except Exception as e:
        return HttpResponse(str(e), status=500)

@login_required
def k8s_deployment_restart(request, namespace, name):
    if not setup_k8s_client():
        return HttpResponse("K8s not available", status=500)
    try:
        apps_v1 = k8s_client.AppsV1Api()
        from datetime import datetime
        now = datetime.now().isoformat()
        body = {
            'spec': {
                'template': {
                    'metadata': {
                        'annotations': {
                            'kubectl.kubernetes.io/restartedAt': now
                        }
                    }
                }
            }
        }
        apps_v1.patch_namespaced_deployment(name=name, namespace=namespace, body=body)
        return redirect('tool_detail', tool_name='k8s')
    except Exception as e:
        return HttpResponse(str(e), status=500)

@login_required
def k8s_resource_describe(request, resource_type, namespace, name):
    try:
        kconfig = get_kubeconfig()
        env = os.environ.copy()
        if kconfig:
            env['KUBECONFIG'] = kconfig

        cmd = ['kubectl', 'describe', resource_type, name]
        if namespace:
            cmd.extend(['-n', namespace])
        
        output = run_command(cmd, env=env).decode()
        return HttpResponse(output)
    except Exception as e:
        return HttpResponse(str(e), status=500)

@login_required
def k8s_resource_yaml(request, resource_type, namespace, name):
    if not setup_k8s_client():
        return HttpResponse("K8s not available", status=500)
    
    api_map = {
        'pod': k8s_client.CoreV1Api().read_namespaced_pod,
        'deployment': k8s_client.AppsV1Api().read_namespaced_deployment,
        'service': k8s_client.CoreV1Api().read_namespaced_service,
        'configmap': k8s_client.CoreV1Api().read_namespaced_config_map,
        'secret': k8s_client.CoreV1Api().read_namespaced_secret,
    }
    
    read_func = api_map.get(resource_type)
    if not read_func:
        return HttpResponse("Invalid resource type", status=400)

    try:
        resource = read_func(name=name, namespace=namespace)
        resource_dict = k8s_client.ApiClient().sanitize_for_serialization(resource)
        
        def strip_read_only(d):
            if not isinstance(d, dict): return
            d.pop('status', None)
            if 'metadata' in d:
                m = d['metadata']
                for field in ['uid', 'resourceVersion', 'creationTimestamp', 'generation', 'managedFields', 'selfLink']:
                    m.pop(field, None)
        
        strip_read_only(resource_dict)

        # Custom YAML dumper for better readability
        class K8sDumper(yaml.SafeDumper):
            def increase_indent(self, flow=False, indentless=False):
                return super(K8sDumper, self).increase_indent(flow, False)

        def str_presenter(dumper, data):
            # Normalize newlines
            data = data.replace('\r\n', '\n').replace('\r', '\n')
            if '\n' in data:
                return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
            return dumper.represent_scalar('tag:yaml.org,2002:str', data)
        
        K8sDumper.add_representer(str, str_presenter)
        
        # Use a larger indent to ensure block scalars are clearly separated
        yaml_content = yaml.dump(resource_dict, Dumper=K8sDumper, default_flow_style=False, sort_keys=False, indent=4)
        
        if request.method == 'POST':
            new_yaml_str = request.POST.get('yaml')
            try:
                kconfig = get_kubeconfig()
                env = os.environ.copy()
                if kconfig:
                    env['KUBECONFIG'] = kconfig

                # Use run_command for apply
                run_command(['kubectl', 'apply', '-f', '-'], input_data=new_yaml_str, env=env)
                return HttpResponse("Resource updated successfully.", status=200)
            except Exception as e:
                return HttpResponse(f"Update failed: {str(e)}", status=500)
            
        return HttpResponse(yaml_content)
    except Exception as e:
        return HttpResponse(str(e), status=500)

@login_required
def k8s_terminal_run(request):
    if request.method == 'POST':
        command = request.POST.get('command', '').strip()
        namespace = request.POST.get('namespace')
        pod = request.POST.get('pod')

        kconfig = get_kubeconfig()
        env = os.environ.copy()
        if kconfig:
            env['KUBECONFIG'] = kconfig

        if pod and namespace:
            full_command = f"kubectl exec -n {namespace} {pod} -- {command}"
            display_prompt = f"# {command}"
        else:
            if not command.startswith('kubectl'):
                command = 'kubectl ' + command
            if ' get ' in command and not any(x in command for x in [' -n ', ' --namespace', ' -A', ' --all-namespaces']):
                command += ' -A'
            full_command = command
            display_prompt = f"$ {command}"
        
        try:
            output = run_command(full_command, shell=True, env=env).decode()
            return HttpResponse(f"{display_prompt}\n{output}")
        except subprocess.CalledProcessError as e:
            return HttpResponse(f"{display_prompt}\nError: {e.output.decode() if e.output else str(e)}")
        except Exception as e:
            return HttpResponse(f"Error: {str(e)}")
    return HttpResponse("Invalid request", status=400)

@login_required
def k8s_pod_shell(request, namespace, pod_name):
    return HttpResponse("Shell initialised")

@login_required
def k8s_service_logs(request):
    try:
        # We'll try to find any relevant service logs
        services = ['kubelet', 'k3s', 'microk8s']
        output = ""
        
        for service in services:
            try:
                # Try journalctl with sudo
                output = run_command(['journalctl', '-u', service, '-n', '200', '--no-pager']).decode()
                if output.strip() and "No entries" not in output:
                    break
            except subprocess.CalledProcessError:
                continue
        
        if not output.strip() or "No entries" in output:
            return HttpResponse("No log entries found. Ensure a Kubernetes service (kubelet, k3s, or microk8s) is running and accessible.", content_type='text/plain')

        return HttpResponse(output, content_type='text/plain')
    except Exception as e:
        return HttpResponse(f"Error fetching system logs: {str(e)}", status=500)

@login_required
def k8s_service_logs_download(request):
    try:
        services = ['kubelet', 'k3s', 'microk8s']
        output = ""
        
        for service in services:
            try:
                output = run_command(['journalctl', '-u', service, '--no-pager']).decode()
                if output.strip() and "No entries" not in output:
                    break
            except subprocess.CalledProcessError:
                continue
        
        response = HttpResponse(output, content_type='text/plain')
        response['Content-Disposition'] = 'attachment; filename="k8s_service_logs.log"'
        return response
    except Exception as e:
        return HttpResponse(f"Error downloading system logs: {str(e)}", status=500)

@login_required
def k8s_repair_ip(request):
    """
    Attempts to repair Kubernetes configuration after a server IP change.
    This is a complex operation and might not work for all setups.
    """
    if request.method != 'POST':
        return HttpResponse("Method not allowed", status=405)
    
    try:
        new_ip = get_primary_ip()
        
        # 1. Update API server manifest
        apiserver_manifest = '/etc/kubernetes/manifests/kube-apiserver.yaml'
        if os.path.exists(apiserver_manifest):
            run_command(['sed', '-i', f's/--advertise-address=[0-9.]*/--advertise-address={new_ip}/', apiserver_manifest])
        
        # 2. Update etcd manifest if it exists and uses the old IP
        etcd_manifest = '/etc/kubernetes/manifests/etcd.yaml'
        if os.path.exists(etcd_manifest):
            # This is trickier as etcd uses multiple IPs for peer-urls etc.
            # But we can try to replace the listen-client-urls and advertise-client-urls
            run_command(['sed', '-i', f's/--advertise-client-urls=https:\\/\\/[0-9.]*/--advertise-client-urls=https:\\/\\/{new_ip}/', etcd_manifest])
            run_command(['sed', '-i', f's/--listen-client-urls=https:\\/\\/127.0.0.1:2379,https:\\/\\/[0-9.]*/--listen-client-urls=https:\\/\\/127.0.0.1:2379,https:\\/\\/{new_ip}/', etcd_manifest])

        # 3. Regenerate API server certificates
        # We need to remove the old ones first
        cert_dir = '/etc/kubernetes/pki'
        if os.path.exists(cert_dir):
            for f in ['apiserver.crt', 'apiserver.key']:
                p = os.path.join(cert_dir, f)
                if os.path.exists(p):
                    os.remove(p)
            
            run_command(['kubeadm', 'init', 'phase', 'certs', 'apiserver', f'--apiserver-advertise-address={new_ip}'])

        # 4. Regenerate kubeconfig
        run_command(['kubeadm', 'init', 'phase', 'kubeconfig', 'admin', f'--apiserver-advertise-address={new_ip}'])
        
        # 5. Copy new config to root and current user if possible
        admin_conf = '/etc/kubernetes/admin.conf'
        if os.path.exists(admin_conf):
            dest = '/root/.kube/config'
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            # Use run_command with cp -f to avoid interactive prompts
            run_command(['cp', '-f', admin_conf, dest])
            os.chmod(dest, 0o644)

        # 6. Restart kubelet
        run_command(['systemctl', 'restart', 'kubelet'])
        
        # Clear connectivity error cache
        from django.core.cache import cache
        from core.models import Tool
        try:
            tool = Tool.objects.get(name='k8s')
            cache.delete(f'k8s_connectivity_error_{tool.id}')
        except:
            pass
        
        return HttpResponse("Kubernetes configuration updated. Please wait a minute for components to restart.")
    except Exception as e:
        return HttpResponse(f"Repair failed: {str(e)}", status=500)
