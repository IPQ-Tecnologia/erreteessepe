def validate_user_access(user_id: str, device_name: str) -> bool:
    """
    Valida se o usuário pode acessar o device.
    Aqui você pode plugar:
    - banco
    - RBAC
    - ACL
    - JWT
    """
    return True
