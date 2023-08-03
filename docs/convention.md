# Message Conventions


To make the interface more clear between different components, we develop the KubeROS platform with following message structure convention, which will ensure the consistency and improve communication between different components. 


## Response message convention from backend. 

Typically, KubeROS use following convention: 
```python
{
    'status': 'success' | 'accepted' | 'rejected' | 'failed'
    'data' : {...} # your data 
    'errors' [
        {
            'reason': "a short reason code such as unauthorized, conflict.",
            'msg': "a descriptive message"
        },
        ...
    ]
    'msgs': ['msg1', 'msg2', '...'] # Other messages including warning, info, etc.
}
```

Among the status, 
 - **'success'**: The operation has been completed successfully. 
 - **'accepted'**:  The request has been received and is being processed, but it has not yet been completed. Some operations, like deploy, might take a longer time to complete. You can check the result with kuberos.py deployment status <deployment_name>.
 - **'rejected'**: The request is properly formatted but was rejected due to a lack of appropriate permissions or due to a conflict with existed data.
 - **'failed'**: The operation could not be completed due to an error. Detailed error messages can be found in the err_msgs field.


 ## Response from celery tasks 