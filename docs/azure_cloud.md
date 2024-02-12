## Azure

## Create AKS

```bash

az account set --subscription <subscription-id>

az aks create -n <cluster-name> -g <resource-group> --location <localtion> --network-plugin kubenet --network-plugin-mode calico --pod-cidr 192.168.0.0/16 --node-count 1 --node-vm-size Standard_B2s --generate-ssh-keys

# get ca.crt
kubectl config view --minify --raw --output 'jsonpath={..cluster.certificate-authority-data}' | base64 -d | openssl x509 -text -out -
```


Check locations and available VM sizes: 
```bash

az vm list-sizes --location <location> -o table

az aks get-versions --location <location> -o table


```