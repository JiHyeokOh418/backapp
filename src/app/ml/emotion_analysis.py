import asyncio
import logging
import os
from dataclasses import dataclass

import torch
from fastapi import Request
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from app.enums.common_enum import EmotionType

logger = logging.getLogger(__name__)

# 감정분석 모델 설정
# - KcELECTRA-base를 AI-Hub 감성대화말뭉치로 파인튜닝한 single-label 6분류 모델
# - 출처: https://huggingface.co/GGARA02/kcelectra-korean-emotion (AI허브 데이터 사용, aihub-terms-of-use)
# - 모델 파일 위치: HuggingFace 캐시 (~/.cache/huggingface/hub)
#   처음 로드할 때 config.json, model.safetensors(약 511MB), tokenizer.json, tokenizer_config.json을 받고,
#   이후에는 캐시에서 바로 읽는다.
# - revision은 커밋 해시로 고정한다. 저장소가 갱신되어도 같은 가중치를 쓰고, model_version에 해시가 남는다.
#
# [대안] 모델 파일을 프로젝트 폴더에 직접 두는 방식 (오프라인 서버, Docker 이미지에 모델을 포함할 때)
# - 위 4개 파일을 한 폴더(예: src/app/weight/kcelectra-korean-emotion/)에 두고
#   EMOTION_MODEL_NAME에 그 폴더 경로를 지정한다. (from_pretrained는 로컬 경로도 받는다. 이때 revision은 무시된다)
# - model.safetensors는 GitHub 파일 크기 제한(100MB)을 넘으므로 git에 커밋하지 않는다.
#   (.gitignore에 추가하고 Git LFS나 S3 등으로 따로 배포)
# - model_version이 model_name.split('/')[-1]로 만들어지므로, Windows 경로(\)를 쓰면 이름 추출 방식을 바꿔야 한다.
EMOTION_MODEL_NAME = os.getenv("EMOTION_MODEL_NAME", "GGARA02/kcelectra-korean-emotion")
EMOTION_MODEL_REVISION = os.getenv("EMOTION_MODEL_REVISION", "2eaf89d8d2cbfd902b93e5ec989db2ec103806fb")
# 기본은 cpu: 단건 추론은 cpu로도 충분히 빠르고, 개발 PC의 ROCm GPU에서는 ELECTRA 추론 중 커널 오류가 났다.
EMOTION_DEVICE = os.getenv("EMOTION_DEVICE", "cpu")
# CPU intra-op 스레드 수: 짧은 문장 단건 추론은 스레드가 많을수록 오히려 느려졌다. (8스레드 1.1s, 1스레드 0.04s)
# torch.set_num_threads는 프로세스 전역 설정이다.
EMOTION_NUM_THREADS = int(os.getenv("EMOTION_NUM_THREADS", "1"))
EMOTION_MAX_LENGTH = 128  # 학습 시 max sequence length와 맞춘다

# 모델 config의 id2label(한글) -> EmotionType
# 인덱스가 아니라 라벨 이름으로 매핑해서, 모델이 바뀌어 순서가 달라져도 잘못 저장되지 않게 한다.
LABEL_TO_EMOTION: dict[str, EmotionType] = {
    "분노": EmotionType.ANGER,
    "기쁨": EmotionType.JOY,
    "불안": EmotionType.ANXIETY,
    "당황": EmotionType.EMBARRASSMENT,
    "슬픔": EmotionType.SADNESS,
    "상처": EmotionType.HURT,
}


# 감정분석 결과 1건
# - 점수는 softmax 확률이라 6개의 합이 1이다. (감정별 강도가 아니라 "어느 감정인지"의 확률)
# - 필드 이름은 emotion_analyses 테이블 컬럼과 같다.
@dataclass(frozen=True)
class EmotionResult:
    anger: float
    joy: float
    anxiety: float
    embarrassment: float
    sadness: float
    hurt: float
    dominant: EmotionType
    model_version: str


class EmotionAnalyzer:
    def __init__(
        self,
        model_name: str = EMOTION_MODEL_NAME,
        revision: str = EMOTION_MODEL_REVISION,
        device: str = EMOTION_DEVICE,
        num_threads: int = EMOTION_NUM_THREADS,
    ):
        self.device = torch.device(device)
        if self.device.type == "cpu":
            torch.set_num_threads(num_threads)
        self.tokenizer = AutoTokenizer.from_pretrained(model_name, revision=revision)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_name, revision=revision)
        self.model.to(self.device)
        self.model.eval()

        # 모델 출력 인덱스 -> EmotionType (라벨이 예상과 다르면 로드 단계에서 바로 실패시킨다)
        id2label: dict[int, str] = self.model.config.id2label
        unknown = [label for label in id2label.values() if label not in LABEL_TO_EMOTION]
        if unknown or len(id2label) != len(LABEL_TO_EMOTION):
            raise ValueError(f"감정분석 모델 라벨이 예상과 다릅니다: {id2label}")
        self.index_to_emotion = [LABEL_TO_EMOTION[id2label[i]] for i in range(len(id2label))]

        # emotion_analyses.model_version (String(50)): 커밋 해시는 git처럼 앞 12자리만 남긴다.
        self.model_version = f"{model_name.split('/')[-1]}@{revision[:12]}"[:50]
        logger.info("감정분석 모델 로드 완료: %s (device=%s)", self.model_version, self.device)

    # 동기 추론 (CPU/GPU 연산이라 이벤트 루프에서 직접 호출하지 않는다)
    def predict(self, texts: list[str]) -> list[EmotionResult]:
        if not texts:
            return []

        inputs = self.tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=EMOTION_MAX_LENGTH,
            return_tensors="pt",
        ).to(self.device)

        with torch.inference_mode():
            probs = self.model(**inputs).logits.softmax(dim=-1).cpu().tolist()

        return [self._to_result(row) for row in probs]

    # 비동기 추론: 스레드로 넘겨서 요청 처리 루프를 막지 않는다.
    async def analyze(self, text: str) -> EmotionResult:
        results = await asyncio.to_thread(self.predict, [text])
        return results[0]

    async def analyze_batch(self, texts: list[str]) -> list[EmotionResult]:
        return await asyncio.to_thread(self.predict, texts)

    def _to_result(self, probs: list[float]) -> EmotionResult:
        scores = {emotion.value: prob for emotion, prob in zip(self.index_to_emotion, probs)}
        dominant = self.index_to_emotion[max(range(len(probs)), key=probs.__getitem__)]
        return EmotionResult(**scores, dominant=dominant, model_version=self.model_version)


# 주입 팩토리 함수
# - main.py lifespan이 app.state.emotion_analyzer에 올려 둔 모델을 꺼낸다.
# - 로드에 실패했으면 None이다. (호출하는 쪽은 감정분석 없이 진행)
def get_emotion_analyzer(request: Request) -> EmotionAnalyzer | None:
    return getattr(request.app.state, "emotion_analyzer", None)
