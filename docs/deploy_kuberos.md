# Deploy KubeROS

This document gives you a quick guide to deploy KubeROS in your organization in Kubernetes on-premises. 

All you need is a running Kubernetes cluster. 

Currently, KubeROS doesn't support deployment in the K3s cluster due to a limitations of K3s.



## Deploy in Kubernetes for Testing

At the current stage of development, we are using multiple yaml files instead of one `all-in-one.yaml'. 

All pods are deployed on the master node using node selector. A directory on the host is used for persistent storage. 

You can use `kubectl apply -f' to deploy the following resources in the cluster
 
 - To add a temporary Docker Hub registry token to pull the Kuberos image, use the command in the file `temp_registry_credential`

 - Label the master node
If you have only one local K8s cluster, we recommend deploying all KubeROS components on the master node to improve communication between the KubeROS API server and the Kubernetes API server.

```bash
export MASTER_NODE=<node-name>
kubectl label node $MASTER_NODE kuberos.io/kuberos=kuberos-control-plane
# check it: 
kubectl get no --show-labels
```

 - Create a persistent volume claim (pvc) and a persistent volume (pc) for the Postgresql database and for storing static files. 
 Replace the **hostpath** before applying
```bash
# Replace the hostpath in the PersistentVolume resource, then
kubectl apply -f pv-pvc-kuberos.yaml
```

 - Deploy postgresql and redis pods
```bash
# Replace the nodeSeletor in both yaml file, then
kubectl apply -f redis.yaml
kubectl apply -f postgres.yaml
```

 - Deploy KubeROS api server
```bash
# Modify the ENV DJANGO_ALLOWED_HOSTS -> TODO use configmap
# Replace the nodeSeletor, then
kubectl apply -f kuberos.yaml
```

 - Deploy Celery workers
```bash
# replace nodeSelector
kubectl apply -f celery-workers.yaml
```


## Update and Delete for Testing

You only need to update the `kuberos-api-server` and `celery-workers` deployments. 

```bash
# Apply the modified deployment yaml 
kubectl apply -f kuberos.yaml
kuberos apply -f celery-workers.yaml
```




## Deploy in Kubernetes for Production Use
For use in a production environment, we have to provide a more professional delivery pipeline. Now it is not the main focus.
