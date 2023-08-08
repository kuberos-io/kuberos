kubectl apply -f pg-pv-pvc.yaml
kubectl apply -f data-pv-pvc.yaml

kubectl apply -f redis.yaml 
kubectl apply -f postgres.yaml

kubectl apply -f kuberos.yaml
kubectl apply -f celery-workers.yaml
