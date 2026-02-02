from django.apps import AppConfig

class K8sConfig(AppConfig):
    name = 'modules.k8s'
    label = 'k8s_module'
    verbose_name = 'Kubernetes Module'
