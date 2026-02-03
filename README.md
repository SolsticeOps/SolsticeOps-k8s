<div align="center">
    <picture>
        <source
            srcset="https://raw.githubusercontent.com/SolsticeOps/SolsticeOps-core/refs/heads/main/docs/images/logo_dark.png"
            media="(prefers-color-scheme: light), (prefers-color-scheme: no-preference)"
        />
        <source
            srcset="https://raw.githubusercontent.com/SolsticeOps/SolsticeOps-core/refs/heads/main/docs/images/logo_light.png"
            media="(prefers-color-scheme: dark)"
        />
        <img src="https://raw.githubusercontent.com/SolsticeOps/SolsticeOps-core/refs/heads/main/docs/images/logo_light.png" />
    </picture>
</div>

# SolsticeOps-k8s

Kubernetes management module for SolsticeOps.

[Русская версия](README-ru_RU.md)

## Features
- Pod management and logs
- Node overview
- Namespace filtering
- Terminal access to pods (via kubectl exec)
- Cluster status overview

## Installation
Add as a submodule to SolsticeOps-core:
```bash
git submodule add https://github.com/SolsticeOps/SolsticeOps-k8s.git modules/k8s
pip install -r modules/k8s/requirements.txt
```
