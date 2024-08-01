class HeritageServiceException(Exception):
    """Heritage 서비스 기본 예외 클래스"""
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)

class SessionNotFoundException(HeritageServiceException):
    """채팅 세션을 찾을 수 없을 때 발생하는 예외"""
    def __init__(self, session_id: int):
        super().__init__(f"세션 ID {session_id}인 채팅 세션을 찾을 수 없습니다.")

class BuildingNotFoundException(HeritageServiceException):
    """건축물을 찾을 수 없을 때 발생하는 예외"""
    def __init__(self, building_id: int):
        super().__init__(f"건축물 ID {building_id}인 건축물을 찾을 수 없습니다.")

class InvalidAssociationException(HeritageServiceException):
    """건축물과 채팅 세션이 연관되지 않았을 때 발생하는 예외"""
    def __init__(self, session_id: int, building_id: int):
        super().__init__(f"세션 ID {session_id}와 건축물 ID {building_id}가 연관되어 있지 않습니다.")