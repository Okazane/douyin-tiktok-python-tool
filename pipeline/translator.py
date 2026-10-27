"""
Advanced Translation Engine (zh-CN -> vi) with AI LLM (Gemini) support,
Culinary & Vlog Glossary, and Contextual Post-processing.
"""
import os
import json
import time
import re
import logging
from dataclasses import dataclass
from pathlib import Path
from deep_translator import GoogleTranslator

from config import GEMINI_API_KEY, AI_KEY_FILE, AI_TRANSLATOR_MODEL
from pipeline.transcriber import Segment

logger = logging.getLogger(__name__)

@dataclass
class TranslatedSegment:
    """A translated segment with speaker role tagging."""
    id: int
    start: float
    end: float
    original_text: str  # Chinese
    translated_text: str  # Vietnamese
    role: str = "host"  # host (nam chính) | guest_female (nữ đối đáp) | guest_male (nam đối đáp) | child (trẻ em)

# 1. Tiền xử lý từ ngữ tiếng Trung trước khi dịch (để máy không dịch sai)
CHINESE_PRE_RULES = [
    (r'妹妹', '小妹'),
    (r'烤得很厉害', '烤得很香'),
    (r'臊子', '肉酱'),
    (r'老表', '表哥'),
    (r'下锅', '放入锅中'),
    (r'出锅', '盛出装盘'),
    (r'赶集', '去集市'),
    (r'摆摊', '摆摊售卖'),
]

# 2. Hậu xử lý văn phong tiếng Việt sau khi dịch
VI_POST_RULES = [
    (r'\bchị gái\b', 'em gái'),
    (r'\brất rang\b', 'nướng rất thơm'),
    (r'\bnảy mầm\b', 'kho'),
    (r'\bcá nảy mầm\b', 'cá kho'),
    (r'\bđề cập đến nó với bạn\b', 'kể cho mọi người nghe'),
    (r'\bngon tuyệt\b', 'ngon đỉnh chóp'),
    (r'\bmùi thơm quá\b', 'thơm phức luôn'),
    (r'\bnó ra khỏi nồi rồi\b', 'múc ra đĩa thôi'),
    (r'\băn lúc còn nóng\b', 'ăn nóng mới ngon'),
    (r'\bxuống nồi\b', 'cho vào chảo'),
    (r'\bra khỏi nồi\b', 'múc ra đĩa'),
    (r'\bchạy tập\b', 'đi chợ phiên'),
    (r'\blàm kinh tế\b', 'kiếm thêm thu nhập'),
]

SYSTEM_PROMPT = """Bạn là một Biên tập viên / Chuyên gia lồng tiếng và dịch phụ đề video TikTok hàng đầu Việt Nam.
Nhiệm vụ của bạn là dịch danh sách câu thoại tiếng Trung (khẩu ngữ vlog đời sống, nấu ăn ẩm thực Douyin của Điền Tây Tiểu Ca, Nhị Oa hoặc các nhà sáng tạo nội dung) sang tiếng Việt.

YÊU CẦU BẮT BUỘC VỀ VĂN PHONG VÀ NGÔN NGỮ:
1. ĐẠI TỪ XƯNG HÔ (BẮT BUỘC):
   - Nhân vật người nói CHÍNH trong video LUÔN XƯNG LÀ "TÔI" (tuyệt đối không xưng "mình", "em", "anh").
   - Gọi khán giả người xem là: "mọi người", "cả nhà", "các bạn".
   - Gọi người thân/hàng xóm đúng ngữ cảnh: "bà ngoại", "mẹ", "em gái", "bác", "chú", "chị".

2. VĂN PHONG SÚC TÍCH, NGẮN GỌN (QUAN TRỌNG NHẤT):
   - CẤM TUYỆT ĐỐI thêm các trợ từ ngữ khí thừa thãi (như: "nha mọi người", "luôn nè", "đấy nhé", "mọi người ơi", "nhỉ", "hả cả nhà").
   - Lược bỏ đại từ xưng hô nếu không cần thiết. Dùng từ đồng nghĩa ngắn nhất có thể.
   - Bản dịch khi đọc lên CẦN PHẢI NGẮN TƯƠNG ĐƯƠNG CÂU GỐC TIẾNG TRUNG để khớp hình ảnh.
   - Tuyệt đối loại bỏ từ ngữ dịch máy móc sáo rỗng. Càng ngắn gọn càng tốt.

3. TỪ NGỮ ẨM THỰC & NÔNG THÔN CHUẨN XÁC:
   - Dùng từ gợi cảm giác chân thực: chần sơ, phi thơm nức mũi, xào xém cạnh, sốt sánh quyện, giòn rụm, vàng ươm, ngọt thanh, đi chợ phiên, dọn sạp hàng...

4. NGẮT NHỊP DẤU CÂU CHO GIỌNG ĐỌC TTS:
   - Chèn dấu phẩy (,) và dấu chấm (.) hợp lý tại các vế câu để giọng đọc AI lấy hơi và ngắt nghỉ truyền cảm, không bị đọc dồn dập.

5. ĐỘ DÀI BẢN DỊCH — BẮT BUỘC TUÂN THỦ (QUAN TRỌNG NHẤT):
   - Mỗi câu trong input JSON có trường `duration_sec` = thời lượng tối đa được phép đọc.
   - Giọng đọc TTS tiếng Việt đọc khoảng 13–15 âm tiết/giây. Số âm tiết tối đa = duration_sec × 14.
   - Bản dịch PHẢI đủ ngắn để đọc vừa vặn trong `duration_sec` giây. Ưu tiên súc tích hơn đầy đủ ý.
   - Được phép lược bỏ thành phần phụ, trạng ngữ dài, giữ ý chính + cảm xúc cốt lõi.
   - Ví dụ bắt buộc: duration_sec=1.5 → tối đa 21 âm tiết (~10 từ). duration_sec=2.0 → tối đa 28 âm tiết (~13 từ).
   - KHÔNG dịch thêm ý, KHÔNG mở rộng câu, KHÔNG thêm từ ngữ nếu câu gốc đã ngắn.

6. PHÂN VAI HỘI THOẠI (SPEAKER ROLE TAGGING):
   - Phân loại vai người nói cho từng câu vào trường "role":
     - "host": Người dẫn chuyện / chủ kênh / người nấu chính (mặc định đa số).
     - "guest_female": Khách hàng nữ / phụ nữ mua hàng / người phụ nữ đối đáp với chủ kênh.
     - "guest_male": Khách hàng nam / người đàn ông khác đối đáp với chủ kênh.
     - "child": Trẻ em / giọng con nít đối đáp.

7. ĐỊNH DẠNG ĐẦU RA: Bắt buộc trả về duy nhất 1 mảng JSON thuần túy theo cấu trúc:
[
  {"id": 0, "translation": "Câu dịch tiếng Việt", "role": "host"},
  {"id": 1, "translation": "Bao nhiêu một xiên thế anh?", "role": "guest_female"}
]
Không thêm bất kỳ lời giải thích nào ngoài mảng JSON."""


def get_gemini_keys() -> list[str]:
    """Lấy danh sách Gemini API Keys từ config, env hoặc file gemini_key.txt."""
    keys = []
    if GEMINI_API_KEY and GEMINI_API_KEY.strip():
        keys.extend([k.strip() for k in GEMINI_API_KEY.split(',') if k.strip()])
    env_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if env_key and env_key.strip():
        keys.extend([k.strip() for k in env_key.split(',') if k.strip()])
    if AI_KEY_FILE.exists():
        c = AI_KEY_FILE.read_text(encoding='utf-8').lstrip('\ufeff')
        for line in c.splitlines():
            line = line.strip()
            if line and not line.startswith('#'):
                keys.append(line)
    return list(dict.fromkeys([k for k in keys if k]))

import asyncio
import httpx

async def _translate_batch_async(client, batch, prompt, key_cycle, models_to_try, batch_index):
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.2
        }
    }
    
    max_attempts = 6
    for attempt in range(max_attempts):
        current_key = next(key_cycle)
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": current_key
        }
        for model_name in models_to_try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
            try:
                logger.info(f"[Batch {batch_index}] Đang gửi sang Gemini ({model_name}, key ...{current_key[-4:]})...")
                r = await client.post(url, headers=headers, json=payload, timeout=25.0)
                
                if r.status_code == 200:
                    resp_json = r.json()
                    text_content = resp_json['candidates'][0]['content']['parts'][0]['text'].strip()
                    
                    if text_content.startswith("```"):
                        text_content = re.sub(r"^```(?:json)?\n|\n```$", "", text_content, flags=re.DOTALL)
                        
                    translated_list = json.loads(text_content)
                    trans_map = {item["id"]: item.get("translation", "").strip() for item in translated_list if "id" in item}
                    role_map = {item["id"]: item.get("role", "host").strip().lower() for item in translated_list if "id" in item}
                    
                    results = []
                    for s in batch:
                        vi_text = trans_map.get(s.id, s.text)
                        if vi_text:
                            vi_text = vi_text[0].upper() + vi_text[1:]
                        results.append(TranslatedSegment(
                            id=s.id, start=s.start, end=s.end,
                            original_text=s.text, translated_text=vi_text,
                            role=role_map.get(s.id, "host")
                        ))
                    return results

                elif r.status_code == 429:
                    logger.warning(f"[Batch {batch_index}] Rate limit 429 trên key ...{current_key[-4:]} -> Chuyển sang key tiếp theo...")
                    break
            except Exception as e:
                logger.warning(f"[Batch {batch_index}] Timeout/lỗi ({model_name}, key ...{current_key[-4:]}): {e} -> Chuyển tiếp...")
                continue
        await asyncio.sleep(1.0)
        
    logger.error(f"[Batch {batch_index}] Thất bại sau {max_attempts} lần thử.")
    return None


async def _extract_terminology_async(client, segments: list, api_key: str, models_to_try: list) -> str:
    """
    Trích xuất thuật ngữ ẩm thực, tên riêng, địa danh từ transcript.
    Trả về chuỗi glossary để truyền vào mọi batch dịch.
    """
    # Lấy tối đa 40 câu đầu đủ để AI hiểu ngữ cảnh
    sample_texts = [s.text for s in segments[:40]]
    all_text = " ".join(sample_texts)

    prompt = (
        "Bạn là chuyên gia thuật ngữ ẩm thực Trung-Việt.\n"
        f"Phân tích đoạn thoại tiếng Trung sau: '{all_text[:1500]}'\n\n"
        "Nhiệm vụ: Trích xuất danh sách thuật ngữ cần dịch NHẤT QUÁN gồm:\n"
        "- Tên món ăn, nguyên liệu, gia vị, dụng cụ nấu ăn\n"
        "- Tên địa danh, tên người, tên kênh\n"
        "- Từ địa phương, khẩu ngữ đặc trưng\n\n"
        "Trả về JSON dạng:\n"
        "{\"glossary\": [{\"zh\": \"凉皮\", \"vi\": \"lương bì\", \"note\": \"bánh lá lạnh\"}, ...]}\n"
        "Tối đa 20 thuật ngữ. Chỉ trả JSON, không giải thích."
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.1},
    }
    headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}

    for model in models_to_try[:3]:  # Chỉ thử 3 model đầu
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        try:
            r = await client.post(url, headers=headers, json=payload, timeout=15.0)
            if r.status_code == 200:
                text_content = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                if text_content.startswith("```"):
                    text_content = re.sub(r"^```(?:json)?\n|\n```$", "", text_content, flags=re.DOTALL)
                data = json.loads(text_content)
                terms = data.get("glossary", [])
                if terms:
                    lines = [f"  - {t['zh']} → {t['vi']} ({t.get('note','')})" for t in terms]
                    glossary_str = "TỪ ĐIỂN THUẬT NGỮ (bắt buộc dùng nhất quán):\n" + "\n".join(lines)
                    logger.info(f"[Glossary] Trích xuất {len(terms)} thuật ngữ: {[t['zh'] for t in terms]}")
                    return glossary_str
        except Exception as e:
            logger.debug(f"[Glossary] Lỗi model {model}: {e}")

    return ""  # Fallback: không có glossary


def _translate_with_gemini(segments: list[Segment], api_keys: list[str], video_context: dict = None) -> list[TranslatedSegment] | None:

    """Dịch toàn bộ segments bằng Google Gemini LLM qua REST API (Async Multi-Key)."""
    models_to_try = [
        "gemini-3.1-flash-lite",
        "gemini-flash-lite-latest",
        "gemini-3.5-flash-lite",
        "gemini-3.6-flash",
        "gemini-flash-latest"
    ]
    
    context_str = ""
    if video_context:
        title = video_context.get("title", "")
        author = video_context.get("author", "")
        tags = video_context.get("tags", [])
        context_str = (
            "\nTHÔNG TIN NGỮ CẢNH VIDEO:\n"
            f"- Tiêu đề Douyin: {title}\n"
            f"- Tác giả kênh: {author}\n"
            f"- Chủ đề/Tags: {', '.join(tags) if tags else 'Ẩm thực đời sống, nông thôn'}\n"
            "Hãy bám sát ngữ cảnh trên để dịch đúng tên nguyên liệu, trái cây, dụng cụ và đại từ xưng hô.\n"
        )
    
    BATCH_SIZE = 50
    import itertools
    key_cycle = itertools.cycle(api_keys)

    async def process_all():
        async with httpx.AsyncClient() as client:
            # ── C: Trích xuất glossary thuật ngữ (chạy trước, 1 API call duy nhất) ──
            glossary_str = ""
            try:
                key_for_glossary = next(itertools.cycle(api_keys))
                glossary_str = await _extract_terminology_async(
                    client, segments, key_for_glossary, models_to_try
                )
            except Exception as e:
                logger.debug(f"[Glossary] Bỏ qua do lỗi: {e}")

            tasks = []
            all_batches = list(range(0, len(segments), BATCH_SIZE))
            for i, idx in enumerate(all_batches):
                batch = segments[idx:idx + BATCH_SIZE]
                input_data = [
                    {"id": s.id, "duration_sec": round(s.end - s.start, 2), "text": s.text}
                    for s in batch
                ]

                # ── B: Context window — 3 câu cuối batch trước + 2 câu đầu batch sau ──
                prev_idx = all_batches[i - 1] if i > 0 else None
                next_idx = all_batches[i + 1] if i + 1 < len(all_batches) else None

                ctx_parts = []
                if prev_idx is not None:
                    prev_batch = segments[prev_idx:prev_idx + BATCH_SIZE]
                    prev_texts = [s.text for s in prev_batch[-3:]]
                    ctx_parts.append(f"NGỮ CẢNH - 3 câu VỪA NÓI TRƯỚC (dùng để nhất quán xưng hô):\n{chr(10).join(prev_texts)}")
                if next_idx is not None:
                    next_texts = [s.text for s in segments[next_idx:next_idx + 2]]
                    ctx_parts.append(f"NGỮ CẢNH - 2 câu SẮP NÓI TIẾP (xem trước):\n{chr(10).join(next_texts)}")

                context_window_str = ("\n" + "\n\n".join(ctx_parts) + "\n") if ctx_parts else ""

                prompt = (
                    f"{SYSTEM_PROMPT}\n"
                    f"{context_str}\n"
                    f"{glossary_str}\n"
                    f"{context_window_str}"
                    "Hãy dịch danh sách các câu thoại sau đây sang tiếng Việt chuẩn vlog ẩm thực đời sống TikTok:\n"
                    f"{json.dumps(input_data, ensure_ascii=False, indent=2)}"
                )
                tasks.append(_translate_batch_async(client, batch, prompt, key_cycle, models_to_try, i + 1))
            return await asyncio.gather(*tasks)


    logger.info(f"Đang dịch {len(segments)} câu bằng Async Multi-Key với {len(api_keys)} keys...")
    batch_results = asyncio.run(process_all())
    
    all_results = []
    for res in batch_results:
        if res is None:
            return None
        all_results.extend(res)
        
    logger.info(f"✅ Gemini AI đã dịch TRỌN VẸN thành công {len(all_results)} câu thoại cực tốc!")
    return all_results

def _preprocess_chinese(text: str) -> str:
    """Tiền xử lý tiếng Trung."""
    result = text
    for pattern, replacement in CHINESE_PRE_RULES:
        result = re.sub(pattern, replacement, result)
    return result

def _apply_glossary_and_humanizer(text: str) -> str:
    """Hậu xử lý văn phong tiếng Việt."""
    result = text
    for pattern, replacement in VI_POST_RULES:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    return result

def _translate_with_enhanced_google(segments: list[Segment]) -> list[TranslatedSegment]:
    """Dịch bằng Google Translate cải tiến kết hợp bộ từ điển ẩm thực và sửa lỗi ngữ cảnh."""
    translator = GoogleTranslator(source='zh-CN', target='vi')
    translated_segments = []
    
    batches = []
    current_batch = []
    current_length = 0
    
    for seg in segments:
        seg_len = len(seg.text)
        if current_length + seg_len + 5 > 4500 and current_batch:
            batches.append(current_batch)
            current_batch = [seg]
            current_length = seg_len
        else:
            current_batch.append(seg)
            current_length += seg_len + 5
            
    if current_batch:
        batches.append(current_batch)
        
    for batch in batches:
        batch_texts = [_preprocess_chinese(seg.text) for seg in batch]
        batch_text = '\n|||\n'.join(batch_texts)
        
        retries = 3
        backoffs = [1, 2, 4]
        success = False
        
        for i in range(retries):
            try:
                translated_batch = translator.translate(batch_text)
                translations = translated_batch.split('|||')
                
                for seg, trans in zip(batch, translations):
                    clean_trans = trans.strip()
                    clean_trans = _apply_glossary_and_humanizer(clean_trans)
                    clean_trans = ' '.join(clean_trans.split())
                    if clean_trans:
                        clean_trans = clean_trans[0].upper() + clean_trans[1:]
                        
                    translated_segments.append(TranslatedSegment(
                        id=seg.id,
                        start=seg.start,
                        end=seg.end,
                        original_text=seg.text,
                        translated_text=clean_trans
                    ))
                
                success = True
                time.sleep(0.3)
                break
                
            except Exception as e:
                logger.error(f"Lỗi dịch batch: {e}")
                if i < retries - 1:
                    time.sleep(backoffs[i])
                else:
                    raise RuntimeError("Lỗi kết nối khi dịch. Vui lòng kiểm tra mạng.") from e
                    
        if not success:
            raise RuntimeError("Không thể dịch, quá trình bị huỷ.")
            
    return translated_segments

# ────────────────────────────────────────────────────────────
#  BƯỚC 3.2 — AI SENIOR EDITOR / AUTO-PROOFREADER
# ────────────────────────────────────────────────────────────

PROOFREADER_SYSTEM_PROMPT = """Bạn là Biên tập viên cấp cao (Senior Editor) chuyên nội dung TikTok Việt Nam.
Nhiệm vụ của bạn là THẨM ĐỊNH và TINH CHỈNH bản dịch tiếng Việt đã có sẵn dưới đây theo 4 tiêu chuẩn khắt khe:

1. KHÓA ĐẠI TỪ XƯNG HÔ "TÔI" (BẮT BUỘC):
   - Rà soát toàn bộ đoạn hội thoại. Đảm bảo nhân vật chính LUÔN XƯNG LÀ "TÔI" xuyên suốt từ đầu đến cuối (tuyệt đối không để sót câu nào xưng "mình", "em", "anh").
   - Xưng với khán giả nhất quán: "mọi người", "cả nhà" hoặc "các bạn".

2. VĂN PHONG SÚC TÍCH, NGẮN GỌN (QUAN TRỌNG NHẤT):
   - Tuyệt đối KHÔNG ĐƯỢC thêm các từ đệm, từ xưng hô, trợ từ ngữ khí (như "nha mọi người", "luôn nè", "nhé", "hả cả nhà").
   - Viết lại các câu dài dòng thành những câu siêu ngắn gọn, gãy gọn, để vừa vặn với nhịp điệu nhanh.
   - Nếu bản dịch ban đầu dài hơn câu gốc tiếng Trung, PHẢI CẮT BỎ các từ thừa, rút gọn nó lại.

3. NGẮT NGHỈ HỢP LÝ BẰNG DẤU CÂU:
   - Thêm dấu phẩy (,) hợp lý để giọng đọc TTS ngắt nhịp tự nhiên, không đọc dồn dập.

4. CHUẨN HÓA TỪ NGỮ ẨM THỰC & NÔNG THÔN:
   - Đảm bảo các từ ngữ chuẩn người Việt: dầu hào, xì dầu, chần sơ, xào xém cạnh, sốt sánh quyện, giòn rụm, đậm đà, đi chợ phiên, dọn sạp hàng...

ĐỊNH DẠNG ĐẦU RA: Bắt buộc trả về duy nhất 1 mảng JSON thuần túy theo cấu trúc:
[
  {"id": 0, "translation": "Câu tiếng Việt đã tinh chỉnh"},
  {"id": 1, "translation": "Câu tiếng Việt đã tinh chỉnh"}
]
Không thêm bất kỳ lời giải thích nào ngoài mảng JSON."""

async def _proofread_batch_async(client, batch, prompt, key_cycle, models_to_try, batch_index):
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.3
        }
    }
    
    max_attempts = 3
    for attempt in range(max_attempts):
        current_key = next(key_cycle)
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": current_key
        }
        for model_name in models_to_try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
            try:
                logger.info(f"[AI Editor Batch {batch_index}] Thẩm định ({model_name}, key ...{current_key[-4:]})...")
                r = await client.post(url, headers=headers, json=payload, timeout=30.0)
                
                if r.status_code == 200:
                    resp_json = r.json()
                    text_content = resp_json['candidates'][0]['content']['parts'][0]['text'].strip()
                    
                    if text_content.startswith("```"):
                        text_content = re.sub(r"^```(?:json)?\n|\n```$", "", text_content, flags=re.DOTALL)
                        
                    reviewed_list = json.loads(text_content)
                    results = {}
                    for item in reviewed_list:
                        if "id" in item and "translation" in item:
                            t = item["translation"].strip()
                            if t:
                                t = t[0].upper() + t[1:]
                            results[item["id"]] = t
                    return results
                elif r.status_code == 429:
                    logger.warning(f"[AI Editor Batch {batch_index}] Rate limit trên key ...{current_key[-4:]}")
            except Exception as e:
                pass
        await asyncio.sleep(1.5)
        
    return {}

def _proofread_with_gemini(translated: list[TranslatedSegment], api_keys: str | list[str], video_context: dict = None) -> list[TranslatedSegment]:
    """Bước 3.2: AI Senior Editor — Tự động thẩm định (Async Multi-Key)."""
    import itertools
    if isinstance(api_keys, str):
        keys = [api_keys]
    else:
        keys = list(api_keys) if api_keys else [""]
    key_cycle = itertools.cycle(keys)

    models_to_try = [
        "gemini-3.1-flash-lite",
        "gemini-flash-lite-latest",
        "gemini-3.5-flash-lite",
        "gemini-flash-latest"
    ]

    context_str = ""
    if video_context:
        title = video_context.get("title", "")
        author = video_context.get("author", "")
        context_str = (
            f"\nNGỮ CẢNH: Kênh {author} - Tiêu đề: {title}\n"
            "Hãy đảm bảo đồng nhất 100% đại từ xưng hô và tên gọi món ăn/nguyên liệu từ đầu đến cuối kịch bản.\n"
        )

    BATCH_SIZE = 50
    
    async def process_all_proof():
        async with httpx.AsyncClient() as client:
            tasks = []
            for i, idx in enumerate(range(0, len(translated), BATCH_SIZE)):
                batch = translated[idx:idx + BATCH_SIZE]
                input_data = [
                    {
                        "id": seg.id,
                        "original_zh": seg.original_text,
                        "draft_vi": seg.translated_text,
                        "duration_sec": round(seg.end - seg.start, 2)
                    }
                    for seg in batch
                ]
                prompt = (
                    f"{PROOFREADER_SYSTEM_PROMPT}\n"
                    f"{context_str}\n"
                    "Dưới đây là danh sách câu thoại (có câu gốc tiếng Trung, bản dịch sơ bộ tiếng Việt và thời lượng mỗi câu).\n"
                    "Hãy thẩm định và tinh chỉnh toàn bộ:\n"
                    f"{json.dumps(input_data, ensure_ascii=False, indent=2)}"
                )
                tasks.append(_proofread_batch_async(client, batch, prompt, key_cycle, models_to_try, i+1))
            return await asyncio.gather(*tasks)

    logger.info(f"[AI Editor] Bắt đầu thẩm định song song {len(translated)} câu...")
    batch_results = asyncio.run(process_all_proof())
    
    all_results = {}
    for res in batch_results:
        all_results.update(res)

    final = []
    improved = 0
    for seg in translated:
        refined_text = all_results.get(seg.id)
        if refined_text and refined_text != seg.translated_text:
            improved += 1
        final.append(TranslatedSegment(
            id=seg.id,
            start=seg.start,
            end=seg.end,
            original_text=seg.original_text,
            translated_text=refined_text if refined_text else seg.translated_text,
            role=getattr(seg, "role", "host")
        ))

    logger.info(f"[AI Editor] ✅ Hoàn tất thẩm định — đã tinh chỉnh {improved}/{len(translated)} câu.")
    return final



async def condense_sentence_async(
    text: str,
    current_duration: float,
    target_duration: float,
    api_keys: list[str] | str,
    client,
) -> str:
    """
    Async — Rút gọn câu tiếng Việt cho vừa target_duration giây.
    Tự động xoay vòng đa key API và đa model khi gặp 429 (Rate limit) hoặc timeout.
    """
    if isinstance(api_keys, str):
        keys_to_use = [api_keys]
    else:
        keys_to_use = list(api_keys) if api_keys else []
    
    if not keys_to_use:
        return text

    max_syllables = int(target_duration * 14)
    prompt = (
        f"Câu tiếng Việt: '{text}'\n"
        f"Khi đọc TTS mất {current_duration:.1f}s nhưng chỉ cho phép {target_duration:.1f}s "
        f"(tối đa ~{max_syllables} âm tiết).\n"
        "Yêu cầu: Viết lại ngắn hơn, súc tích, khẩu ngữ TikTok tự nhiên, giữ ý chính. "
        "Chỉ trả về duy nhất câu đã viết lại, không giải thích thêm."
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 120},
    }

    models_to_try = [
        "gemini-3.1-flash-lite",
        "gemini-flash-lite-latest",
        "gemini-3.5-flash-lite",
        "gemini-flash-latest"
    ]

    for key in keys_to_use:
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": key,
        }
        for model in models_to_try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            try:
                r = await client.post(url, headers=headers, json=payload, timeout=6.0)
                if r.status_code == 200:
                    condensed = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                    condensed = condensed.strip("'\"")
                    if condensed and condensed != text:
                        logger.info(
                            f"[TTS Condenser] '{text[:35]}' ({current_duration:.1f}s) "
                            f"→ '{condensed[:35]}' (target={target_duration:.1f}s)"
                        )
                        return condensed
                elif r.status_code == 429:
                    # Key bị rate limit, chuyển sang key tiếp theo
                    break
            except Exception:
                continue

    return text



def condense_sentence(text: str, current_duration: float, target_duration: float) -> str:
    """Sync wrapper — Rút gọn câu tiếng Việt cho vừa target_duration giây."""
    import asyncio
    import httpx
    gemini_keys = get_gemini_keys()
    if not gemini_keys:
        return text

    async def _run():
        async with httpx.AsyncClient() as client:
            return await condense_sentence_async(
                text, current_duration, target_duration, gemini_keys[0], client
            )

    try:
        return asyncio.run(_run())
    except Exception as e:
        logger.warning(f"[TTS Condenser] Lỗi sync wrapper: {e}")
        return text




def _load_translation_cache() -> dict:
    from config import CACHE_DIR
    import json
    cache_path = CACHE_DIR / "translation_cache.json"
    if cache_path.exists():
        try:
            return json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"Lỗi đọc translation_cache.json: {e}")
    return {}

def _save_translation_cache(cache_dict: dict):
    from config import CACHE_DIR
    import json
    cache_path = CACHE_DIR / "translation_cache.json"
    try:
        cache_path.write_text(json.dumps(cache_dict, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"Lỗi lưu translation_cache.json: {e}")


def translate_segments(segments: list[Segment], video_context: dict = None) -> list[TranslatedSegment]:
    """Hàm điều phối dịch thuật 2 bước (Gemini AI Dịch sơ bộ -> AI Senior Editor Thẩm định) kết hợp Caching."""
    if not segments:
        return []

    gemini_keys = get_gemini_keys()
    
    # --- Caching Mechanism ---
    cache_dict = _load_translation_cache()
    cached_results = []
    uncached_segments = []
    
    for seg in segments:
        key = seg.text.strip()
        if key in cache_dict and cache_dict[key]:
            val = cache_dict[key]
            if isinstance(val, dict):
                trans_text = val.get("text", "")
                role = val.get("role", "host")
            else:
                trans_text = str(val)
                role = "host"
            cached_results.append(TranslatedSegment(
                id=seg.id,
                start=seg.start,
                end=seg.end,
                original_text=seg.text,
                translated_text=trans_text,
                role=role
            ))
        else:
            uncached_segments.append(seg)
            
    if cached_results:
        logger.info(f"[Cache] Đã tái sử dụng {len(cached_results)} câu dịch từ cache cục bộ (tiết kiệm API).")
        
    if not uncached_segments:
        cached_results.sort(key=lambda x: x.id)
        return cached_results

    # ── Bước 3.1: Dịch sơ bộ các câu chưa có trong cache ────────────────────────────────
    if gemini_keys:
        draft = _translate_with_gemini(uncached_segments, gemini_keys, video_context=video_context)
        if not draft:
            logger.warning("Gemini AI dịch thất bại, chuyển sang Google Translate dự phòng...")
            draft = _translate_with_enhanced_google(uncached_segments)
    else:
        draft = _translate_with_enhanced_google(uncached_segments)

    # ── Bước 3.2: AI Senior Editor tự động thẩm định & tinh chỉnh ───
    if gemini_keys and draft:
        logger.info(f"[AI Editor] Bắt đầu thẩm định tự động {len(draft)} câu bản dịch mới...")
        draft = _proofread_with_gemini(draft, gemini_keys, video_context=video_context)
        
    # Lấy kết quả lưu ngược lại vào cache
    new_cache_added = False
    for item in draft:
        key = item.original_text.strip()
        if key and item.translated_text:
            cache_dict[key] = {
                "text": item.translated_text,
                "role": getattr(item, "role", "host")
            }
            new_cache_added = True

            
    if new_cache_added:
        _save_translation_cache(cache_dict)

    # Gộp kết quả cache và kết quả mới, sắp xếp lại theo ID
    all_results = cached_results + draft
    all_results.sort(key=lambda x: x.id)
    
    return all_results


def translate_single(text: str) -> str:
    """Dịch một câu đơn lẻ."""
    gemini_keys = get_gemini_keys()
    if gemini_keys:
        seg = [Segment(id=0, start=0.0, end=1.0, text=text, confidence=1.0)]
        res = _translate_with_gemini(seg, gemini_key)
        if res:
            return res[0].translated_text

    try:
        translator = GoogleTranslator(source='zh-CN', target='vi')
        raw = translator.translate(text)
        return _apply_glossary_and_humanizer(raw)
    except Exception as e:
        logger.error(f"Single translation error: {e}")
        raise RuntimeError("Lỗi kết nối khi dịch. Vui lòng kiểm tra mạng.") from e

