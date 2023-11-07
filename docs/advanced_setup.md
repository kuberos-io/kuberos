# Useful Commands to Setup and Configure the Machines 



### Set the hostnames

If you want change the hostname after installing for more clearity in the cluster. Use follow command: 
```bash
sudo hostnamectl set-hostname <new-hostname>
```
Update the `/etc/hosts` file: 
```bash
sudo nano /etc/hosts
```
Add following at the bottom:
```
<control-plane-node-name> IP_ADDRESS
<worker-node-1-name> IP_ADDRESS
```

### Setting default namespace 
```bash
kubectl config set-context --current --namespace=ros-default
```

### Install K9s

[K9s](https://k9scli.io) provides a terminal based UI to simplify the interacton with Kubernetes clusters. 

Install on Linux (amd64)
```
wget https://github.com/derailed/k9s/releases/download/v0.27.4/k9s_Linux_amd64.tar.gz
tar -xvf k9s_Linux_amd64.tar.gz
sudo mv k9s /usr/bin
```


### Metrics Server 

Get the latest deployment yaml file from [kubernetes-sigs/metrics-server](https://github.com/kubernetes-sigs/metrics-server)

To disable the certificate validation for using in the local network, add the `- --kubelet-insecure-tls` in container args as follow: 

```YAML
apiVersion: apps/v1
kind: Deployment
metadata:
  labels:
    k8s-app: metrics-server
  name: metrics-server
  namespace: kube-system
spec:
  selector:
    matchLabels:
      k8s-app: metrics-server
  strategy:
    rollingUpdate:
      maxUnavailable: 0
  template:
    metadata:
      labels:
        k8s-app: metrics-server
    spec:
      containers:
      - args:
        - --cert-dir=/tmp
        - --secure-port=4443
        - --kubelet-preferred-address-types=InternalIP,ExternalIP,Hostname
        - --kubelet-use-node-status-port
        - --metric-resolution=15s
        - --kubelet-insecure-tls  ## Add this line
        image: registry.k8s.io/metrics-server/metrics-server:v0.6.4
        imagePullPolicy: IfNotPresent
        livenessProbe:
          failureThreshold: 3
          httpGet:
            path: /livez
```
