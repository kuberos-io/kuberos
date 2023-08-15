# Using K3s as Underlying Orchestration Framework 

[K3s](https://k3s.io) is a certified lightweight Kubernetes distribution for IoT & Edge computing. It is easy to install and uses half the memory.


### Installation

Compared to the native Kubernetes, the installation of K3s is very easy. It provides an installation script to install it in a convenient way. 

To install the server (Master node):
```bash
curl -sfL https://get.k3s.io | sh -
```

To install the agent (Worker nodes): 
```bash
curl -sfL https://get.k3s.io | K3S_URL=https://<server-ip>:6443 K3S_TOKEN=<server-node-token> sh -
```
Replace the `<server-ip>` and `<server-node-token>` which is stored at `/var/lib/rancher/k3s/server/node-token` on the master node.



### Post-Installation - Using Kubectl
To use `kubetl` to inspect the cluster directly without `sudo`, you can do the following 

```bash
# Copy the config file `k3s.yml` to the user's home directory 
sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/config/k3s.yaml

# Change the owner 
sudo chown $USER ~/.kube/config/k3s.yaml
sudo chmod 600 ~/.kube/config/k3s.yaml

# set this config as the default for kubectl
export KUBECONFIG=~/.kube/config/k3s.yaml

# Optional, add this to `bashrc` or `bash_profile`
echo "export KUBECONFIG=~/.kube/config/k3s.yaml" >> ~/.bashrc
```

**Enable shell autocompletion**: 
kubectl provides autocompletions support for Bash, Zsh, Fish and Powershell. 


```bash
# Install bash-completion
apt-get install bash-completion

# Enalble kubectl autocompletion (Bash)
echo 'source <(kubectl completion bash)' >> ~/.bashrc

# Add alias for kubectl
echo 'alias k=kubectl' >>~/.bashrc
echo 'complete -o default -F __start_kubectl k' >>~/.bashrc
```



### Proxy-Setup
If you're on a network behind a proxy, you'll need to configure the container runtime to use the proxy server to access the Internet to download images.



### Get Certificate and Service Token for KubeROS 
To grant KubeROS API to access the K3s API server, the server's CA certificate and a service account token that has enough permissions are required. 

**CA cerfiticate**
You can either read the content or use `scp` or similar command to copy the certificate. 
```bash
sudo cat /var/lib/rancher/k3s/server/tls/server-ca.crt
``` 

**Service Account**
Creating a service account with the Cluster Admin Role is similar to K8s. 
```bash
# Create namespace 
kubectl create namespace kuberos

# Create service account 
kubectl -n kuberos create serviceaccount kuberos-admin-sa

# Create cluster role binding
kubectl create clusterrolebinding kuberos-admin-rolebinding -n kuberos --clusterrole=cluster-admin --serviceaccount=kuberos:kuberos-admin-sa
```

**Service Account Token (Long-lived)**
Before K8s 1.24, creating a new service account creates a persistent token by default. Due to security and scalability concerns, no token is appended after 1.24. To create a long-lived service token, you can use:
```bash
kubectl apply -f - <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: kuberos-admin-sa-token
  namespace: kuberos
  annotations:
    kubernetes.io/service-account.name: kuberos-admin-sa
type: kubernetes.io/service-account-token
EOF
```

The token can be retrieved: 
```bash
kubectl describe secrets -n kuberos kuberos-admin-sa-token
```

**Service Account Token (time-bound)**
Starting with version 1.22, Kubernetes introduced the `TokenRequest` API to generate a token that expires after one hour by default.
```bash
kubectl create token kuberos-admin-sa -n kuberos
```

In k3s, you can also get the token by using followng command: 
```bash
sudo k3s kubectl -n kuberos create token kuberos-admin-sa --duration=0s
```

Note that, the token created by this method, cannot be retrieved with `kubectl get token -n kuberos` and cannot be displayed with `kubectl describe -n kuberos kuberos-admin-sa` 
```bash
Name:                kuberos-admin-sa
Namespace:           kuberos
Labels:              <none>
Annotations:         <none>
Image pull secrets:  <none>
Mountable secrets:   <none>
Tokens:              <none> 
Events:              <none>
```

To **check** it, you can use: 
```bash
export API_SERVER_IP=<your-api-server-ip-addresse>
export TOKEN=your token from the steps above>
curl -k -H "Authorization: Bearer $TOKEN" -X GET "https://$API_SERVER_IP:6443/api/v1/nodes" | json_pp
echo $TOKEN #  # put this token in the KubeROS registration YAML
```

Here is a link for further information to unserstand Kubernetes service accounts: *[Link](https://medium.com/@th3b3ginn3r/understanding-service-accounts-in-kubernetes-e9d2abe19df8)*



### Preparing the YAML File for Cluster Registration in KubeROS 

Registration YAML file definition: 
```yaml
apiVersion: v1alpha
kind: ClusterRegistration
metadata:
  name: <kubernetes_cluster_name>
  clusterType: k3s
  description: 'Short description'
  apiServer: https://<K3s-api-server-addresse>:6443
  caCert: <path to cluster_ca.crt>
  serviceTokenAdmin: eyJhbGciOiJSUzI1NiIsImtxxxxxxxxxxx
```


### Issues
 - [ ] Service account token expires automatically in about 1 hour.