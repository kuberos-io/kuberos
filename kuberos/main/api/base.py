"""
Generic API Response classes for Kuberos.
"""

# django rest framework
from rest_framework.utils.serializer_helpers import (
    ReturnList,
    ReturnDict
)


class KuberosResponse():
    """
    Generic response class for Kuberos API.
    """
    def __init__(self):
        self._status = 'unknown'
        self._data = {}
        self._errors = []
        self._msgs = []

    def set_data(self, data: dict) -> None:
        """
        set the data to the response.
        """
        if not type(data) in [dict, ReturnDict, ReturnList]:
            raise ValueError("The data must be a dict or a DRF object. ")
        self._data = data

    def _add_error(self,
                  err_reason: str,
                  err_msg: str) -> None:
        if not isinstance(err_reason, str):
            raise ValueError("The err_reason must be a string.")
        if not isinstance(err_msg, str):
            raise ValueError("The err_msg must be a string.")

        self._errors.append({
            'reason': err_reason,
            'msg': err_msg
        })

    def add_msg(self, msg: str) -> None:
        """
        Add the message to the response. 
        """
        self._msgs.append(msg)

    def set_failed(self,
                   reason: str,
                   err_msg: str) -> None:
        """
        Set the response status as failed.
        """
        self._status = 'failed'
        self._add_error(reason, err_msg)

    def set_success(self, 
                    msg: str = None) -> None:
        """
        Set the response status as success.
        """
        self._status = 'success'
        if msg: 
            if not isinstance(msg, str):
                raise ValueError("The msg must be a string.")
            self._msgs.append(msg)

    def set_accepted(self,
                     msg: str = None) -> None:
        """
        Set the response status as accepted.
        """
        self._status = 'accepted'
        if not isinstance(msg, str):
            raise ValueError("The msg must be a string.")
        if msg:
            self._msgs.append(msg)


    def set_rejected(self,
                     reason: str,
                     err_msg: str) -> None:
        """
        Set the response status as rejected.
        """
        self._status = 'rejected'
        self._add_error(reason, err_msg)

    def concatenate(self, other_response) -> None:
        """
        concatenate other response.
        """
        if not isinstance(other_response, KuberosResponse):
            raise ValueError("The other_response must be a KuberosResponse object.")

        self._data.update(other_response.data)
        self._errors.extend(other_response.errors)
        self._msgs.extend(other_response.msgs)
        
    def to_dict(self) -> dict:
        """
        Get the response as a dict.
        """
        return {
            'status': self._status,
            'data': self._data,
            'errors': self._errors,
            'msgs': self._msgs
        }

    @property
    def data(self):
        return self._data
    
    @property
    def errors(self):
        return self._errors
    
    @property
    def msgs(self):
        return self._msgs