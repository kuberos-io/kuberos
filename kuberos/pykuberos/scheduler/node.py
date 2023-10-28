# KubeROS default scheduler
from typing import Optional

from .rosmodule import RosModule, DiscoveryServer




class NodeBase(object):
    """
    Base object for scheduled node, to store the rosmodules, discovery server, bridge server, etc.
    
    """
    def __init__(self, 
                 hostname: str, 
                 node_state: dict,
                 ) -> None:
        
        self._hostname = hostname
        self._node_state = node_state
        
        self.phase = 'initaliazed'  # scheduled | dispatched
        self.discovery_server = None
        self.ros_modules = []
        
    def get_pod_list(self):
        """
        Return the pod list with determined node selector of rosmodules and discovery server.
        """
        pod_list = []
        # discovery server 
        pod_list.append(self.discovery_server.pod_manifest)
        # rosmodules
        for k, v in self.ros_modules.items():
            pod_list.append(v.pod_manifest)
        
        print(self.ros_modules)
        return pod_list
        
    def get_svc_list(self):
        """
        Return the service list with matching pod selector of disvoery server.
        """
        svc_list = []
        svc_list.append(self.discovery_server.service_manifest)
        return svc_list
    
    
    @property
    def num_of_scheduled_rosmodules(self):
        return len(self.ros_modules)
    
    def add_rosmodule(self, 
                    rosmodule: RosModule
                    )-> None:
        """
        Add the scheduled rosmodules to the node.
        """
        self.ros_modules.update({rosmodule.name: rosmodule})
    
    def get_discovery_svc_name(self) -> str:

        """
        Return the service name for rosmodule to connect to the discovery server.
        """
        if self.discovery_server is not None:
            return self.discovery_server.discovery_svc_name
        else:
            print("ERROR: No discovery server is assigned to this node.")
    
    @property
    def hostname(self):
        return self._hostname
    
    
class FleetNode(NodeBase):
    
    def __init__(self, 
                 hostname: str, 
                 node_state: dict) -> None:
        
        super().__init__(hostname, node_state)
        
    def add_discovery_server(self, 
                             pod_name: str = None,
                                ) -> None:
        self.discovery_server = DiscoveryServer(
            name=f'dds-{self.hostname}', 
            port= 11933, 
            target_node=self.hostname
        )
        

class EdgeNode(NodeBase):
    
    def __init__(self, 
                 hostname: str, 
                 node_state: dict) -> None:
        super().__init__(hostname, node_state)



    
class EdgeNodeGroup(object):
    """
    KubeROS consider all edge works as a group of resources.
    
    Generally, the KubeROS don't schedule the rosmodule to a specific edge node and 
    let the Kubernetes scheduler to do the job. 
    
    In advance, the KubeROS provides an advanced scheduling policy to allow the user to 
    optimize the scheduling, depending on the network status, requirements, etc.
    
    Like the ScheduledFleetNode, the ScheduledEdgeGroup stores the rosmodules, 
    discovery server, bridge server for EACH robots! 
    
    It shares only the computing resources, but not the rosmodules! 
   
    Basic methods: 
        - add rosmodule 
        - add discovery server
        - add bridge server
    
    Advanced features: 
        - bridge_server_modus: break the direct communication between the edge worker and 
                               the fleet node through DDS, and use the bridge server as a proxy.
                               Set a backup rosmodule on the fleet node, 
                               Switch to the backup ros module, if the network conditions 
                               are not fullfill the requirements.
    """
    
    def __init__(self, 
                 edge_state: list,
                 ) -> None:
        # self.edge_node_name_list = []
        # self.edge_node = {}
        # self.rosmodules = []
        
        self._edge_nodes_state = edge_state
        
        # each robot should get a dedicated rosmodules 
        # two steps:
        #  - first assign the rosmodules to the edge group
        #  - second: refine: depending on the network status, and scheduling policy.

    @property
    def num_of_ava_edge_nodes(self):
        return len(self._edge_nodes_state)
    
    def get_pod_list(self):
        pass
    
    def requirements(self):
        pass
    
    def bind_bridge_node(self, 
                         node_pair: str):
        # Experimental feature 
        pass 
    
    def set_brief_info_from_kuberos_db(self):
        # cache the essential info for kuberos database 
        # for dynamic scheduler! 
        pass 

    def add_bridge_server(self):
        pass





class ScheduledFleetNode_Backup(object):
    """
    Fleet node that has been scheduled by the scheduler,
    and store the rosmodules, discovery server, bridge server, etc.
    
    Basic methods: 
        - add_rosmodule: update the rosmodules list 
        - add discovery server: add a discovery server objects to this node
        
    Outputs: 
        - pod list: list of pod manifest with determined node selector
        - service list: list of service manifest with matching pod selector
        
        - dictionary of deployed pods and services: 
            * for dynamic scheduler and deployment controller
            * stored in the KubeROS database
    """
    def __init__(self, 
                 robot_name: str,
                 device_name: str, 
                 device_type: str,
                 discovery_server: Optional[DiscoveryServer] = None,
                #  bridges: Optional[KuberosBridge] = None,
                 ) -> None:
        
        self._robot_name = robot_name
        self._device_name = device_name
        self._device_type = device_type
        
        self.finished = False
        
        self.discovery_server = discovery_server
        self.ros_modules = {}
    
    @property
    def robot_name(self):
        return self._robot_name
    
    @property
    def device_name(self):
        return self._device_name
    
    @property
    def device_type(self):
        return self._device_type
    
    @property
    def num_of_scheduled_rosmodules(self):
        return len(self.ros_modules)
    
    def get_discovery_svc_name(self) -> str:
    
        """
        Return the service name for rosmodule to connect to the discovery server.
        """
        if self.discovery_server is not None:
            return self.discovery_server.discovery_svc_name
        else:
            print("ERROR: No discovery server is assigned to this node.")
        
    def add_rosmodule(self, 
                      rosmodule: RosModule
                      )-> None:
        """
        Add the scheduled rosmodules to the node.
        """
        self.ros_modules.update({rosmodule.name: rosmodule})

    def get_pod_list(self):
        """
        Return the pod list with determined node selector of rosmodules and discovery server.
        """
        pod_list = []
        # discovery server 
        pod_list.append(self.discovery_server.pod_manifest)
        # rosmodules
        for k, v in self.ros_modules.items():
            pod_list.append(v.pod_manifest)
        
        print(self.ros_modules)
        return pod_list
        
    def get_svc_list(self):
        """
        Return the service list with matching pod selector of disvoery server.
        """
        svc_list = []
        svc_list.append(self.discovery_server.service_manifest)
        return svc_list

    def add_bridge_node_and_backup_rosmodule(self,
                                             ros_module: RosModule,
                                             bridge_settings: dict
                                             ) -> None:
        """
        [Experimental feature]
        In the situation that the internet connection is not stable or lost, 
        the bridge node will switch to the backup node, which use usually a small model for inference, 
        to keep the robot on working. 
        
        Large model -> goes to the cloud, delivery high quality result. 
        Small model -> deployed locally, as back up node.        
        
        """
        pass

        






