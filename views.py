import subprocess
import os
import yaml
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
try:
    from kubernetes import client as k8s_client, config as k8s_config
    K8S_AVAILABLE = True
except ImportError:
    K8S_AVAILABLE = False

@login_required
def k8s_pod_logs(request, namespace, pod_name):
    if not K8S_AVAILABLE:
        return HttpResponse("K8s not available", status=500)
    try:
        k8s_config.load_kube_config()
        v1 = k8s_client.CoreV1Api()
        logs = v1.read_namespaced_pod_log(name=pod_name, namespace=namespace, tail_lines=200)
        return HttpResponse(logs, content_type='text/plain')
    except Exception as e:
        return HttpResponse(f"Error: {str(e)}", status=500)

@login_required
def k8s_pod_logs_download(request, namespace, pod_name):
    if not K8S_AVAILABLE:
        return HttpResponse("K8s not available", status=500)
    try:
        k8s_config.load_kube_config()
        v1 = k8s_client.CoreV1Api()
        logs = v1.read_namespaced_pod_log(name=pod_name, namespace=namespace)
        response = HttpResponse(logs, content_type='text/plain')
        response['Content-Disposition'] = f'attachment; filename="pod_{pod_name}_logs.log"'
        return response
    except Exception as e:
        return HttpResponse(f"Error downloading pod logs: {str(e)}", status=500)

@login_required
def k8s_pod_action(request, namespace, pod_name, action):
    if not K8S_AVAILABLE:
        return redirect('tool_detail', tool_name='k8s')
    try:
        k8s_config.load_kube_config()
        v1 = k8s_client.CoreV1Api()
        if action == 'delete':
            v1.delete_namespaced_pod(name=pod_name, namespace=namespace)
    except Exception as e:
        pass
    
    return redirect('tool_detail', tool_name='k8s')

@login_required
def k8s_deployment_scale(request, namespace, name, replicas):
    if not K8S_AVAILABLE:
        return HttpResponse("K8s not available", status=500)
    try:
        k8s_config.load_kube_config()
        apps_v1 = k8s_client.AppsV1Api()
        body = {'spec': {'replicas': int(replicas)}}
        apps_v1.patch_namespaced_deployment_scale(name=name, namespace=namespace, body=body)
        return redirect('tool_detail', tool_name='k8s')
    except Exception as e:
        return HttpResponse(str(e), status=500)

@login_required
def k8s_deployment_restart(request, namespace, name):
    if not K8S_AVAILABLE:
        return HttpResponse("K8s not available", status=500)
    try:
        k8s_config.load_kube_config()
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
    if not K8S_AVAILABLE:
        return HttpResponse("K8s not available", status=500)
    try:
        cmd = ['kubectl', 'describe', resource_type, name]
        if namespace:
            cmd.extend(['-n', namespace])
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode()
        return HttpResponse(output)
    except Exception as e:
        return HttpResponse(str(e), status=500)

@login_required
def k8s_resource_yaml(request, resource_type, namespace, name):
    if not K8S_AVAILABLE:
        return HttpResponse("K8s not available", status=500)
    
    k8s_config.load_kube_config()
    
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
                process = subprocess.Popen(
                    ['kubectl', 'apply', '-f', '-'],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                stdout, stderr = process.communicate(input=new_yaml_str)
                
                if process.returncode == 0:
                    return HttpResponse("Resource updated successfully.", status=200)
                else:
                    return HttpResponse(f"Update failed: {stderr}", status=400)
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
            env = os.environ.copy()
            output = subprocess.check_output(full_command, shell=True, stderr=subprocess.STDOUT, env=env).decode()
            return HttpResponse(f"{display_prompt}\n{output}")
        except subprocess.CalledProcessError as e:
            return HttpResponse(f"{display_prompt}\nError: {e.output.decode()}")
        except Exception as e:
            return HttpResponse(f"Error: {str(e)}")
    return HttpResponse("Invalid request", status=400)

@login_required
def k8s_pod_shell(request, namespace, pod_name):
    return HttpResponse("Shell initialised")

@login_required
def k8s_service_logs(request):
    try:
        # Try journalctl without sudo first
        try:
            output = subprocess.check_output(['journalctl', '-u', 'kubelet', '-n', '200', '--no-pager'], stderr=subprocess.STDOUT).decode()
            if "Hint: You are currently not seeing messages" in output:
                raise subprocess.CalledProcessError(1, 'journalctl')
        except (subprocess.CalledProcessError, FileNotFoundError):
            # Fallback to sudo if the first one fails or is restricted
            output = subprocess.check_output(['sudo', '-n', 'journalctl', '-u', 'kubelet', '-n', '200', '--no-pager'], stderr=subprocess.STDOUT).decode()
        
        if not output.strip() or "No entries" in output:
            return HttpResponse("No log entries found. Ensure the 'kubelet' service is running and you have permissions to view logs (group 'systemd-journal' or 'adm').", content_type='text/plain')

        return HttpResponse(output, content_type='text/plain')
    except Exception as e:
        return HttpResponse(f"Error fetching system logs: {str(e)}", status=500)

@login_required
def k8s_service_logs_download(request):
    try:
        # Try journalctl without sudo first
        try:
            output = subprocess.check_output(['journalctl', '-u', 'kubelet', '--no-pager'], stderr=subprocess.STDOUT).decode()
            if "Hint: You are currently not seeing messages" in output:
                raise subprocess.CalledProcessError(1, 'journalctl')
        except (subprocess.CalledProcessError, FileNotFoundError):
            # Fallback to sudo if the first one fails or is restricted
            output = subprocess.check_output(['sudo', '-n', 'journalctl', '-u', 'kubelet', '--no-pager'], stderr=subprocess.STDOUT).decode()
        
        response = HttpResponse(output, content_type='text/plain')
        response['Content-Disposition'] = 'attachment; filename="k8s_service_logs.log"'
        return response
    except Exception as e:
        return HttpResponse(f"Error downloading system logs: {str(e)}", status=500)
