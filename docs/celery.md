# Using Celery for Asynchronous Task Execution 

KubeROS uses Celery to perform the tasks that actually interact with the Kubernetes API server. 

KubeROS from its design aims to manage multiple Kubernetes clusters (support different distributions), and can be used in large scale. 

We use Celery to distribute the actual workload to interact with different Kubernetes API server, so that the KubeROS API can better handle concurrent requests without performance degradation even at large scale. In addition, we use Celery to schedule the periodic task execution to synchronize the cluster status, monitor the deployed ROS 2 application, and trigger rescheduling in an advanced mode.


### Celery Basics: 

Celery is an asynchronous distributed task/job queue written in Python. It focuses on real-time operation and supports task scheduling. This is particularly useful for tasks that can be executed independently of the main application. 

Celery uses a message broker to handle communication between the main program (the producer) and the tasks (the consumers). This allows horizontal scalability: We can use many workers on different machines to process the tasks from the queue. In KubeROS we use the Reds as a message broker.


### For Development

In the development with devContainer, a redis server is already started to act as a message broker. 

If you want to do it manually: 

```
sudo apt-get update 
sudo apt-get install redis
```

Then start the redis-server with default settings: 
```
redis-server
# check if redis is up and running: 
redis-clit
# after that you should see the Redis Command Line 
127.0.0.1:6370> 
# than 
127.0.0.1:6370>PING # you will get response: PONG
```

To start the celery workers: 
Navigate to the kuberos folder and start the workers for development with verbose output for debugging.
```
/workspace/kuberos $ celery -A settings worker -l info
```

Note: 
 - For any changes in the code related to celery tasks, you must restart the celery workers.


