# Using K8s as Underlying Orchestration Framework 


### Install with KubeAdm

### Install with Kubespray

### Setup proxy


### Get Certificate and Service Token for KubeROS

To grant KubeROS API to access the K3s API server, the server's CA certificate and a service account token that has enough permissions are required. 

**CA cerfiticate**
You can either read the content or use `scp` or similar command to copy the certificate. 
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
  serviceTokenAdmin: eyJhbGciOiJSUzI1NiIsImtxxxxxxxxxxx # Token from the steps about
```
