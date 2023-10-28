#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.


from django.urls import path, include
from knox import views as knox_views

from main.api.auth import (
    RegisterAPI,
    LoginAPI,
    UserAPI
)

urls = [
    path('', include('knox.urls')),
    path('user_register/', RegisterAPI.as_view()),
    path('user_login/', LoginAPI.as_view()),
    path('user/', UserAPI.as_view()),
    path('user_logout/', knox_views.LogoutView.as_view(), name='knox_logout')
]

__all__ = ['urls']
