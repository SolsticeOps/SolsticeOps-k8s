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

Модуль управления Kubernetes для SolsticeOps.

[English Version](README.md)

## Возможности
- Управление подами и логи
- Обзор узлов
- Фильтрация по пространствам имен (namespaces)
- Доступ к терминалу подов (через kubectl exec)
- Обзор статуса кластера

## Установка
Добавьте как субмодуль в SolsticeOps-core:
```bash
git submodule add https://github.com/SolsticeOps/SolsticeOps-k8s.git modules/k8s
pip install -r modules/k8s/requirements.txt
```
