# Install K8s with Kubeadm



### Get Certificate and Service Token for KubeROS

To grant KubeROS API to access the K3s API server, the server's CA certificate and a service account token that has enough permissions are required. 

**CA cerfiticate**
You can either read the content or use `scp` or similar command to copy the certificate. 
```bash
sudo cat /var/lib/rancher/k3s/server/tls/server-ca.crt
``` 

**Service Account Token**
Creating a service account with the Cluster Admin Role is similar to K8s. 
```bash
# Create namespace 
kubectl create namespace kuberos

# Create service account 
kubectl -n kuberos create serviceaccount kuberos-admin-sa
```

Get service account token:
```bash
# get token name
export TOKENNAME=$(kubectl -n kuberos get serviceaccount/kuberos-admin-sa -o jsonpath='{.secrets[0].name}')

# get token 
export TOKEN=$(kubectl -n kuberos get secret $TOKENNAME -o jsonpath='{.data.token}' | base64 --decode)
```

To test it, you can use: 
```bash
API_SERVER_IP=<your-api-server-ip-addresse>
TOKEN=<your token from the steps above>
curl -k -H "Authorization: Bearer $TOKEN" -X GET "https://$API_SERVER_IP:6443/api/v1/nodes" | json_pp
```
