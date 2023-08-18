from django.contrib import admin
from django.contrib.admin.options import StackedInline
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from main.models import (
    UserProfile,
    HostCredential,
    Host, 
    Cluster,
    ClusterSyncLog,
    ClusterNode,
    ContainerRegistryAccessToken,
    Fleet, 
    FleetNode,
    FleetHardwareOperationEvent,
    Deployment, 
    DeploymentEvent,
    DeploymentJob,
    BatchJobDeployment,
    BatchJobUnit,
)



# Auth 
class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False


class UserAdmin(BaseUserAdmin):
    inlines = (UserProfileInline, )
    
admin.site.unregister(User)
admin.site.register(User, UserAdmin)


# Host
@admin.register(HostCredential)
class HostCredentialAdmin(admin.ModelAdmin):
    model = HostCredential, 
    readonly_fields = (
        'created_by',
    )
    
    def save_model(self, request, obj, form, change):
        if not change: 
            obj.created_by = request.user
        obj.save()
        
@admin.register(Host)
class HostAdmin(admin.ModelAdmin):
    model = Host
    readonly_fields = (
        'created_by',
    )


# Cluster
@admin.register(Cluster)
class ClusterAdmin(admin.ModelAdmin):
    model = Cluster
    readonly_fields = (
        'created_by',
    )


@admin.register(ClusterNode)
class ClusterNodeAdmin(admin.ModelAdmin):
    model = ClusterNode


@admin.register(ClusterSyncLog)
class ClusterSyncLogAdmin(admin.ModelAdmin):
    model = ClusterSyncLog


@admin.register(ContainerRegistryAccessToken)
class ContainerRegistryAccessTokenAdmin(admin.ModelAdmin):
    model = ContainerRegistryAccessToken


# Fleet
class FleetNodeAdminInline(StackedInline):
    model = FleetNode
    extra = 1


@admin.register(Fleet)
class FleetAdmin(admin.ModelAdmin):
    model = Fleet  
    inlines = (FleetNodeAdminInline,)
    readonly_fields = (
        'created_by',
    )

@admin.register(FleetNode)
class FleetNodeAdmin(admin.ModelAdmin):
    model = FleetNode
    # readonly_fields = (
    #     'created_by',
    # )

# Deployment
class DeploymentEventAdminInline(StackedInline):
    model = DeploymentEvent
    extra = 1

class DeploymentJobInProgressAdminInline(StackedInline):
    model = DeploymentJob
    extra = 1    

@admin.register(Deployment)
class DeploymentAdmin(admin.ModelAdmin):
    model = Deployment
    inlines = (DeploymentEventAdminInline, DeploymentJobInProgressAdminInline)
    readonly_fields = (
        'created_by',
    )
    
# Batch Jobs
class BatchJobUnitAdminInline(StackedInline):
    model = BatchJobUnit
    extra = 1
    
@admin.register(BatchJobDeployment)
class BatchJobDeploymentAdmin(admin.ModelAdmin):
    model = BatchJobDeployment
    inlines = (BatchJobUnitAdminInline, )
    readonly_fields = (
        'created_by',
    )

# FleetHardwareOperationEvent    
@admin.register(FleetHardwareOperationEvent)
class FleetHardwareOperationEventAdmin(admin.ModelAdmin):
    model = FleetHardwareOperationEvent
    readonly_fields = (
        'created_by',
    )
