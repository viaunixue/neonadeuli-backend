# 로깅 설정
import logging
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.deps import get_db
from app.error.heritage_exceptions import DatabaseConnectionError, HeritageNotFoundException, HeritageServiceException, InvalidCoordinatesException
from app.schemas.heritage import HeritageDetailResponse, HeritageListResponse
from app.service.heritage_service import HeritageService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

# 문화재 리스트 조회
@router.get("/lists", response_model=List[HeritageListResponse])
async def get_heritage_list(
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    user_latitude: float = Query(..., ge=-90, le=90),
    user_longitude: float = Query(..., ge=-180, le=180)
):
    try:
        heritage_service = HeritageService(db)
        heritages = await heritage_service.get_heritages(page, limit, user_latitude, user_longitude)
        return heritages
    except DatabaseConnectionError as e:
        logger.error(f"데이터 베이스 연결 에러: {str(e)}")
        raise HTTPException(status_code=503, detail="데이터 베이스를 사용할 수 없습니다.")
    except InvalidCoordinatesException as e:
        logger.warning(str(e))
        # 여기서는 400 에러를 반환하지 않고, 거리 정보가 없는 결과를 반환합니다.
        return []
    except HeritageServiceException as e:
        logger.error(f"문화재 서비스 에러: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"문화재 리스트 조회에서 예상치 못한 에러 발생: {str(e)}")
        raise HTTPException(status_code=500, detail="내부 서버 에러 발생")

# 문화재 상세 조회
@router.get("/{heritage_id}/details", response_model=HeritageDetailResponse)
async def get_heritage_detail(
    heritage_id: int,
    db: AsyncSession = Depends(get_db)
):
    try:
        heritage_service = HeritageService(db)
        heritage = await heritage_service.get_heritage_by_id(heritage_id)
        
        return heritage
    except HeritageNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HeritageServiceException as e:
        logger.error(f"문화재 서비스 에러 : {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"문화재 상세 조회에서 발생한 예상치 못한 에러: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")