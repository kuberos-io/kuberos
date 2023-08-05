"""
APIs for user authentication
"""

# Python
import logging

# Django
from django.core.exceptions import PermissionDenied
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from knox.models import AuthToken

# KubeROS
from main.serializers import UserSerializer, RegisterSerializer, LoginSerializer


logger = logging.getLogger('kuberos.main.api')



class RegisterAPI(generics.GenericAPIView):
    """
    API for registering a new user
    - POST Request
    Example:
    {   'username': 'dummy', 
        'password': 'dummy',
        'email': 'dummy@xxx'}
    """
    serializer_class = RegisterSerializer

    def post(self, request, *args, **kwargs):
        """
        Get the user data from request and create a new user
        """
        serializer = self.get_serializer(data=request.data)

        if serializer.is_valid(raise_exception=True):
            user = serializer.save()
            return Response({
                "user": UserSerializer(user, context=self.get_serializer_context()).data, 
                "token": AuthToken.objects.create(user)[1]}, 
                status=status.HTTP_201_CREATED)
        else:
            return Response(serializer.errors,
                            status=status.HTTP_400_BAD_REQUEST)


class LoginAPI(generics.GenericAPIView):
    """
    API for logging in an existing user with password.
    Handle POST request.
    
    Request data should be in this format: 
    {
        'username': 'dummy',
        'password': 'dummy'
    }
    
    Upon successful login, the response will be in this format:
    {
        'user': user details 
        'token': token
    }
    
    If login is unsuccessful, a 400 Bad Request error will be returned with error details.
    """
    serializer_class = LoginSerializer

    def post(self, request, *args, **kwargs):
        """
        User login with password
        """
        serializer = self.get_serializer(data=request.data)

        if serializer.is_valid(raise_exception=True):
            user = serializer.validated_data
            
            logger.debug("Validated user data: %s", user)

            return Response({
                "user": UserSerializer(user, context=self.get_serializer_context()).data, 
                "token": AuthToken.objects.create(user)[1]
                }, status=status.HTTP_200_OK)

        else:
            return Response(serializer.errors,
                            status=status.HTTP_400_BAD_REQUEST)


# Get the user data through knox token
class UserAPI(generics.RetrieveAPIView):
    """
    API for getting user data through knox token.
    
    GET Request: 
        - Header: Authorization: Token <token>
    
    Returns: 
        - User data in JSON format
        
    If the user is not authenticated, a 403 Forbidden error will be returned.
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserSerializer

    def get_object(self):
        """
        Get user through knox token
        """
        user = self.request.user
        if user.is_authenticated:
            logger.debug("Authenticated user from request: %s", user)
            return user
        else:
            logger.warning("User is not authenticated.")
            raise PermissionDenied({
                "message": "Invalid user."
                })
