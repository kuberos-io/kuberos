# Using K3s as Underlying Orchestration Framework 



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

Enable shell autocompletion: 
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