from rest_framework import serializers



class BaseModelSerializer(serializers.ModelSerializer):
        
    def create(self, validated_data):
        validated_data['created_by'] = self.context['created_by']
        return super().create(validated_data=validated_data)
