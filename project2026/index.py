import streamlit as st
import streamlit.components.v1 as components
from openai import OpenAI
from PIL import Image
import io
import base64
import re
import json
import hashlib

# -----------------------------
# 1. 페이지 설정
# -----------------------------
st.set_page_config(
    page_title="AI 시각 보조 시스템 made by 3116이지훈",
    page_icon="🦯",
    layout="wide"
)

st.title("🦯 AI 시각 보조 시스템")
st.markdown("사진을 촬영하면 주변을 분석하고 음성으로 안내합니다.")

# -----------------------------
# 2. 고정 설정값
# -----------------------------
BASE_URL = "https://aruba-ada-humanitarian-pros.trycloudflare.com/v1"
MODEL_NAME = "qwen3.5-9b"
SPEECH_RATE = 1.1
LANGUAGE_CODE = "ko-KR"

# -----------------------------
# 3. 세션 상태 초기화
# -----------------------------
if "last_spoken_text" not in st.session_state:
    st.session_state.last_spoken_text = ""

if "last_image_hash" not in st.session_state:
    st.session_state.last_image_hash = ""

if "analysis_count" not in st.session_state:
    st.session_state.analysis_count = 0

# -----------------------------
# 4. LM Studio 클라이언트
# -----------------------------
client = OpenAI(
    base_url=BASE_URL,
    api_key="lm-studio"
)

# -----------------------------
# 5. 유틸 함수
# -----------------------------
def image_to_base64(image: Image.Image) -> str:
    buffered = io.BytesIO()
    image = image.convert("RGB")
    image.save(buffered, format="JPEG", quality=85)
    return base64.b64encode(buffered.getvalue()).decode("utf-8")

def image_hash(uploaded_file) -> str:
    return hashlib.md5(uploaded_file.getvalue()).hexdigest()

def clean_model_output(raw_text: str) -> str:
    default_text = "[풍경: 알 수 없음, 보이는 사물: 알 수 없음, 위협 요소: 알 수 없음]"

    if not raw_text:
        return default_text

    text = raw_text.strip()
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE).strip()
    text = text.replace("<", "[").replace(">", "]").strip()

    if not text:
        return default_text

    if not text.startswith("["):
        text = f"[{text}]"

    required_tokens = ["풍경", "보이는 사물", "위협"]
    if not all(token in text for token in required_tokens):
        return default_text

    return text

def extract_result_text(response) -> str:
    """
    content만 우선 사용.
    reasoning_content는 읽지 않음.
    content가 비어 있으면 기본 문장 반환.
    """
    default_text = "[풍경: 알 수 없음, 보이는 사물: 알 수 없음, 위협 요소: 알 수 없음]"

    try:
        message = response.choices[0].message
        content = getattr(message, "content", None)

        if isinstance(content, str) and content.strip():
            return clean_model_output(content)

        return default_text
    except Exception:
        return default_text

def speak_text_via_browser(text: str):
    safe_text = json.dumps(text)

    js = f"""
    <script>
    (function() {{
        const synth = window.parent.speechSynthesis;
        if (!synth) return;

        synth.cancel();

        const utter = new SpeechSynthesisUtterance({safe_text});
        utter.lang = "{LANGUAGE_CODE}";
        utter.rate = {SPEECH_RATE};

        const voices = synth.getVoices();
        const koVoice = voices.find(v => v.lang && v.lang.toLowerCase().startsWith("ko"));
        if (koVoice) {{
            utter.voice = koVoice;
        }}

        synth.speak(utter);
    }})();
    </script>
    """
    components.html(js, height=0)

SYSTEM_PROMPT = """
너는 시각 장애인을 돕는 AI다.
반드시 최종 답변만 한국어로 짧게 출력해.
추론 과정, reasoning, think, 설명문은 절대 출력하지 마라.

반드시 아래 형식으로만 답해.
[풍경: ~, 보이는 사물: ~, 위협 요소: ~]

규칙:
- 풍경: 장소나 주변 환경
- 보이는 사물: 가장 중요하거나 가까운 사물
- 위협 요소: 이동에 위험할 수 있는 요소
- 불확실하면 알 수 없음이라고 써라
"""

# -----------------------------
# 6. UI
# -----------------------------
col1, col2 = st.columns([1.2, 1])

with col1:
    camera_photo = st.camera_input("사진을 촬영하세요")

with col2:
    st.subheader("상태")
    st.write(f"분석 횟수: {st.session_state.analysis_count}")
    st.write(f"마지막 출력: {st.session_state.last_spoken_text or '없음'}")

# -----------------------------
# 7. 분석
# -----------------------------
if camera_photo is not None:
    current_hash = image_hash(camera_photo)

    if current_hash != st.session_state.last_image_hash:
        st.session_state.last_image_hash = current_hash

        img = Image.open(camera_photo)
        b64_img = image_to_base64(img)

        with st.spinner("분석 중..."):
            try:
                response = client.chat.completions.create(
                    model=MODEL_NAME,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "사진을 분석해 줘."},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{b64_img}"
                                    }
                                }
                            ],
                        }
                    ],
                    temperature=0.1,
                    max_tokens=1000,
                )

                result = extract_result_text(response)

                st.session_state.analysis_count += 1
                st.success("분석 완료")
                st.markdown(f"### 🤖 AI 분석 결과\n{result}")

                # 새 사진이면 항상 읽기
                speak_text_via_browser(result)
                st.session_state.last_spoken_text = result

                finish_reason = response.choices[0].finish_reason
                if finish_reason == "length":
                    st.warning("모델 응답이 길이 제한으로 중간에 잘렸습니다. 다른 모델을 쓰거나 max_tokens를 더 늘리면 더 안정적일 수 있습니다.")

            except Exception as e:
                st.error(f"LM Studio 또는 모델 호출 오류: {e}")
    else:
        st.info("같은 사진입니다. 다른 사진을 촬영해 보세요.")
else:
    st.warning("카메라 권한을 허용한 뒤 사진을 촬영하세요.")
