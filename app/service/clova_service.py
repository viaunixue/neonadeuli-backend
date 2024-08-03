import logging
import json
import requests
import http.client
from typing import Dict, List
from http import HTTPStatus

from app.core.config import settings
from app.error.chat_exception import APICallException, ChatServiceException
from app.models.enums import ChatbotType
from app.utils.prompts import *

logger = logging.getLogger(__name__)

def parse_non_stream_response(response):
    result = response.get('result', {})
    message = result.get('message', {})
    content = message.get('content', '')
    return content.strip()

class CLOVAStudioExecutor:
    def __init__(self, host, api_key, api_key_primary_val, request_id):
        self._host = host
        self._api_key = api_key
        self._api_key_primary_val = api_key_primary_val
        self._request_id = request_id
  
    def _send_request(self, completion_request, endpoint):
        headers = {
            'Content-Type': 'application/json; charset=utf-8',
            'X-NCP-CLOVASTUDIO-API-KEY': self._api_key,
            'X-NCP-APIGW-API-KEY': self._api_key_primary_val,
            'X-NCP-CLOVASTUDIO-REQUEST-ID': self._request_id
        }
  
        conn = http.client.HTTPSConnection(self._host)
        conn.request('POST', endpoint, json.dumps(completion_request), headers)
        response = conn.getresponse()
        status = response.status
        result = json.loads(response.read().decode(encoding='utf-8'))
        conn.close()
        return result, status
  
    def execute(self, completion_request, endpoint):
        res, status = self._send_request(completion_request, endpoint)
        if status == HTTPStatus.OK:
            return res, status
        else:
            error_message = res.get("status", {}).get("message", "Unknown error") if isinstance(res, dict) else "Unknown error"
            raise ValueError(f"오류 발생: HTTP {status}, 메시지: {error_message}")

class ChatCompletionExecutor(CLOVAStudioExecutor):
    def __init__(self, host, api_key, api_key_primary_val, request_id):
        super().__init__(host, api_key, api_key_primary_val, request_id)
 
    def execute(self, completion_request, stream=True):
        headers = {
            'X-NCP-CLOVASTUDIO-API-KEY': self._api_key,
            'X-NCP-APIGW-API-KEY': self._api_key_primary_val,
            'X-NCP-CLOVASTUDIO-REQUEST-ID': self._request_id,
            'Content-Type': 'application/json; charset=utf-8',
            'Accept': 'text/event-stream' if stream else 'application/json'
        }
 
        with requests.post(self._host + '/testapp/v1/chat-completions/HCX-003',
                           headers=headers, json=completion_request, stream=stream) as r:
            if stream:
                if r.status_code == HTTPStatus.OK:
                    response_data = ""
                    for line in r.iter_lines():
                        if line:
                            decoded_line = line.decode("utf-8")
                            print(decoded_line)
                            response_data += decoded_line + "\n"
                    return response_data
                else:
                    raise ValueError(f"오류 발생: HTTP {r.status_code}, 메시지: {r.text}")
            else:
                if r.status_code == HTTPStatus.OK:
                    return r.json()
                else:
                    raise ValueError(f"오류 발생: HTTP {r.status_code}, 메시지: {r.text}")

class SlidingWindowExecutor(CLOVAStudioExecutor):

    def execute(self, completion_request):
        endpoint = '/v1/api-tools/sliding/chat-messages/HCX-003'
        try:
            # logger.info(f"SlidingWindowExecutor input: {sliding_window}")
            # completion_request = {"messages": sliding_window}
            logger.info(f"SlidingWindowExecutor request: {completion_request}")
            result, status = super().execute(completion_request, endpoint)
            logger.info(f"SlidingWindowExecutor result: {result}, status: {status}")
            if status == 200:
                # 슬라이딩 윈도우 적용 후 메시지를 반환
                return result['result']['messages']
            else:
                error_message = result.get('status', {}).get('message', 'Unknown error')
                raise ValueError(f"오류 발생: HTTP {status}, 메시지: {error_message}")
        except Exception as e:
            print(f"Error in SlidingWindowExecutor: {e}")
            raise

class ClovaService:
    '''
    input: session_id, content(sliding_window + user_input)
    output: clova x output
    '''
    def __init__(self):
        self.api_key = settings.CLOVA_API_KEY
        self.api_key_primary_val = settings.CLOVA_API_KEY_PRIMARY_VAL
        self.api_sliding_url = settings.CLOVA_SLIDING_API_HOST
        self.api_completion_url = settings.CLOVA_COMPLETION_API_HOST

    async def get_chatting(self, session_id: int, sliding_window: list) -> str:
        try:
            logger.info(f"get_chatting input - session_id: {session_id}, sliding_window: {sliding_window}")

            if sliding_window is None:
                sliding_window = []

            # Sliding Window 요청
            sliding_window_executor = SlidingWindowExecutor(
                host = self.api_sliding_url,
                api_key = self.api_key,
                api_key_primary_val= self.api_key_primary_val,
                request_id = str(session_id)
            )

            request_data = {
                "messages": [{"role": "system", "content": SYSTEM_PROMPT_CHATBOT}] + sliding_window,
                "maxTokens": 3000
            }

            adjusted_sliding_window = sliding_window_executor.execute(request_data)
            logger.info(f"Adjusted sliding window: {adjusted_sliding_window}")

            # 마지막 메시지 ASSISTANT 응답인 경우 이를 resopnse로 사용
            if adjusted_sliding_window[-1]['role'] == 'assistant':
                response_text = adjusted_sliding_window[-1]['content']
            else:
                # ASSISTANT 응답 없는 경우 Completion 요청 실행
                completion_executor = ChatCompletionExecutor(
                    host = self.api_completion_url,
                    api_key = self.api_key,
                    api_key_primary_val = self.api_key_primary_val,
                    request_id = str(session_id)
                )

                # Completion 요청 실행
                completion_request_data = {
                    "messages": adjusted_sliding_window,
                    "maxTokens": 400,
                    "temperature": 0.5,
                    "topK": 0,
                    "topP": 0.8,
                    "repeatPenalty": 1.2,
                    "stopBefore": [],
                    "includeAiFilters": True,
                    "seed": 0
                }

                logger.info(f"요청 데이터 완료: {completion_request_data}")
                response = completion_executor.execute(completion_request_data, stream=False)

                # 응답 로깅
                logger.info(f"세션 ID {session_id}에 대한 Raw한 API 응답 {response}")

                response_text = parse_non_stream_response(response)
                logger.info(f"세션 ID {session_id}에 대한 Parsed 된 응답 {response_text}")

                # 새로운 sliding window에 방금 얻은 response를 더해서 반환
                # adjusted_sliding_window.append({"role":"assistant", "content":response_text})
        
            # new_sliding_window 크기 관리
            new_sliding_window = self.manage_sliding_window_size(adjusted_sliding_window)

            return {"response": response_text, "new_sliding_window": new_sliding_window }
        except APICallException as e:
            logger.error(f"채팅 요청 처리 중 API 오류 발생: {e.api_name}, 상태 코드: {e.status_code}, 오류 메시지: {e.error_message}")
            raise ChatServiceException(f"채팅 요청 처리 중 API 오류 발생: {e.api_name}")
        except Exception as e:
            logger.error(f"채팅 요청 처리 중 예상치 못한 오류 발생: {str(e)}")
            raise ChatServiceException("채팅 요청 처리 중 오류 발생")

    # 여기서 퀴즈 버튼을 누를 때, 현재 위치의 이름을 받아와야 합니다. (ex - 근정전)
    # async def get_quiz(self, session_id: int, building_name: str) -> Dict[str, str]:
    async def get_info_or_quiz(self, session_id: int, building_name: str, request_type: ChatbotType) -> str:
        try:
            completion_executor = ChatCompletionExecutor(
                host = self.api_completion_url,
                api_key = self.api_key,
                api_key_primary_val = self.api_key_primary_val,
                request_id = str(session_id)
            )

            if request_type == "quiz":
                system_prompt = SYSTEM_PROMPT_QUIZ
                user_content = f"{building_name}에 대한 퀴즈를 생성해주세요."
            elif request_type == "info":
                system_prompt = SYSTEM_PROMPT_INFO
                user_content = f"{building_name}에 대해 설명해주세요."
            else:
                raise ValueError("유효하지 않은 요청 타입입니다. 반드시 퀴즈 또는 정보 타입이어야 합니다.")
            
            request_data = [
                {"role": "system", "content": system_prompt}, 
                {"role": "user", "content": user_content}
            ]

            completion_request_data = {
                "messages": request_data,
                "maxTokens": 300,
                "temperature": 0.5,
                "topK": 0,
                "topP": 0.8,
                "repeatPenalty": 1.2,
                "stopBefore": [],
                "includeAiFilters": True,
                "seed": 0
            }

            logger.info(f"{request_type.capitalize()} request data: {completion_request_data}")
            response = completion_executor.execute(completion_request_data, stream=False)
            logger.info(f"Raw API response for session ID {session_id}: {response}")
            
            # 경복궁의 중심이 되는 건물은 다음 중 무엇일까요?\n1. 근정전\n2. 사정전\n3. 교태전\n4. 강녕전\n5. 향원정 형식
            # 이 반환값이 full_conversation에 저장되어야 합니다.
            # 아니라면 퀴즈의 정답을 사용자가 선택할때까지 이 질문을 가지고 있어야 해요....
            response_text = parse_non_stream_response(response)
            logger.info(f"Parsed response for session ID {session_id}: {response_text}")

            return response_text
        
        except APICallException as e:
            logger.error(f"퀴즈 생성 중 API 오류 발생: {e.api_name}, 상태 코드: {e.status_code}, 오류 메시지: {e.error_message}")
            raise ChatServiceException(f"퀴즈 생성 중 API 오류 발생: {e.api_name}")
        except Exception as e:
            logger.error(f"퀴즈 생성 중 예상치 못한 오류 발생: {str(e)}")
            raise ChatServiceException("퀴즈 생성 중 오류 발생")

    # content는 돌았던 코스 텍스트가 담겨있으면 됩니다.
    async def get_summary(self, session_id: int, content: str) -> str:
        try:
            completion_executor = ChatCompletionExecutor(
                host = self.api_completion_url,
                api_key = self.api_key,
                api_key_primary_val = self.api_key_primary_val,
                request_id = str(session_id)
            )

            completion_request_data = {
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT_SUMMARY}, 
                    {"role":"user", "content": content}
                ],
                "maxTokens": 400,
                "temperature": 0.5,
                "topK": 0,
                "topP": 0.8,
                "repeatPenalty": 1.2,
                "stopBefore": [],
                "includeAiFilters": True,
                "seed": 0
            }

            response = completion_executor.execute(completion_request_data, stream=False)
            response_text = parse_non_stream_response(response)

            keywords = response_text.split()[1:]    # '너나들이' 키워드 제외
            return {"keywords": keywords}
        
        except APICallException as e:
            logger.error(f"요약 생성 중 API 오류 발생: {e.api_name}, 상태 코드: {e.status_code}, 오류 메시지: {e.error_message}")
            raise ChatServiceException(f"요약 생성 중 API 오류 발생: {e.api_name}")
        except Exception as e:
            logger.error(f"요약 생성 중 예상치 못한 오류 발생: {str(e)}")
            raise ChatServiceException("요약 생성 중 오류 발생")
        
    def manage_sliding_window_size(self, sliding_window: List[Dict[str, str]]) -> List[Dict[str, str]]:
        max_window_size = settings.MAX_SLIDING_WINDOW_SIZE
        if len(sliding_window) > max_window_size:
            return [sliding_window[0]] + sliding_window[-(max_window_size-1):]
        return sliding_window
    
    def update_sliding_window_system(self, sliding_window: List[Dict[str, str]], new_system_prompt: str) -> List[Dict[str, str]]:
        # system 메시지를 새로운 프롬프트로 교체
        updated_window = [{"role": "system", "content": new_system_prompt}]
        
        # 기존의 user와 assistant 메시지만 유지
        for message in sliding_window:
            if message['role'] in ['user', 'assistant']:
                updated_window.append(message)
        
        return updated_window