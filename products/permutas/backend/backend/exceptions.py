from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status


def custom_exception_handler(exc, context):
    """
    Custom exception handler that returns structured error responses.
    
    Response format:
    {
        "errors": [
            {
                "error": "ERROR_CODE",
                "message": "Human-readable message",
                "field": "field_name" (optional)
            }
        ],
        "path": "/api/...",
        "method": "POST"
    }
    """
    response = exception_handler(exc, context)
    
    if response is not None:
        if response.status_code == status.HTTP_400_BAD_REQUEST:
            structured_errors = []
            
            if isinstance(response.data, dict):
                for field, messages in response.data.items():
                    if isinstance(messages, list):
                        for message in messages:
                            structured_errors.append({
                                'error': 'VALIDATION_ERROR',
                                'message': str(message),
                                'field': field
                            })
                    else:
                        structured_errors.append({
                            'error': 'VALIDATION_ERROR',
                            'message': str(messages),
                            'field': field
                        })
            elif isinstance(response.data, list):
                for message in response.data:
                    structured_errors.append({
                        'error': 'VALIDATION_ERROR',
                        'message': str(message)
                    })
            else:
                structured_errors.append({
                    'error': 'VALIDATION_ERROR',
                    'message': str(response.data)
                })
            
            response.data = {
                'errors': structured_errors,
                'path': context['request'].path,
                'method': context['request'].method
            }
        
        elif response.status_code == status.HTTP_404_NOT_FOUND:
            response.data = {
                'errors': [{
                    'error': 'NOT_FOUND',
                    'message': 'Recurso não encontrado.'
                }],
                'path': context['request'].path,
                'method': context['request'].method
            }
        
        elif response.status_code == status.HTTP_401_UNAUTHORIZED:
            response.data = {
                'errors': [{
                    'error': 'UNAUTHORIZED',
                    'message': 'Credenciais inválidas ou não fornecidas.'
                }],
                'path': context['request'].path,
                'method': context['request'].method
            }
        
        elif response.status_code == status.HTTP_403_FORBIDDEN:
            response.data = {
                'errors': [{
                    'error': 'FORBIDDEN',
                    'message': 'Você não tem permissão para acessar este recurso.'
                }],
                'path': context['request'].path,
                'method': context['request'].method
            }
        
        elif response.status_code >= 500:
            response.data = {
                'errors': [{
                    'error': 'SERVER_ERROR',
                    'message': 'Ocorreu um erro interno. Tente novamente mais tarde.'
                }],
                'path': context['request'].path,
                'method': context['request'].method
            }
    
    return response
