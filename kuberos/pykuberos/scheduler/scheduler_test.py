from .scheduler import KuberosScheduler


fleet = {
    "name": "bw0-fleet",
    "uuid": "80bb0142-e522-420d-864e-b162cc844e65",
    "created_by": 2,
    "created_time": "2023-04-18T07:25:33.950616Z",
    "modified_time": "2023-04-18T07:25:33.950642Z",
    "active": True,
    "description": 'Null',
    "k8s_main_cluster": "f5e8878d-a271-4e30-8dae-4c6f16916a41",
    "fleet_node_set": [
        {
            "name": "dummy-1",
            "uuid": "b6be48fb-b173-4a68-ac3c-3bba86433e0f",
            "cluster_node": "92bd39c6-ef88-4865-a15c-d21e9b53d631",
            "node_type": "onboard",
            "shared_resource": False,
            "status": "deployable"
        },
        {
            "name": "dummy-2",
            "uuid": "1b2e5918-aa55-40e8-95c1-0a48f0090257",
            "cluster_node": "633a26cb-2742-4297-908c-e24e2af42228",
            "node_type": "onboard",
            "shared_resource": False,
            "status": "deployable"
        }
    ]
}

