# Using K3s as Underlying Orchestration Framework 

[K3s](https://k3s.io) is a certified lightweight Kubernetes distribution for IoT & Edge computing. It is easy to install and uses half the memory.


### Installation

Compared to the native Kubernetes, the installation of K3s is very easy. It provides an installation script to install it in a convenient way. 

To install the server (Master node):
```
curl -sfL https://get.k3s.io | sh -
```

To install the agent (Worker nodes): 
```
curl -sfL https://get.k3s.io | K3S_URL=https://<server-ip>:6443 K3S_TOKEN=<server-node-token> sh -
```
Replace the `<server-ip>` and `<server-node-token>` which is stored at `/var/lib/rancher/k3s/server/node-token` on the master node.



### Post-Installation - Using Kubectl
To use `kubetl` to inspect the cluster directly without `sudo`, you can do the following 

```
# Copy the config file `k3s.yml` to the user's home directory 
sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/config/k3s.yaml

# Change the owner 
sudo chown $USER ~/.kube/config/k3s.yaml
sudo chmod 600 ~/.kube/config/k3s.yaml

# set this config as the default for kubectl
export KUBECONFIG=~/.kube/config/k3s.yaml

# Optional, add this to `bashrc` or `bash_profile`
echo "KUBECONFIG=~/.kube/config/k3s.yaml" >> ~/.bashrc
```

**Enable shell autocompletion**: 
kubectl provides autocompletions support for Bash, Zsh, Fish and Powershell. 


```
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