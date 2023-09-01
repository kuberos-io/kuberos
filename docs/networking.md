# Networking 


### Manual assign IP address to pod

Reserve the ip addresses for manual assiging with the [IP reserveration resource](https://docs.tigera.io/calico/latest/reference/resources/ipreservation)


```yaml
apiVersion: projectcalico.org/v3
kind: IPReservation
metadata:
  name: my-ipreservation-1
spec:
  reservedCIDRs:
    - 192.168.2.3/24
    - 10.0.2.3/32
    - cafe:f00d::/123
```

Add annotation for the pod: 
```yaml
  "cni.projectcalico.org/ipAddrs": "[\"192.168.2.78\"]"
```


