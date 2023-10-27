# KubeROS Platform (Preview)

This repository contains the main components of the KubeROS platform, which is built on Django, with a strong community support. This platform can be easily deployed in any self-managed Kubernetes cluster, which acts as the main cluster in KubeROS.

 - **KubeROS API server**: handling API requests and interacting among various system elements.
 - **Controllers**: Monitors the system state, making necessary adjustments to maintain the desired state.
 - **Integrated hardware resource manager**:  manages the available resources and provides the system state for the schedulers and controllers

To use the platform with the `kuberos-cli` tools, please refer to the `CLI` repository: [kuberos-cli](https://github.com/kuberos-io/kuberos-cli)

Basic exmaples and explanation of the KubeROS deployment yaml file can be found here: [ROS2 Basic Examples](https://github.com/kuberos-io/ros2-basic-examples)




## Preliminary

Before installing the platform, you will need to create a Kubernetes cluster and do some configurations: 

There are different distributions of Kubernetes and also many tools are available. For users who are not very familiar with Kubernetes, we provide the following `step-by-step guide`, you can use any of them: 
    - Use `Kubeadm` manually setup the cluster: [Creating K8s with Kubeadm](/docs/k8s_with_kubeadm.md)
    - Use [Kubespray](https://kubespray.io) to automatically initialize a new cluster: 
    - Create a lightweight [K3s](https://k3s.io) cluster (Only work with FastDDS): [Creating a K3s cluster](/docs/k3s.md)

Due to the complexity and the diversity of both `ROS2` and `Kubernetes`, we recommend using `calico` as the network plugin, to support both `FastDDS` and `CycloneDDS` as the communication middleware.



## Deploy a KubeROS platform

Since the backend of KubeROS is built on Django, you can easily deploy it like a typical web backend in a Kubernetes cluster (Main cluster in your edge side).

The deployment yaml file can be found in the [`deployment`](/deployment/) directory and the installation guide is here: [Deploy KubeROS backend into a Kubernetes cluster](/docs/deploy_kuberos.md)


## Development
For development, we recommend using the DevContainer as your development environment. All required componenents such as PostgreSQL, Redis, Django are preconfigured and can be started out of box. For more details, see [`docker-compose.yaml`](/.devcontainer/docker-compose.yml)

After starting the containers for the first time, you need to create a superuser in Django and initialize the database with the following commands: 
```bash
python3 manage.py createsuperuser
python3 manage.py migrate
```

In the DevContainer, you should open two terminals and start the django dev server and celery workers for testing and debugging.
```bash
# Start dev server
./run_dev_server.sh
# Start the celery workers
cd /workspace/kuberos
celery -A settings worker -l info
# (Optional) Start beat services
celery -A settings beat -l info
```

For more details about the using of celery in KubeROS, refer to [Using Celery as Task Executor](/docs/celery.md)



## Conventions

To make the interface more clear between different components, we suggest using the following conventions throughout the development process: [Conventions in KubeROS](/docs/convention.md)


## Acknowledgments
The architectural design and initial prototype implementation is conducted as part of the project KI5GRob funded by German Federal Ministry of Education and Research (BMBF) under project number 13FH579KX9.
