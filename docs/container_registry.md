# Use a Private Registry

If your container images are stored in a private registry, the Kubernetes cluster uses the [secret](https://kubernetes.io/docs/concepts/configuration/secret/) of type `kubernetes.io/dockerconfigjson` to pull the private images. 

Instead of [manual setup process](https://kubernetes.io/docs/tasks/configure-pod-container/pull-image-private-registry/) directly in the cluster, KubeROS provides an API group `registry_token` to allow you to upload your access token to the platform. With a single command `kuberos registry_token attach` you can easily add the secret to the clusters managed by KubeROS.

To use one or more private registries in a deployment, you can add the `containerRegistry` to the deployment manifest as follows

```YAML
containerRegistry:

  - name: default
    imagePullSecretName: 'kuberos-registry-token-default'
    imagePullPolicy: 'Always'

  - name: second-registry
    imagePullSecretName: 'second-registry-token'
    imagePullPolicy: 'IfNotPresent'
```

If this attribute is not specified, KubeROS will pull the image from the public DockerHub. If you are using multiple private registries for different ROSModules, you need to specify the `containerRegistryName` in your ROSModule, such as:

```YAML
name: rosmodule-name
    image: <private-registry-url>/ros2-basic-examples:v2-param
    containerRegistryName: default # Optional, if not specified, use the default registry
    entrypoint: ["ros2 launch pkg xxx.launch.py"]
```

## Add an Access Token to KubeROS
As with the creation of other resources, you can use the following YAML file template:

```YAML
apiVersion: v1alpha
kind: RegistryToken
metadata:
  name: <token name in the cluster>
  userName: 'user name in you container registry'
  registryUrl: <registry url>
  token: <token>
  description: 'Test token'
```

Be careful, you should delete this file immediately after a successful import. The purpose of this YAML is **only** to provide a readable template instead of a long terminal command.

With this template you can use KubeROS:

```bash
kuberos.py registry_token create -f <path-to-yaml-file>
```

Also, for security reasons, KuROS doesn't provide an interface that allows you to read this token again. If the token doesn't work, you have to delete it and import it again with the correct token.

## Attach the Token to Kubernetes

Currently, you need to tell KubeROS which Kubernetes cluster you want to use this token in.

```bash
kuberos.py registry_token attach --cluster=<cluster-name-in-kuberos> --token=<token-name-in-kuberos>
```

Before sending the request, you can check the `cluster-name' and `token-name' with the following commands:

```bash
# check the token name
kuberos.py registry_token list
# check the cluster name
kuberos.py cluster list
```

## TODOs
 - [ ] Error handling in the processing of the request
 - [ ] Add an interface to delete the attached secrets in the cluster
 - [ ] Add an interface to update the secrets
 