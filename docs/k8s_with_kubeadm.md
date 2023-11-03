# Using K8s as Underlying Orchestration Framework 


## Install with Kubeadm

Installing and configuring a Kubernetes cluster is a challenging and not straightforward process due to its complexity, compability, and diversity in terms of container runtimes and container network interface (CNI) plugins. In this document, we provide a brief guide to get you up and running with a Kubernetes cluster as quickly as possible. For more details, please refer to the Kubernetes. [KubeAdm documents](https://kubernetes.io/docs/setup/production-environment/tools/kubeadm/install-kubeadm/).


### Tested Software Version

 - **OS**: Ubuntu 20.04 / Ubuntu 22.04
 - **Containerd.io**: v1.6.22
 - **Kubernetes**: v1.27.4 - [Docs](https://v1-27.docs.kubernetes.io/docs/setup/production-environment/tools/kubeadm/create-cluster-kubeadm/)
 - **Calico**: v3.25.1 - [Docs](https://docs.tigera.io/calico/3.25/getting-started/kubernetes/self-managed-onprem/onpremises)

### Prerequisite:

 - 2 machines running Linux: Ubuntu 20.04 or Ubuntu 22.04
 - Full network connectivity between all machines on the local network
 - Internet access to download resources and pull images
 - Port 6443 for the API server on the master node is open, quick check with `nc 127.0.0.1 6443`, you should get an empty output.
 - (Optional) If you are hosting a cluster with strict network boundaries, please make sure that certain ports used by K8s components are configured correctly, see docs:[Ports and Protocols](https://kubernetes.io/docs/reference/networking/ports-and-protocols/)


### Disable Swap
The Linux Swap **MUST** be disabled in order for the kubelet to work properly!

To temporarily disable it:
```bash
sudo swapoff -a
```
To persistent disable it
```bash
sudo nano /etc/fstab
```
Comment out the line that starts with `/swap`
```bash
# /swapfile                      none            swap    sw              0       0
```
Reboot to disable swap or use `sudo swapoff -a`


### Install Container Runtime (Containerd)
Kubernetes versions after v1.25 don't integrate the Docker Engine using the component named `dockershim`. You need to install a container runtime that complies with the Container Runtime Interface (CRI) on each node. There are serveral options, see [Container Runtimes](https://kubernetes.io/docs/setup/production-environment/container-runtimes/).

In this document, we choose `Containerd` as the container runtime and install it with `apt-get`, for more installation method, refer to [`Gettin stared with containerd`](https://github.com/containerd/containerd/blob/main/docs/getting-started.md). 

The `containerd.io` pakcages in debian are distributed by Docker (not by the containerd project). We follow the [Docker documentation](https://docs.docker.com/engine/install/ubuntu/) to set up `apt-get` and install `containerd.io`.


#### Prerequisites

Setup and load two kernel modules: 
```bash
cat <<EOF | sudo tee /etc/modules-load.d/k8s.conf
overlay
br_netfilter
EOF
# Enable it immediately
sudo modprobe overlay
sudo modprobe br_netfilter
```
 - The purpose of `modules-load.d` configurations is to specify kernel modules to load at boot time.
 - **overlay** is for the overlay network filesystem which allows mounting a filesystem on top of another filesystem. In Kubernetes, the overlay network is a common type of network that allows pods to communicate. It is not required when using Calico. While Calico does not use the overlay network mechanism by default (it uses unencapsulated routing), it doesn't harm to have the overlay module loaded. 
 - **br_netfilter** is for the bridge netfilter, which allows for iptables/nftables rules to bridge traffic.

Verify that the `br_netfilter`, `overlay` modules are loaded:
```bash
lsmod | grep br_netfilter
lsmod | grep overlay
```

Configure sysctl parameters
```bash
# sysctl params required by setup, params persist across reboots
cat <<EOF | sudo tee /etc/sysctl.d/k8s.conf
net.bridge.bridge-nf-call-iptables  = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward                 = 1
EOF

# Apply sysctl params without reboot
sudo sysctl --system
```

Verify: 
```bash
sysctl net.bridge.bridge-nf-call-iptables net.bridge.bridge-nf-call-ip6tables net.ipv4.ip_forward
```


#### Install containerd using apt repository
 - setup the repository:
```bash
# install prerequisite packages
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg

# Add official GPG key
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# setup the repository
echo \
  "deb [arch="$(dpkg --print-architecture)" signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  "$(. /etc/os-release && echo "$VERSION_CODENAME")" stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
```
 - Install containerd. Docker Engine components such as `docker-ce`, `docker-ce-cli` are not needed
```bash
sudo apt-get update
sudo apt-get install -y containerd.io
```

Please following the upate-to-date [docker documentation](https://docs.docker.com/engine/install/ubuntu/), if you have problem with the above commands, due to changes such as GPG key, etc..


#### Configuring the `systemd` cgroup driver
Since we installed `containerd` from a Debian package, the CRI integration plugin is disabled by default. CRI support is required for Kubelet to interact with it. For more details see[Customizing containerd](https://github.com/containerd/containerd/blob/main/docs/getting-started.md#advanced-topics). 

```bash
sudo su -
rm /etc/containerd/config.toml
containerd config default>/etc/containerd/config.toml
```

Set the `SystemdCgroup` as true in `/etc/containerd/config.toml` with `runc`
```bash
[plugins."io.containerd.grpc.v1.cri".containerd.runtimes.runc]
  ...
  [plugins."io.containerd.grpc.v1.cri".containerd.runtimes.runc.options]
    SystemdCgroup = true
```

Restart and enable to run at startup
```bash
sudo systemctl restart containerd
sudo systemctl enable containerd
```




### Install Kubeadm
You will install following packages on all of your machines, more detail on [Kubernetes kubeadm v1.27](https://v1-27.docs.kubernetes.io/docs/setup/production-environment/tools/kubeadm/create-cluster-kubeadm/)

 - **kubeadm**: the command to bootstrap the cluster.

 - **kubelet**: the component that runs on all of the machines in your cluster and does things like starting pods and containers.

 - **kubectl**: the command line util to talk to your cluster.

This instruction has only been tested for v1.27.

Install required packages
```bash
sudo apt-get update
# apt-transport-https may be a dummy package; if so, you can skip that package
sudo apt-get install -y apt-transport-https ca-certificates curl
```
Download public signing key
```bash
curl -fsSL https://dl.k8s.io/apt/doc/apt-key.gpg | sudo gpg --dearmor -o /etc/apt/keyrings/kubernetes-archive-keyring.gpg
```
Add Kubernetes apt repository
```bash
# This overwrites any existing configuration in /etc/apt/sources.list.d/kubernetes.list
echo "deb [signed-by=/etc/apt/keyrings/kubernetes-archive-keyring.gpg] https://apt.kubernetes.io/ kubernetes-xenial main" | sudo tee /etc/apt/sources.list.d/kubernetes.list
```
Install kubeadm, kubelet, kubectl
```bash
sudo apt-get update
# check available versions
apt-cache policy kubelet
# Install
export KUBE_VERSION=1.27.4-00
sudo apt-get install -y kubelet=$KUBE_VERSION kubeadm=$KUBE_VERSION kubectl=$KUBE_VERSION
sudo apt-mark hold kubelet kubeadm kubectl
```


### Initialize the cluster 
```bash
sudo kubeadm init --pod-network-cidr=192.168.0.0/16 --control-plane-endpoint xx.xx.xx.xx
# Unknown error, when the pod-network-cidr is not specified
```
Copy the admin.conf to your local home directory and allow regular users to run `kubectl` without sudo permissions. 
```bash
mkdir -p $HOME/.kube
sudo cp -i /etc/kubernetes/admin.conf $HOME/.kube/config
sudo chown $(id -u):$(id -g) $HOME/.kube/config
```

Check the cluster's `ConfigMap`:
```bash
kubectl get cm -n kube-system kubeadm-config -o=jsonpath='{.data.ClusterConfiguration}'
```

Get join command after expiration (24 hours) 
```bash
kubeadm token create --print-join-command
```


### Install Calico as CNI-Plugin

For more details, see [installing calico for on-premise deployment](https://docs.tigera.io/calico/3.25/getting-started/kubernetes/self-managed-onprem/onpremises)

This is only a quick install guide for v3.25.1

Install the operator on the cluster 
```bash
kubectl create -f https://raw.githubusercontent.com/projectcalico/calico/v3.25.1/manifests/tigera-operator.yaml
```

Download the custom resources: 
```bash
curl https://raw.githubusercontent.com/projectcalico/calico/v3.25.1/manifests/custom-resources.yaml -O
```
You can change the settings before applying them to the cluster.
**IMPORTANT**: change encapsulation to VXLAN, otherwise unknown communication error by distributed ROS deployment
```t
encapsulation: VXLAN
```
```bash
kubectl create -f custom-resources.yaml
```


### Install bash-completion
Intall bash-completion
```bash
sudo apt-get update
sudo apt-get install -y bash-completion
```
Source in `.bashrc`
```bash
echo 'source <(kubectl completion bash)' >>~/.bashrc
```

Setup alias
```bash
echo 'alias k=kubectl' >>~/.bashrc
echo 'complete -o default -F __start_kubectl k' >>~/.bashrc
```


### Setup proxy



## Post-Setup for KubeROS
The following information is required to add a new cluster to KubeROS 
 - CA certificate 
 - API server address
 - Service account with cluster admin role (or namespace)
 - Service account token

### Get Certificate and Service Token for KubeROS

To grant KubeROS API to access the K3s API server, the server's CA certificate and a service account token that has enough permissions are required. 

**CA cerfiticate**
You can either read the content or use `scp` or similar command to copy the certificate. If you are setting up the cluster through SSH, the easiest way is to copy the printed content to your local machine.
```bash
sudo cat /etc/kubernetes/pki/ca.crt
sudo cp /etc/kubernetes/pki/ca.crt ~/k8s_ca.crt # this file will be uploaded to KubeROS
```


**Check Cluster Info**
You can get and check the API server url using:
```bash
kubectl cluster-info
# Output
Kubernetes control plane is running at https://<k8s-api-sever-address>:6443
```

**Service Account with Cluster Admin Role**
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

Get service account token:
```bash
export TOKENNAME=kuberos-admin-sa-token
export TOKEN=$(kubectl -n kuberos get secret $TOKENNAME -o jsonpath='{.data.token}' | base64 --decode)
echo $TOKEN  # put this token in the KubeROS registration YAML
```

To test it, you can use: 
```bash
export API_SERVER_IP=<your-api-server-ip-addresse>
export TOKEN=<your token from the steps above>
curl -k -H "Authorization: Bearer $TOKEN" -X GET "https://$API_SERVER_IP:6443/api/v1/nodes" | json_pp
```


### Preparing the YAML File for Cluster Registration in KubeROS 

Registration YAML file definition: 
```yaml
apiVersion: v1alpha
kind: ClusterRegistration
metadata:
  name: <kubernetes_cluster_name>
  clusterType: k8s
  description: 'Short description'
  apiServer: https://<K8s-api-server-addresse>:6443
  caCert: ~/k8s_ca.crt # <path to cluster_ca.crt> # Change the corresponed path
  serviceTokenAdmin: eyJhbGciOiJSUzI1NiIsImtxxxxxxxxxxx # Token from the steps above
```


### K8s Commands 

 - print the `join` command for new worker node

 ```bash
 kubeadm token create --print-join-command
 ```