kubectl delete deployments.apps kuberos-api-server-deployment
kubectl delete deployments.apps celery-worker
kubectl delete deployments.apps postgres
kubectl delete deployments.apps redis-master

kubectl delete pvc data-pv-claim
kubectl delete pvc postgres-pv-claim

kubectl delete pv postgresql-pv
kubectl delete pv data-pv

kubectl delete svc kuberos-api-server-service
kubectl delete svc postgres-service
kubectl delete svc redis-service

# TODO: Remove the data directory from the host
