# Batch Job Deployment

This deployment mode is primarily designed for large-scale evaluations with simulation. For instance, if you want to test your software stack for different scenarios within a simulation, you may wish to test various combination of underlying algorithms and parameters.

KubeROS provide the `Batch Job Deployment` to meet this demand. Modifzing the existed `Rosmodule` which is already containerized for use in in production environments, is not necessary. You only need to add a `JobSpec` to your deployment manifest. KubeROS will attempt to use all of authorized resources, even from multi-clusters, to complete this large batch of jobs. 


## Why don't use Job resource in native Kubernetes. 
 - An application contains serveral pods
 - Each Job in the context of robotics usually requires a substantial amount of resources -> Even One `Job` per `Node`. 
 - Jobs must be scheduled based on the current status.
 - Provides a persistent volume to store the results and an interface for the evalutation module to directly access the data.

## JobSpec

Definition of `JobSpec`




### BatchJobDeployment Status
 - **Pending**


### Job Status
 - **Pending**: 

