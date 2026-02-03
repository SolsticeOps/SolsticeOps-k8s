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
