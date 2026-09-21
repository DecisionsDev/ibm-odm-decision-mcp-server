# Copyright contributors to the IBM ODM MCP Server project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import sys
import os
import tempfile

# Add the root directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

import pytest
import responses
import json
import requests  # Add this line to import the requests module
from unittest.mock import patch, MagicMock
from decision_mcp_server.Credentials import Credentials
from decision_mcp_server.DecisionMCPServer import create_credentials

def get_test_credentials():
    return Credentials(
        odm_url="http://localhost:9060/res",
        username="test_user",
        password="test_pass"
    )

def test_valid_url():
    # Test with a valid URL
    cred = Credentials(odm_url="http://localhost:9060/res")
    assert cred.odm_url == "http://localhost:9060/res"

def test_url_with_trailing_slash():
    # Test with a URL that has a trailing slash
    cred = Credentials(odm_url="http://localhost:9060/res/", username="user", password="pass")
    assert cred.odm_url == "http://localhost:9060/res"

def test_url_with_extra_path():
    # Test with a URL that has an extra path
    cred = Credentials(odm_url="http://localhost:9060/odm/res/", username="user", password="pass")
    assert cred.odm_url == "http://localhost:9060/odm/res"

def test_get_auth_zenapikey():
    # Test get_auth with zenapikey
    cred = Credentials(odm_url="http://localhost:9060/res", username="test_username", zenapikey="test_key")
    headers = cred.get_auth()
    assert headers == {
        'Authorization': 'ZenApiKey dGVzdF91c2VybmFtZTp0ZXN0X2tleQ==', # Base64 encoded 'test_username:test_key'
        'Content-Type': 'application/json; charset=UTF-8',
        'accept': 'application/json; charset=UTF-8'
    }

def test_get_auth_missusername_zenapikey():
    # Test get_auth with zenapikey
    with pytest.raises(ValueError, match="Username must be provided when using zenapikey."):
        cred = Credentials(odm_url="http://localhost:9060/res", zenapikey="test_key", username=None)
        cred.get_auth()
    

def test_get_auth_basic_auth():
    # Test get_auth with username and password
    cred = Credentials(odm_url="http://localhost:9060/res", username="user", password="pass")
    headers = cred.get_auth()
    assert headers == {
        'Authorization': 'Basic dXNlcjpwYXNz',
        'Content-Type': 'application/json; charset=UTF-8',
        'accept': 'application/json; charset=UTF-8'
    }

def test_get_auth_no_credentials():
    # Test get_auth with no credentials
    cred = Credentials(odm_url="http://localhost:9060/res")
    headers = cred.get_auth()
    assert headers == {
        'Content-Type': 'application/json; charset=UTF-8',
        'accept': 'application/json; charset=UTF-8'
    }

@responses.activate
def test_get_auth_openid_flow():
    """Test the complete OpenID Connect authentication flow with a mocked token endpoint."""
    
    # Mock token URL
    token_url = "https://auth.example.com/token"
    
    # Expected access token that will be returned by the mock server
    expected_token = "mocked_access_token_12345"
    
    # Set up the mock response for the token endpoint
    responses.add(
        responses.POST,
        token_url,
        json={
            "access_token": expected_token,
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": "openid"
        },
        status=200
    )
    
    # Create credentials with OpenID Connect parameters
    cred = Credentials(
        odm_url="http://localhost:9060/res",
        client_id="test_client_id",
        client_secret="test_client_secret",
        token_url=token_url,
        scope="openid profile"  # Test with multiple scopes
    )
    
    # Call get_auth which should make the token request
    headers = cred.get_auth()
    
    # Verify the token request was made correctly
    assert len(responses.calls) == 1
    assert responses.calls[0].request.url == token_url
    
    # Verify the request body contains the correct parameters
    request_body = responses.calls[0].request.body
    # Check if body is bytes, if so decode it, otherwise use as is
    if isinstance(request_body, bytes):
        request_body = request_body.decode('utf-8')
    
    # Make sure request_body is not None before checking content
    assert request_body is not None
    assert "grant_type=client_credentials" in request_body
    assert "scope=openid+profile" in request_body
    
    # Verify the auth header uses HTTP Basic auth with client_id and client_secret
    auth_header = responses.calls[0].request.headers['Authorization']
    assert auth_header.startswith('Basic ')
    
    # Verify the returned headers contain the expected token
    assert headers == {
        'Authorization': f'Bearer {expected_token}',
        'Content-Type': 'application/json; charset=UTF-8',
        'accept': 'application/json; charset=UTF-8'
    }

@responses.activate
def test_get_auth_openid_error_handling():
    """Test error handling in the OpenID Connect authentication flow."""
    
    # Mock token URL
    token_url = "https://auth.example.com/token"
    
    # Set up the mock response to simulate a server error
    responses.add(
        responses.POST,
        token_url,
        json={
            "error": "invalid_client",
            "error_description": "Client authentication failed"
        },
        status=401
    )
    
    # Create credentials with OpenID Connect parameters
    cred = Credentials(
        odm_url="http://localhost:9060/res",
        client_id="invalid_client_id",
        client_secret="invalid_client_secret",
        token_url=token_url
    )
    
    # Call get_auth which should make the token request and raise an exception
    with pytest.raises(requests.exceptions.HTTPError) as excinfo:
        cred.get_auth()
    
    # Verify the correct error was raised
    assert "401" in str(excinfo.value)
    
    # Verify the token request was made
    assert len(responses.calls) == 1
    assert responses.calls[0].request.url == token_url

@responses.activate
def test_get_auth_openid_malformed_response():
    """Test handling of malformed responses in the OpenID Connect flow."""
    
    # Mock token URL
    token_url = "https://auth.example.com/token"
    
    # Set up the mock response with a malformed JSON body
    responses.add(
        responses.POST,
        token_url,
        body="Not a JSON response",
        status=200
    )
    
    # Create credentials with OpenID Connect parameters
    cred = Credentials(
        odm_url="http://localhost:9060/res",
        client_id="test_client_id",
        client_secret="test_client_secret",
        token_url=token_url
    )
    
    # Call get_auth which should make the token request and raise a JSON decoding exception
    with pytest.raises(json.JSONDecodeError):
        cred.get_auth()
    
    # Verify the token request was made
    assert len(responses.calls) == 1

@responses.activate
def test_get_auth_pkjwt_with_public_cert():
    """Test PKJWT authentication with a public certificate for x5t computation."""
    import tempfile
    import os
    import base64
    import hashlib
    import jwt  # Make sure PyJWT is installed
    from unittest.mock import patch, MagicMock
    
    # Create temporary certificate files for testing
    with tempfile.NamedTemporaryFile(delete=False, suffix='.key') as private_key_file:
        # This is a test private key (not secure, just for testing)
        private_key = """-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEAu1SU1LfVLPHCozMxH2Mo4lgOEePzNm0tRgeLezV6ffAt0gun
VTLw7onLRnrq0/IzW7yWR7QkrmBL7jTKEn5u+qKhbwKfBstIs+bMY2Zkp18gnTxK
LxoS2tFczGkPLPgizskuemMghRniWWoLnB0/QILJvmjVWSv9ddnx6mT2J5Cv5KMD
Hq7Vdi3PzwJC2/Lw9VW1VVBswxWxIexPAlKe8LFzgawqiGWEUGXAGFy+I0IH8oes
C3T+fCmpgsTWMjCfBpvEIRaqFLy0EzDcg8FsThmZRY15RJJg+cAiAPgvEEB44zaJ
w+SkayLjej4qPfD2cQIDAQABAoIBAQDlJ+ScFfDgfDAbvYwFPGBGEYUYAGHb4bGd
EJXMiRawFRqTb1l5jCRjgEDVG3caeRlW/S7mE0IgkDWUwUCSjvwGXxrOzXCswA73
/HEu6Br9aWKGJu8EFP4QhSVYVZRIPocWSO5lbL8QlFUgEMTi5Srzu2WWQnRlSIFi
KxvSfs/EtQIBAQDRcQdz+1sT5g7iulAxqmz/OS7Qb0GTd0UE2xrV56cT+IlXAF3h
M+/VDzKk3DyDAAdlkXWtInOx1TetF2qpdb+zY8GRS8FkCKScc7gVP9z66cFlU82a
KvAybcWww2BWXL+al8VM/sE+W9JIdkrBuyVfMRfTU1s1OaBszKv+71EDdwIBAQBl
JDyr8WZCEfFmeadrh7t2kEjMzE/fjy3lF8oMrl9XrT+rxDGBnuSUx8BCJRcZUXLr
10RMtBWQo3G+zsB/D8mXw9m1Cv93G2P+ZFlpY9fQoIlxjsGtDCosSTm8VKNG8/V0
aXuIr8PYf6HgnH+DjMpHXEKLWdeqsRuKoYo3ZbEyFQIBAQDGAlR8ndMpcUcUEMSz
udr0mTsv50daJRri54jesvbDO6caLcLWIT1Tmy1FRRQvywdjeUPE0VdO4Ym1bGZM
aBhUsErwlm7QwkUHBW0xBOcbwVrj5qo0N1DTXYKxhBx/VGfmznBGb71FBTRX0czZ
gUcH45OnFljBB8PtQ+T/RZenIwIBAQCgwC/KJbEPKyDxV8GWcX7zOi+W5q9qXMJm
Y0mNaZHuYNJOdOKW9hCmUQY/BXBdd2KYkpRD0SnGfF/VQrZRfcXmLCExNYpMRTDN
2wZX7sXNh6AYwFdJKW8yP9FxoLUbNDmmYyPlqIiAcBKJvvwndZczROLmwLFgYUzw
qYQV1B0ATz0Yd6X+RGQhD6kocCRXJFmHhYjMdLINd+KKjOxSG0j3OKjzHEPLMpbp
QCQJVp0YqLKYXUYAA4VZi+MBpZA5KgZVIFQLm5IzQvuGqEQOMmCQC+Z2TPt8VQQN
t+Z1H5t2K+MG8ky6bo3QaSNBXOPHVnK/TQ0S171JfQDmzXJSPVEr
-----END RSA PRIVATE KEY-----"""
        private_key_file.write(private_key.encode())
        private_key_path = private_key_file.name
    
    with tempfile.NamedTemporaryFile(delete=False, suffix='.crt') as public_cert_file:
        # This is a test public certificate (not secure, just for testing)
        public_cert = """-----BEGIN CERTIFICATE-----
MIIDazCCAlOgAwIBAgIUOd70QQlNOIUgFoNNa7QzbdtKWucwDQYJKoZIhvcNAQEL
BQAwRTELMAkGA1UEBhMCQVUxEzARBgNVBAgMClNvbWUtU3RhdGUxITAfBgNVBAoM
GEludGVybmV0IFdpZGdpdHMgUHR5IEx0ZDAeFw0yMzA0MTIxNDQ2NDNaFw0yNDA0
MTExNDQ2NDNaMEUxCzAJBgNVBAYTAkFVMRMwEQYDVQQIDApTb21lLVN0YXRlMSEw
HwYDVQQKDBhJbnRlcm5ldCBXaWRnaXRzIFB0eSBMdGQwggEiMA0GCSqGSIb3DQEB
AQUAA4IBDwAwggEKAoIBAQC7VJTUt9Us8cKjMzEfYyjiWA4R4/M2bS1GB4t7NXp9
8C3SC6dVMvDuictGeurT8jNbvJZHtCSuYEvuNMoSfm76oqFvAp8Gy0iz5sxjZmSn
XyCdPEovGhLa0VzMaQ8s+CLOyS56YyCFGeJZagucHT9Agsm+aNVZK/112fHqZPYn
kK/kowMertV2Lc/PAkLb8vD1VbVVUGzDFbEh7E8CUp7wsXOBrCqIZYRQZcAYXL4j
Qgfyh6wLdP58KamCxNYyMJ8Gm8QhFqoUvLQTMNyDwWxOGZlFjXlEkmD5wCIA+C8Q
QHjjNonD5KRrIuN6Pio98PZxAgMBAAGjUzBRMB0GA1UdDgQWBBQNRxQMcVIlWiL7
RjXiqqFKmNKBQDAfBgNVHSMEGDAWgBQNRxQMcVIlWiL7RjXiqqFKmNKBQDAPBgNV
HRMBAf8EBTADAQH/MA0GCSqGSIb3DQEBCwUAA4IBAQCgwC/KJbEPKyDxV8GWcX7z
Oi+W5q9qXMJmY0mNaZHuYNJOdOKW9hCmUQY/BXBdd2KYkpRD0SnGfF/VQrZRfcXm
LCExNYpMRTDN2wZX7sXNh6AYwFdJKW8yP9FxoLUbNDmmYyPlqIiAcBKJvvwndZcz
ROLmwLFgYUzwqYQV1B0ATz0Yd6X+RGQhD6kocCRXJFmHhYjMdLINd+KKjOxSG0j3
OKjzHEPLMpbpQCQJVp0YqLKYXUYAA4VZi+MBpZA5KgZVIFQLm5IzQvuGqEQOMmCQ
C+Z2TPt8VQQNt+Z1H5t2K+MG8ky6bo3QaSNBXOPHVnK/TQ0S171JfQDmzXJSPVEr
-----END CERTIFICATE-----"""
        public_cert_file.write(public_cert.encode())
        public_cert_path = public_cert_file.name
    
    try:
        # Mock the certificate loading and thumbprint calculation
        with patch('cryptography.x509.load_pem_x509_certificate') as mock_load_cert, \
             patch('cryptography.x509.load_der_x509_certificate') as mock_load_der_cert, \
             patch('jwt.encode') as mock_encode:
            
            # Create a mock certificate
            mock_cert = MagicMock()
            mock_cert.public_bytes.return_value = b"mocked_cert_bytes"
            mock_load_cert.return_value = mock_cert
            mock_load_der_cert.return_value = mock_cert
            
            # Expected x5t value (doesn't matter what it is for the test)
            expected_x5t = "mocked_x5t_value"
            
            # Set up the mock to return a dummy JWT token
            mock_encode.return_value = "dummy.jwt.token"
            
            # Mock token URL
            token_url = "https://auth.example.com/token"
            
            # Expected access token that will be returned by the mock server
            expected_token = "mocked_access_token_12345"
            
            # Set up the mock response for the token endpoint
            responses.add(
                responses.POST,
                token_url,
                json={
                    "access_token": expected_token,
                    "token_type": "Bearer",
                    "expires_in": 3600,
                    "scope": "openid"
                },
                status=200
            )
            
            # Create credentials with PKJWT parameters
            cred = Credentials(
                odm_url="http://localhost:9060/res",
                client_id="test_client_id",
                pkjwt_key_path=private_key_path,
                pkjwt_cert_path=public_cert_path,
                token_url=token_url
            )
            
            # Call get_auth which should make the token request
            headers = cred.get_auth()
            
            # Verify that jwt.encode was called with the correct headers
            # Get the headers argument from the call
            args, kwargs = mock_encode.call_args
            assert 'headers' in kwargs
            assert 'x5t' in kwargs['headers']
            
            # Verify the token request was made
            assert len(responses.calls) == 1
            assert responses.calls[0].request.url == token_url
            
            # Verify the returned headers contain the expected token
            assert headers == {
                'Authorization': f'Bearer {expected_token}',
                'Content-Type': 'application/json; charset=UTF-8',
                'accept': 'application/json; charset=UTF-8'
            }
            
            # Test that providing only one of the certificate paths raises an error
            with pytest.raises(ValueError, match="Both 'pkjwt_key_path' and 'pkjwt_cert_path' are required for PKJWT authentication."):
                Credentials(
                    odm_url="http://localhost:9060/res",
                    client_id="test_client_id",
                    pkjwt_key_path=private_key_path,  # Only providing private key
                    token_url=token_url
                ).get_auth()
                
            with pytest.raises(ValueError, match="Both 'pkjwt_key_path' and 'pkjwt_cert_path' are required for PKJWT authentication."):
                Credentials(
                    odm_url="http://localhost:9060/res",
                    client_id="test_client_id",
                    pkjwt_cert_path=public_cert_path,  # Only providing certificate
                    token_url=token_url
                ).get_auth()
    
    finally:
        # Clean up temporary files
        if os.path.exists(private_key_path):
            os.unlink(private_key_path)
        if os.path.exists(public_cert_path):
            os.unlink(public_cert_path)

@responses.activate
def test_get_auth_pkjwt_with_password_protected_cert():
    """Test PKJWT authentication with a password-protected certificate."""
    import tempfile
    import os
    from unittest.mock import patch, MagicMock
    
    # Create temporary certificate files for testing
    with tempfile.NamedTemporaryFile(delete=False, suffix='.key') as private_key_file:
        # This would be an encrypted key in reality, but we'll mock the decryption
        private_key = """-----BEGIN ENCRYPTED PRIVATE KEY-----
MIIFHDBOBgkqhkiG9w0BBQ0wQTApBgkqhkiG9w0BBQwwHAQIkZzwRoNvLt8CAggA
MAwGCCqGSIb3DQIJBQAwFAYIKoZIhvcNAwcECNDUvECBYigoBI...
-----END ENCRYPTED PRIVATE KEY-----"""
        private_key_file.write(private_key.encode())
        private_key_path = private_key_file.name
    
    with tempfile.NamedTemporaryFile(delete=False, suffix='.crt') as public_cert_file:
        # Test public certificate
        public_cert = """-----BEGIN CERTIFICATE-----
MIIDazCCAlOgAwIBAgIUOd70QQlNOIUgFoNNa7QzbdtKWucwDQYJKoZIhvcNAQEL
BQAwRTELMAkGA1UEBhMCQVUxEzARBgNVBAgMClNvbWUtU3RhdGUxITAfBgNVBAoM
GEludGVybmV0IFdpZGdpdHMgUHR5IEx0ZDAeFw0yMzA0MTIxNDQ2NDNaFw0yNDA0...
-----END CERTIFICATE-----"""
        public_cert_file.write(public_cert.encode())
        public_cert_path = public_cert_file.name
    
    try:
        # Mock the cryptography functions for decrypting the private key
        with patch('cryptography.hazmat.primitives.serialization.load_pem_private_key') as mock_load_key, \
             patch('cryptography.x509.load_pem_x509_certificate') as mock_load_cert, \
             patch('cryptography.x509.load_der_x509_certificate') as mock_load_der_cert, \
             patch('jwt.encode') as mock_encode:
            
            # Create a mock key object
            mock_key = MagicMock()
            mock_key.private_bytes.return_value = b"-----BEGIN RSA PRIVATE KEY-----\nDecrypted Key Content\n-----END RSA PRIVATE KEY-----"
            mock_load_key.return_value = mock_key
            
            # Create a mock certificate
            mock_cert = MagicMock()
            mock_cert.public_bytes.return_value = b"mocked_cert_bytes"
            mock_load_cert.return_value = mock_cert
            mock_load_der_cert.return_value = mock_cert
            
            # Set up the mock to return a dummy JWT token
            mock_encode.return_value = "dummy.jwt.token"
            
            # Mock token URL
            token_url = "https://auth.example.com/token"
            
            # Expected access token that will be returned by the mock server
            expected_token = "mocked_access_token_12345"
            
            # Set up the mock response for the token endpoint
            responses.add(
                responses.POST,
                token_url,
                json={
                    "access_token": expected_token,
                    "token_type": "Bearer",
                    "expires_in": 3600,
                    "scope": "openid"
                },
                status=200
            )
            
            # Create credentials with PKJWT parameters
            cred = Credentials(
                odm_url="http://localhost:9060/res",
                client_id="test_client_id",
                pkjwt_key_path=private_key_path,
                pkjwt_cert_path=public_cert_path,
                pkjwt_key_password="test_password",  # Add password for the certificate
                token_url=token_url
            )
            
            # Call get_auth which should make the token request
            headers = cred.get_auth()
            
            # Verify that load_pem_private_key was called with the correct password
            mock_load_key.assert_called_once()
            args, kwargs = mock_load_key.call_args
            assert kwargs['password'] == b"test_password"
            
            # Verify the token request was made
            assert len(responses.calls) == 1
            assert responses.calls[0].request.url == token_url
            
            # Verify the returned headers contain the expected token
            assert headers == {
                'Authorization': f'Bearer {expected_token}',
                'Content-Type': 'application/json; charset=UTF-8',
                'accept': 'application/json; charset=UTF-8'
            }
    
    finally:
        # Clean up temporary files
        if os.path.exists(private_key_path):
            os.unlink(private_key_path)
        if os.path.exists(public_cert_path):
            os.unlink(public_cert_path)

@responses.activate
def test_get_auth_openid_missing_access_token():
    """Test handling when the token response is missing the access_token field."""
    
    # Mock token URL
    token_url = "https://auth.example.com/token"
    
    # Set up the mock response with a JSON body missing the access_token
    responses.add(
        responses.POST,
        token_url,
        json={
            "token_type": "Bearer",
            "expires_in": 3600
            # access_token is missing
        },
        status=200
    )
    
    # Create credentials with OpenID Connect parameters
    cred = Credentials(
        odm_url="http://localhost:9060/res",
        client_id="test_client_id",
        client_secret="test_client_secret",
        token_url=token_url
    )
    
    # Call get_auth which should make the token request and raise a KeyError
    with pytest.raises(KeyError) as excinfo:
        cred.get_auth()
    
    # Verify the correct error was raised
    assert "access_token" in str(excinfo.value)
    
    # Verify the token request was made
    assert len(responses.calls) == 1

# Test get_session method
def test_get_session_https_with_verify():
    """Test get_session with HTTPS URL and SSL verification enabled."""
    with patch('requests.Session') as mock_session_class, \
         patch('decision_mcp_server.Credentials.CustomHTTPAdapter') as mock_adapter_class:
        
        # Setup mocks
        mock_session = mock_session_class.return_value
        mock_adapter = mock_adapter_class.return_value
        
        # Create credentials with HTTPS URL and SSL verification enabled
        cred = Credentials(
            odm_url="https://localhost:9060/res",
            username="user",
            password="pass",
            verify_ssl=True
        )
        
        # Call get_session
        session = cred.get_session()
        
        # Verify session was created and configured correctly
        assert mock_session_class.called
        assert mock_adapter_class.called
        assert mock_session.mount.called
        assert mock_session.mount.call_args[0][0] == 'https://'
        assert mock_session.mount.call_args[0][1] == mock_adapter
        assert mock_session.verify is True
        assert session == mock_session

def test_get_session_http_no_verify():
    """Test get_session with HTTP URL (no SSL verification needed)."""
    with patch('requests.Session') as mock_session_class, \
         patch('urllib3.disable_warnings') as mock_disable_warnings:
        
        # Setup mocks
        mock_session = mock_session_class.return_value
        
        # Create credentials with HTTP URL
        cred = Credentials(
            odm_url="http://localhost:9060/res",
            username="user",
            password="pass"
        )
        
        # Call get_session
        session = cred.get_session()
        
        # Verify session was created and configured correctly
        assert mock_session_class.called
        assert mock_disable_warnings.called  # Should still be called even for HTTP
        assert mock_session.verify is False
        assert session == mock_session

def test_get_session_https_no_verify():
    """Test get_session with HTTPS URL but SSL verification disabled."""
    with patch('requests.Session') as mock_session_class, \
         patch('urllib3.disable_warnings') as mock_disable_warnings:
        
        # Setup mocks
        mock_session = mock_session_class.return_value
        
        # Create credentials with HTTPS URL but verification disabled
        cred = Credentials(
            odm_url="https://localhost:9060/res",
            username="user",
            password="pass",
            verify_ssl=False
        )
        
        # Call get_session
        session = cred.get_session()
        
        # Verify session was created and configured correctly
        assert mock_session_class.called
        assert mock_disable_warnings.called
        assert mock_session.verify is False
        assert session == mock_session

def test_get_session_with_mtls():
    """Test get_session with mTLS configuration."""
    import tempfile
    import os

    with patch('requests.Session') as mock_session_class, \
         patch('decision_mcp_server.Credentials.Credentials.mtls_cert_tuple') as mock_mtls_cert_tuple, \
         tempfile.NamedTemporaryFile(delete=False, suffix='.key') as key_file:

        key_file.write(b"-----BEGIN PRIVATE KEY-----\ncontent\n-----END PRIVATE KEY-----")
        key_path = key_file.name

        # Setup mocks
        mock_session = mock_session_class.return_value
        mock_mtls_cert_tuple.return_value = ('/path/to/cert', key_path)
        
        try:
            # Create credentials with mTLS configuration
            cred = Credentials(
                odm_url="https://localhost:9060/res",
                username="user",
                password="pass",
                mtls_cert_path="/path/to/cert",
                mtls_key_path=key_path
            )
            
            # Call get_session
            session = cred.get_session()
            
            # Verify session was created and configured correctly
            assert mock_session_class.called
            assert mock_mtls_cert_tuple.called
            assert session.cert == ('/path/to/cert', key_path)
            assert session == mock_session

        finally:
            # Clean up the temporary file
            if os.path.exists(key_path):
                os.unlink(key_path)

# Test mtls_cert_tuple method
def test_mtls_cert_tuple_no_password():
    """Test mtls_cert_tuple method without password."""
    import tempfile
    import os

    # Create a temporary key file
    with tempfile.NamedTemporaryFile(delete=False, suffix='.key') as key_file:
        # This is just a placeholder, the actual content doesn't matter as we'll mock the decryption
        key_file.write(b"-----BEGIN PRIVATE KEY-----\ncontent\n-----END PRIVATE KEY-----")
        key_path = key_file.name

    try:
        cred = Credentials(
            odm_url="https://localhost:9060/res",
            username="user",
            password="pass",
            mtls_cert_path="/path/to/cert",
            mtls_key_path=key_path
        )
        
        cert_tuple = cred.mtls_cert_tuple()
        assert cert_tuple == ("/path/to/cert", key_path)

    finally:
        # Clean up the temporary file
        if os.path.exists(key_path):
            os.unlink(key_path)

# Test cleanup method
def test_cleanup_with_unencrypted_key():
    """Test cleanup method when an unencrypted key file was created."""
    with patch('os.remove') as mock_remove:
        # Create credentials with mTLS configuration and set unencrypted key path
        cred = Credentials(
            odm_url="https://localhost:9060/res",
            username="user",
            password="pass"
        )
        cred.mtls_key_password = "secret"  # This would trigger cleanup
        cred.mtls_unencrypted_key_path = "/tmp/unencrypted_key"
        
        # Call cleanup
        cred.cleanup()
        
        # Verify temporary file was removed
        mock_remove.assert_called_with("/tmp/unencrypted_key")

def test_cleanup_without_unencrypted_key():
    """Test cleanup method when no unencrypted key file was created."""
    with patch('os.remove') as mock_remove:
        # Create credentials without mTLS password
        cred = Credentials(
            odm_url="https://localhost:9060/res",
            username="user",
            password="pass"
        )
        
        # Call cleanup
        cred.cleanup()
        
        # Verify os.remove was not called
        mock_remove.assert_not_called()

# Test error cases for OpenID authentication
def test_get_auth_missing_token_url():
    """Test get_auth with missing token_url for OpenID authentication."""
    cred = Credentials(
        odm_url="http://localhost:9060/res",
        client_id="client_id",
        client_secret="client_secret"
        # token_url is missing
    )
    
    with pytest.raises(ValueError, match="Both 'client_id' and 'token_url' are required for OpenId authentication."):
        cred.get_auth()

def test_get_auth_missing_client_id():
    """Test get_auth with missing client_id for OpenID authentication."""
    cred = Credentials(
        odm_url="http://localhost:9060/res",
        # client_id is missing
        client_secret="client_secret",
        token_url="http://auth.example.com/token"
    )
    
    with pytest.raises(ValueError, match="Both 'client_id' and 'token_url' are required for OpenId authentication."):
        cred.get_auth()

def test_get_auth_missing_client_secret():
    """Test get_auth with missing client_secret for standard OpenID authentication."""
    cred = Credentials(
        odm_url="http://localhost:9060/res",
        client_id="client_id",
        # client_secret is missing
        token_url="http://auth.example.com/token"
    )
    
    with pytest.raises(ValueError, match="Either 'client_secret' or 'pkjwt_key_path' is required for OpenId authentication."):
        cred.get_auth()

def test_get_unencrypted_key_data_wrong_password():
    """Test get_unencrypted_key_data with wrong password."""
    import tempfile
    import os
    
    # Create a temporary encrypted key file
    with tempfile.NamedTemporaryFile(delete=False, suffix='.key') as key_file:
        # This is just a placeholder, the actual content doesn't matter as we'll mock the decryption
        key_file.write(b"""-----BEGIN ENCRYPTED PRIVATE KEY-----
some content
-----END ENCRYPTED PRIVATE KEY-----""")
        key_path = key_file.name
    
    try:        
        # Mock the decryption to fail
        with patch('cryptography.hazmat.primitives.serialization.load_pem_private_key') as mock_load_key:
            mock_load_key.side_effect = Exception("Incorrect password, could not decrypt key")

            with pytest.raises(ValueError, match="Failed to decrypt private key with provided password: Incorrect password, could not decrypt key"):
                cred = Credentials(
                    odm_url="http://localhost:9060/res",
                    username="user",
                    password="pass",
                    mtls_key_path=key_path,
                    mtls_key_password="some password",
                    mtls_cert_path="some path"
                )
                cred.get_unencrypted_key_data(key_path, "wrong_password")
    
    finally:
        # Clean up the temporary file
        if os.path.exists(key_path):
            os.unlink(key_path)

# Test SSL certificate path handling
def test_ssl_cert_path():
    """Test SSL certificate path handling."""
    with patch('decision_mcp_server.Credentials.CustomHTTPAdapter') as mock_adapter_class:
        # Create credentials with custom SSL cert path
        cred = Credentials(
            odm_url="https://localhost:9060/res",
            username="user",
            password="pass",
            verify_ssl=True,
            verify_ssl_hostname=True,
            ssl_cert_path="/path/to/custom/cert"
        )
        
        # Get session to trigger adapter creation
        cred.get_session()
        
        # Verify adapter was created with the correct cert path
        mock_adapter_class.assert_called_with(certfile="/path/to/custom/cert", verify_ssl_hostname=True)

def test_ssl_cert_path_used_for_token_request():
    """When ssl_cert_path is provided, self.cacert must point to it so that
    the OpenID token POST uses the custom CA bundle, not the certifi default."""
    cred = Credentials(
        odm_url="https://localhost:9060/res",
        username="user",
        password="pass",
        verify_ssl=True,
        ssl_cert_path="/path/to/selfsigned.pem"
    )
    assert cred.cacert == "/path/to/selfsigned.pem"

def test_ssl_no_cert_path_falls_back_to_certifi():
    """When ssl_cert_path is not provided, self.cacert should be the certifi bundle."""
    import certifi
    cred = Credentials(
        odm_url="https://localhost:9060/res",
        username="user",
        password="pass",
        verify_ssl=True,
    )
    assert cred.cacert == certifi.where()

def test_ssl_verify_false_sets_cacert_none():
    """When verify_ssl is False, self.cacert should be None."""
    cred = Credentials(
        odm_url="https://localhost:9060/res",
        username="user",
        password="pass",
        verify_ssl=False,
    )
    assert cred.cacert is None

# ---------------------------------------------------------------------------
# Tests for create_credentials with a comma/semicolon-separated ssl-cert-path
# ---------------------------------------------------------------------------

def _make_args(**overrides):
    """Return a minimal argparse-like namespace for create_credentials tests."""
    defaults = dict(
        url="http://localhost:9060/res",
        runtime_url=None,
        username="odmAdmin",
        password="odmAdmin",
        zenapikey=None,
        client_id=None,
        client_secret=None,
        token_url=None,
        scope="openid",
        pkjwt_cert_path=None,
        pkjwt_key_path=None,
        pkjwt_key_password=None,
        mtls_cert_path=None,
        mtls_key_path=None,
        mtls_key_password=None,
        verifyssl="True",
        verifyssl_hostname="False",
        ssl_cert_path=None,
        console_auth_type=None,
        runtime_auth_type=None,
    )
    defaults.update(overrides)

    class _Namespace:
        pass

    ns = _Namespace()
    for k, v in defaults.items():
        setattr(ns, k, v)
    return ns


def test_create_credentials_single_ssl_cert_path(tmp_path):
    """A single cert path is passed through unchanged to Credentials."""
    cert_file = tmp_path / "ca.pem"
    cert_file.write_text("-----BEGIN CERTIFICATE-----\nABC\n-----END CERTIFICATE-----\n")

    args = _make_args(ssl_cert_path=str(cert_file))
    console_cred, runtime_cred = create_credentials(args)

    assert console_cred.cacert == str(cert_file)
    assert runtime_cred.cacert == str(cert_file)


def test_create_credentials_multi_ssl_cert_path_comma(tmp_path):
    """Two cert paths joined by comma are merged into a single temp file."""
    f_a = tmp_path / "a.pem"
    f_b = tmp_path / "b.pem"
    f_a.write_text("-----BEGIN CERTIFICATE-----\ncertA\n-----END CERTIFICATE-----\n")
    f_b.write_text("-----BEGIN CERTIFICATE-----\ncertB\n-----END CERTIFICATE-----\n")

    args = _make_args(ssl_cert_path=f"{f_a},{f_b}")
    console_cred, runtime_cred = create_credentials(args)

    # cacert must be a different (temp) file — not one of the originals
    assert console_cred.cacert != str(f_a)
    assert os.path.isfile(console_cred.cacert)

    # merge_ssl_cert_paths is now called once in the outer function, so both
    # credentials reference the same merged bundle.
    assert console_cred.cacert == runtime_cred.cacert

    merged_content = open(console_cred.cacert).read()
    assert "certA" in merged_content
    assert "certB" in merged_content
    os.unlink(console_cred.cacert)


def test_create_credentials_multi_ssl_cert_path_semicolon(tmp_path):
    """Two cert paths joined by semicolon are merged into a single temp file."""
    f_a = tmp_path / "a.pem"
    f_b = tmp_path / "b.pem"
    f_a.write_text("-----BEGIN CERTIFICATE-----\ncertA\n-----END CERTIFICATE-----\n")
    f_b.write_text("-----BEGIN CERTIFICATE-----\ncertB\n-----END CERTIFICATE-----\n")

    args = _make_args(ssl_cert_path=f"{f_a};{f_b}")
    console_cred, runtime_cred = create_credentials(args)

    assert os.path.isfile(console_cred.cacert)
    merged_content = open(console_cred.cacert).read()
    assert "certA" in merged_content
    assert "certB" in merged_content

    os.unlink(console_cred.cacert)


def test_create_credentials_no_ssl_cert_path():
    """When ssl_cert_path is None, credentials fall back to certifi."""
    import certifi
    args = _make_args(ssl_cert_path=None)
    console_cred, _ = create_credentials(args)
    assert console_cred.cacert == certifi.where()


# Made with Bob
