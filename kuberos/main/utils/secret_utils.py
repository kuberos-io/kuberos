# Python 
import base64 



def decode_secret(encoded_secret: str) -> dict:
    """
        Decode secret
    """
    decoded_secret = base64.b64decode(encoded_secret).decode('utf-8')
    return {
        'username': decoded_secret.split(':')[0],
        'password': decoded_secret.split(':')[1]
    }


def encode_secret(username: str, password: str) -> str:
    """
        Encode secret
    """
    encoded_secret = base64.b64encode(
        bytes('{}:{}'.format(username, password), 'utf-8')
    ).decode('utf-8')
    return encoded_secret

if __name__ == '__main__':
    encoded_secret = "bm9taTpxdGNuRW5OWlo3cUJuXzZXdkhjSw=="
    decoded = decode_secret(encoded_secret)
    print(decoded)
    
    user = 'nomi'
    password = 'qtcnEnNZZ7qBn_6WvHcK'
    encode = encode_secret(user, password)
    print(encode)
    