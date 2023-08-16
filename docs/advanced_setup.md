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

### Install K9s

[K9s](https://k9scli.io) provides a terminal based UI to simplify the interacton with Kubernetes clusters. 

Install on Linux (amd64)
```
wget https://github.com/derailed/k9s/releases/download/v0.27.4/k9s_Linux_amd64.tar.gz
tar -xvf k9s_Linux_amd64.tar.gz
sudo mv k9s /usr/bin
```