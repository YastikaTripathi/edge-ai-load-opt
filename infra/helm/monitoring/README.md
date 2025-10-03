# Monitoring Install
```bash
kubectl create namespace monitoring
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
helm install kps prometheus-community/kube-prometheus-stack -n monitoring       --set grafana.service.type=NodePort       --set grafana.service.nodePort=30000
```
