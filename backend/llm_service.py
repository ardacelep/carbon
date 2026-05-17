import json
import os
import re
from typing import AsyncGenerator

from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic import ValidationError

from models import JobRecommendation, OptimalWindow
from workload_profiles import WORKLOAD_TYPES, resolve_power_kw

load_dotenv()

_client: AsyncOpenAI | None = None

MODEL = os.getenv("LLM_MODEL", "meta/llama-3.3-70b-instruct")              # chat + function calling
MODEL_SMALL = os.getenv("LLM_MODEL_SMALL", "meta/llama-3.1-8b-instruct")  # structured JSON output
MAX_TOKENS = 1024

TOOLS = [
    {"type": "function", "function": {
        "name": "get_current_carbon",
        "description": "Türkiye elektrik şebekesinin anlık karbon yoğunluğunu ve yenilenebilir enerji oranını döndürür",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }},
    {"type": "function", "function": {
        "name": "get_forecast",
        "description": "Önümüzdeki saatlerin karbon yoğunluğu tahminini döndürür",
        "parameters": {"type": "object", "properties": {
            "hours": {"type": "integer", "description": "Kaç saatlik tahmin isteniyor (1-48)", "default": 24},
        }, "required": []},
    }},
    {"type": "function", "function": {
        "name": "get_grid_status",
        "description": "Baraj doluluk oranı, PTF elektrik spot fiyatı, arz-talep dengesi ve şebeke stresini döndürür",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }},
    {"type": "function", "function": {
        "name": "find_best_window",
        "description": "Verilen iş yükü için en iyi çalışma zamanını hesaplar ve önerir. DB'ye kayıt yapmaz, sadece analiz eder.",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "İş adı (varsa) — güç tahmini için kullanılır"},
            "duration_hours": {"type": "number", "description": "İşin süresi saat cinsinden"},
            "power_kw": {"type": "number", "description": "İşin güç tüketimi kW. OPSİYONEL — kullanıcı kW değerini açıkça söylemediyse boş bırak; sistem iş tipinden hesaplar."},
            "workload_type": {"type": "string", "enum": WORKLOAD_TYPES, "description": "İş yükü tipi. power_kw verilmediyse iş adına/tanımına göre seç — güç tüketimi bu tipten belirlenir."},
            "cost_weight": {"type": "number", "description": "0.0=sadece karbon optimize et, 1.0=sadece elektrik maliyetini minimize et, 0.5=dengeli. Varsayılan 0.0", "default": 0.0},
        }, "required": ["duration_hours"]},
    }},
    {"type": "function", "function": {
        "name": "detect_anomaly",
        "description": "Şu anki karbon yoğunluğunun saatlik geçmiş baseline'a göre anormal olup olmadığını Z-score ile tespit eder. Anomali varsa severity ve öneri döndürür.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }},
    {"type": "function", "function": {
        "name": "create_job",
        "description": "Yeni bir iş oluşturur, optimal karbon penceresini hesaplar ve takvime ekler. Kullanıcı bir işi planlamak veya eklemek istediğinde bu aracı kullan.",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "İş adı (örn. 'ML Model Eğitimi', 'Veritabanı Yedekleme')"},
            "duration_hours": {"type": "number", "description": "İşin süresi saat cinsinden (0-72)"},
            "power_kw": {"type": "number", "description": "İşin güç tüketimi kW. OPSİYONEL — kullanıcı kW değerini açıkça söylemediyse boş bırak; sistem iş tipinden hesaplar. Sayı UYDURMA."},
            "workload_type": {"type": "string", "enum": WORKLOAD_TYPES, "description": "İş yükü tipi. power_kw verilmediyse iş adına/tanımına göre seç — güç tüketimi bu tipten belirlenir."},
            "priority": {"type": "integer", "description": "Öncelik: 1 (düşük) – 5 (acil). Varsayılan 1", "default": 1},
            "cost_weight": {"type": "number", "description": "0.0=sadece karbon, 1.0=sadece maliyet, 0.5=dengeli. Varsayılan 0.0", "default": 0.0},
            "deadline": {"type": "string", "description": "Opsiyonel son tarih, ISO-8601 formatında (örn. '2026-05-17T18:00:00+03:00')"},
        }, "required": ["name", "duration_hours"]},
    }},
]


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            base_url=os.getenv("LLM_BASE_URL", "https://integrate.api.nvidia.com/v1"),
            api_key=os.getenv("NVIDIA_API_KEY"),
        )
    return _client


_ALLOWED_TOOLS = {t["function"]["name"] for t in TOOLS}


async def _execute_tool(name: str, arguments: str, user_id: str | None = None) -> dict:
    if name not in _ALLOWED_TOOLS:
        return {"error": f"İzinsiz araç: {name}"}
    args = json.loads(arguments or "{}")

    if name == "get_current_carbon":
        from carbon_service import get_current_carbon
        r = await get_current_carbon()
        return {
            "carbon_intensity": r.carbon_intensity,
            "renewable_ratio": round(r.renewable_ratio * 100, 1),
            "timestamp": r.timestamp.strftime("%d.%m.%Y %H:%M"),
            "source": r.source,
        }

    if name == "get_forecast":
        from carbon_service import get_forecast
        hours = int(args.get("hours", 24))
        f = await get_forecast(hours)
        points = [
            {"hour": p.timestamp.strftime("%H:%M"), "carbon_intensity": p.carbon_intensity,
             "renewable_pct": round(p.renewable_ratio * 100, 1)}
            for p in f.points[:12]
        ]
        best = min(f.points, key=lambda p: p.carbon_intensity)
        return {
            "forecast_points": points,
            "best_hour": best.timestamp.strftime("%H:%M"),
            "best_intensity": best.carbon_intensity,
            "source": f.source,
        }

    if name == "get_grid_status":
        from grid_service import get_grid_status
        g = await get_grid_status()
        return {
            "dam_fullness_pct": g.dam_fullness_pct,
            "dam_trend": g.dam_trend,
            "ptf_tl_per_mwh": g.ptf_tl_per_mwh,
            "supply_demand_mw": g.supply_demand_mw,
            "grid_stress": g.grid_stress,
            "planned_outages_count": len(g.planned_outages),
        }

    if name == "find_best_window":
        from carbon_service import get_current_carbon, get_forecast
        from scheduler import find_optimal_window
        duration = max(0.5, float(args.get("duration_hours", 1)))
        pw = resolve_power_kw(args.get("name"), args.get("power_kw"), args.get("workload_type"))
        power = pw["power_kw"]
        cost_weight = float(args.get("cost_weight", 0.0))
        current = await get_current_carbon()
        forecast = await get_forecast(24)
        current_ptf = next((p.ptf_tl_per_mwh for p in forecast.points if p.ptf_tl_per_mwh), None)
        window = find_optimal_window(
            forecast, duration, None, power, current.carbon_intensity,
            cost_weight=cost_weight, current_ptf=current_ptf,
        )
        return {
            "start_time": window.start_time.strftime("%d.%m %H:%M"),
            "end_time": window.end_time.strftime("%H:%M"),
            "avg_carbon_intensity": window.avg_carbon_intensity,
            "estimated_savings_pct": window.estimated_savings_pct,
            "estimated_savings_tl": window.estimated_savings_tl,
            "reasoning": window.reasoning,
            "power_kw": power,
            "workload_type": pw["workload_type"],
            "workload_label": pw["label"],
            "power_source": pw["source"],
        }

    if name == "detect_anomaly":
        from anomaly_service import get_anomaly_report
        r = await get_anomaly_report()
        return {
            "is_anomaly": r.is_anomaly,
            "severity": r.severity,
            "z_score": r.z_score,
            "carbon_intensity": r.carbon_intensity,
            "hour": r.hour,
            "hour_mean": r.hour_mean,
            "hour_std": r.hour_std,
            "message": r.message,
            "recommendation": r.recommendation,
        }

    if name == "create_job":
        if not user_id:
            return {"error": "Kullanıcı kimliği doğrulanamadı, iş oluşturulamadı"}
        from carbon_service import get_current_carbon, get_forecast
        from scheduler import find_optimal_window
        from database import create_job as db_create_job
        from models import JobCreate
        from datetime import datetime, timezone, timedelta

        duration = max(0.5, float(args.get("duration_hours", 1)))
        pw = resolve_power_kw(args.get("name"), args.get("power_kw"), args.get("workload_type"))
        power = pw["power_kw"]
        priority = int(args.get("priority", 1))
        cost_weight = float(args.get("cost_weight", 0.0))
        deadline_str = args.get("deadline")
        deadline = datetime.fromisoformat(deadline_str) if deadline_str else None

        current = await get_current_carbon()
        forecast = await get_forecast(24)
        current_ptf = next((p.ptf_tl_per_mwh for p in forecast.points if p.ptf_tl_per_mwh), None)
        try:
            window = find_optimal_window(
                forecast, duration, deadline, power, current.carbon_intensity,
                cost_weight=cost_weight, current_ptf=current_ptf,
            )
        except ValueError:
            window = None

        job = JobCreate(
            name=args.get("name", "Yeni İş"),
            duration_hours=duration,
            power_kw=power,
            priority=priority,
            deadline=deadline,
            cost_weight=cost_weight,
        )
        row = await db_create_job(user_id, job, window, None)
        result = {
            "job_id": row["id"],
            "name": row["name"],
            "status": row["status"],
            "created_at": row.get("created_at", ""),
            "power_kw": power,
            "workload_type": pw["workload_type"],
            "workload_label": pw["label"],
            "power_source": pw["source"],
        }
        if window:
            result["optimal_window"] = {
                "start_time": window.start_time.strftime("%d.%m %H:%M"),
                "end_time": window.end_time.strftime("%H:%M"),
                "avg_carbon_intensity": window.avg_carbon_intensity,
                "estimated_savings_pct": window.estimated_savings_pct,
                "estimated_savings_tl": window.estimated_savings_tl,
                "reasoning": window.reasoning,
            }
        else:
            result["optimal_window"] = None
        return result

    return {"error": f"Bilinmeyen araç: {name}"}


def _grid_context_block(grid_context: dict | None) -> str:
    if not grid_context:
        return ""
    stress_labels = {"low": "Düşük", "medium": "Orta", "high": "Yüksek"}
    trend_labels = {"increasing": "artıyor", "stable": "sabit", "declining": "düşüyor"}
    dam = grid_context.get("dam_fullness_pct")
    trend = grid_context.get("dam_trend")
    ptf = grid_context.get("ptf_tl_per_mwh")
    sd = grid_context.get("supply_demand_mw")
    stress = grid_context.get("grid_stress", "low")
    dam_label = f"%{dam:.1f}" if dam is not None else "?"
    trend_label = trend_labels.get(trend, trend) if trend else "?"
    ptf_label = f"{ptf:.0f} ₺/MWh" if ptf is not None else "?"
    sd_label = f"{abs(sd):.0f} MW {'fazla' if sd and sd >= 0 else 'açık'}" if sd is not None else "?"
    return (
        f"\nŞebeke durumu:\n"
        f"- Baraj doluluk: {dam_label} ({trend_label})\n"
        f"- Spot fiyat (PTF): {ptf_label}\n"
        f"- Arz-talep: {sd_label}\n"
        f"- Şebeke stresi: {stress_labels.get(stress, stress)}"
    )


_SYSTEM_PROMPT = (
    "Sen Karbon Zeka'nın yapay zeka asistanısın. Türkiye elektrik şebekesinin karbon yoğunluğunu "
    "takip eden bir platformda çalışıyorsun.\n\n"
    "Görevin: Veri merkezi operatörlerine karbon bilinçli iş yükü zamanlaması konusunda Türkçe, "
    "net ve pratik tavsiyeler vermek.\n\n"
    "Elinde 6 araç var:\n"
    "- get_current_carbon: anlık karbon verisi\n"
    "- get_forecast: 24 saatlik tahmin\n"
    "- get_grid_status: şebeke durumu (baraj, PTF fiyatı, stres)\n"
    "- find_best_window: iş için optimal pencere hesapla (DB'ye kaydetmez, sadece analiz)\n"
    "- detect_anomaly: anlık karbon değerinin tarihsel baseline'a göre anormal olup olmadığını tespit et\n"
    "- create_job: iş oluştur ve takvime ekle (DB'ye kaydeder)\n\n"
    "ARAÇ SEÇİMİ KURALLARI:\n"
    "- Kullanıcı 'ekle', 'planla', 'takvime al', 'oluştur', 'schedule' gibi bir eylem istiyorsa "
    "create_job kullan. Sadece analiz veya öneri istiyorsa find_best_window yeterli.\n"
    "- Kullanıcı virgülle ayrılmış BİRDEN FAZLA iş adı veriyorsa, her iş için create_job'ı "
    "AYRI AYRI çağır. Tüm işler tamamlanana kadar durma, yanıt yazma.\n"
    "- İşleri oluşturduktan sonra hangi işlerin hangi zaman penceresine eklendiğini ve "
    "beklenen CO₂ tasarrufu yüzdesini Türkçe özetle.\n\n"
    "cost_weight parametresi: 0.0=sadece karbon optimize et (varsayılan), "
    "0.5=karbon ve elektrik maliyetini dengele, 1.0=sadece maliyeti minimize et.\n\n"
    "GÜÇ TÜKETİMİ (power_kw) KURALLARI:\n"
    "- Kullanıcı işin gücünü (kW) AÇIKÇA söylemediyse power_kw'yi BOŞ bırak — sayı UYDURMA.\n"
    "- Bunun yerine işin adına/tanımına bakıp workload_type seç: ml_training, fine_tuning, "
    "inference, batch_processing, database, backup, log_processing, sync, other. "
    "Güç tüketimini sistem bu tipe göre belirler.\n"
    "- Araç sonucunda power_source 'inferred' veya 'workload_type' ise, kullanıcıya hangi "
    "güç değerini neden varsaydığını belirt — örn. '~300 kW (ML model eğitimi tipik değeri) "
    "varsaydım; farklıysa kW belirterek düzeltebilirsiniz.'\n\n"
    "Yanıtlarında:\n"
    "- Somut sayılar ver (gCO2/kWh, kg tasarruf, saat, ₺ tasarruf)\n"
    "- Maksimum 3 kısa paragraf yaz\n"
    "- Her zaman Türkçe yanıt ver\n\n"
    "KRİTİK KURAL: Araç sonuçlarından gelen sayısal değerleri "
    "(gCO₂/kWh, kg CO₂, %, saat, ₺) TAM OLARAK kullan. Yuvarlama, tahmin veya değiştirme yapma. "
    "Bilmediğin bir değer varsa araç çağır, uydurma.\n\n"
    "KESİNLİKLE YASAK: JSON, Python kodu, araç şeması veya herhangi bir yapılandırılmış veri "
    "metni olarak çıktı verme. Araçları YALNIZCA API'nin function calling mekanizması üzerinden "
    "çağır — asla metin içinde yazma. Yanıtın her zaman doğal Türkçe olmalı."
)


def _looks_like_tool_call_json(text: str) -> bool:
    stripped = text.strip()
    if not (stripped.startswith("[") or stripped.startswith("{")):
        return False
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, list):
            return any(isinstance(i, dict) and ("type" in i or "name" in i) for i in parsed)
        if isinstance(parsed, dict):
            return "type" in parsed or "name" in parsed
    except Exception:
        pass
    return '"type": "function"' in text or '"name": "create_job"' in text


async def get_chat_response_with_tools(
    message: str,
    history: list[dict],
    user_id: str | None = None,
) -> tuple[str, bool]:
    messages = [{"role": "system", "content": _SYSTEM_PROMPT}]
    messages += history[-6:]
    messages.append({"role": "user", "content": message})
    jobs_created = False

    try:
        for _ in range(8):
            response = await _get_client().chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                max_tokens=MAX_TOKENS,
                temperature=0.3,
            )
            choice = response.choices[0]

            if choice.finish_reason == "tool_calls":
                messages.append(choice.message)
                for tool_call in choice.message.tool_calls:
                    result = await _execute_tool(
                        tool_call.function.name,
                        tool_call.function.arguments,
                        user_id=user_id,
                    )
                    if tool_call.function.name == "create_job" and "job_id" in result:
                        jobs_created = True
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    })
            else:
                content = choice.message.content.strip()
                if _looks_like_tool_call_json(content):
                    print("[llm_service] Hallüsinasyon tespit edildi: araç JSON metin olarak çıktı")
                    messages.append({"role": "assistant", "content": content})
                    messages.append({
                        "role": "user",
                        "content": (
                            "Türkçe, doğal dilde yanıt ver. JSON veya kod yazma. "
                            "İş oluşturmak istiyorsan function calling kullan, metin olarak yazma."
                        ),
                    })
                    continue
                return content, jobs_created

    except Exception as e:
        print(f"[llm_service] tool-calling hatası: {e}")

    return "Şu anda yapay zeka servisi kullanılamıyor. Lütfen daha sonra tekrar deneyin.", jobs_created


async def get_chat_response(
    message: str,
    history: list[dict],
    carbon_context: dict,
    grid_context: dict | None = None,
    user_id: str | None = None,
) -> str:
    reply, _ = await get_chat_response_with_tools(message, history, user_id=user_id)
    return reply


async def stream_chat_response(
    message: str,
    history: list[dict],
    carbon_context: dict,
    grid_context: dict | None = None,
    user_id: str | None = None,
) -> AsyncGenerator[str, None]:
    try:
        reply, jobs_created = await get_chat_response_with_tools(message, history, user_id=user_id)
    except Exception as e:
        print(f"[llm_service] streaming hatası: {e}")
        yield f"data: {json.dumps({'error': 'Yapay zeka servisi şu anda kullanılamıyor.'})}\n\n"
        yield "data: [DONE]\n\n"
        return

    for word in reply.split(" "):
        yield f"data: {json.dumps({'token': word + ' '})}\n\n"

    if jobs_created:
        yield f"data: {json.dumps({'jobs_changed': True})}\n\n"

    yield "data: [DONE]\n\n"


async def _analyze_carbon_context(
    current_intensity: float,
    optimal_window: OptimalWindow,
    grid_context: dict | None,
) -> str:
    """
    Pipeline Adım 1 — Serbest metin analizi.
    Karbon koşullarını değerlendirir; çıktısı Adım 2'ye bağlam olarak geçer.
    """
    grid_block = _grid_context_block(grid_context)
    start_str = optimal_window.start_time.strftime("%d.%m %H:%M")
    end_str = optimal_window.end_time.strftime("%H:%M")

    prompt = (
        f"Türkiye elektrik şebekesi karbon analisti olarak şu verileri değerlendir:\n\n"
        f"Anlık karbon yoğunluğu: {current_intensity:.1f} gCO2/kWh\n"
        f"Önerilen optimal pencere: {start_str}–{end_str}\n"
        f"Penceredeki ortalama yoğunluk: {optimal_window.avg_carbon_intensity:.1f} gCO2/kWh\n"
        f"Tahmini tasarruf: %{optimal_window.estimated_savings_pct:.0f}"
        f"{grid_block}\n\n"
        "2-3 cümleyle bu zaman diliminin neden uygun olduğunu, hangi enerji kaynaklarının belirleyici "
        "olduğunu ve dikkat edilmesi gereken riskleri belirt. Yalnızca analiz yaz."
    )

    try:
        response = await _get_client().chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.4,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[llm_service] pipeline adım-1 hatası: {e}")
        return optimal_window.reasoning  # scheduler reasoning ile devam et


_RETRY_CONFIDENCE = [0.92, 0.75, 0.58]
_RETRY_TEMPERATURES = [0.3, 0.5, 0.7]


def _parse_llm_json(text: str) -> dict:
    """LLM JSON çıktısını ayrıştırır; 3 strateji dener."""
    # 1. Kod bloğu temizle ve JSON nesnesini kes
    if "```" in text:
        for part in text.split("```")[1:]:
            stripped = part.lstrip("json").strip()
            if stripped.startswith("{"):
                text = stripped
                break
    start = text.find("{")
    end = text.rfind("}") + 1
    if start != -1 and end > start:
        candidate = text[start:end]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
        # 2. Kontrol karakterlerini temizle ve tekrar dene
        cleaned = re.sub(r"[\x00-\x1f\x7f]", " ", candidate)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

    # 3. Regex ile alan bazlı çıkarma (son çare)
    def _rstr(key):
        m = re.search(rf'"{key}"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
        return m.group(1) if m else ""

    def _rfloat(key):
        m = re.search(rf'"{key}"\s*:\s*([0-9]+(?:\.[0-9]+)?)', text)
        return float(m.group(1)) if m else 0.0

    result = {
        "window":      _rstr("window"),
        "date":        _rstr("date"),
        "savings_kg":  _rfloat("savings_kg"),
        "savings_pct": _rfloat("savings_pct"),
        "reasoning":   _rstr("reasoning"),
        "action":      _rstr("action"),
    }
    if result["window"] or result["reasoning"]:
        return result
    raise ValueError("JSON ayrıştırılamadı")


async def get_job_recommendation(
    job_name: str,
    duration_hours: float,
    power_kw: float,
    optimal_window: OptimalWindow,
    current_intensity: float,
    grid_context: dict | None = None,
) -> JobRecommendation | None:
    current_co2 = power_kw * duration_hours * current_intensity / 1000
    optimal_co2 = power_kw * duration_hours * optimal_window.avg_carbon_intensity / 1000
    saving_kg = round(current_co2 - optimal_co2, 2)
    start_str = optimal_window.start_time.strftime("%H:%M")
    end_str = optimal_window.end_time.strftime("%H:%M")
    date_str = optimal_window.start_time.strftime("%d.%m")
    safe_name = job_name.replace("\n", " ").replace("\r", " ")[:80]

    # === PIPELINE ADIM 1: Karbon bağlamını serbest metinle analiz et ===
    context_analysis = await _analyze_carbon_context(
        current_intensity, optimal_window, grid_context
    )

    # === PIPELINE ADIM 2: Adım 1 çıktısını bağlam olarak kullanarak yapılandırılmış öneri üret ===
    prompt = (
        f"Sen bir veri merkezi karbon optimizasyon uzmanısın.\n\n"
        f"=== BAĞLAM ANALİZİ (Pipeline Adım 1) ===\n"
        f"{context_analysis}\n\n"
        f"=== İŞ DETAYLARI ===\n"
        f"İş: {safe_name} | Süre: {duration_hours} sa | Güç: {power_kw} kW\n"
        f"Şu an: {current_co2:.2f} kg CO2 | Önerilen pencerede: {optimal_co2:.2f} kg CO2\n"
        f"Tasarruf: {saving_kg:.2f} kg CO2 (%{optimal_window.estimated_savings_pct:.0f})\n"
        f"Önerilen pencere: {date_str} {start_str}–{end_str}\n\n"
        "Yukarıdaki bağlam analizini referans alarak SADECE şu JSON formatında yanıt ver:\n"
        '{"window":"HH:MM–HH:MM","date":"DD.MM","savings_kg":X.X,"savings_pct":X.X,'
        '"reasoning":"kısa açıklama","action":"eylem cümlesi"}'
    )

    for temp, conf in zip(_RETRY_TEMPERATURES, _RETRY_CONFIDENCE):
        try:
            kwargs = dict(
                model=MODEL_SMALL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=512,
                temperature=temp,
            )
            try:
                response = await _get_client().chat.completions.create(
                    **kwargs, response_format={"type": "json_object"}
                )
            except Exception:
                response = await _get_client().chat.completions.create(**kwargs)
            text = response.choices[0].message.content.strip()
            data = _parse_llm_json(text)
            # Grounding: LLM sayılarını algoritmik değerlerle sabitle; reasoning/action LLM'den gelir.
            data["savings_kg"]       = round(saving_kg, 2)
            data["savings_pct"]      = round(optimal_window.estimated_savings_pct, 1)
            data["window"]           = f"{start_str}–{end_str}"
            data["date"]             = date_str
            data["confidence"]       = conf
            data["pipeline_context"] = context_analysis
            return JobRecommendation.model_validate(data)
        except (ValidationError, Exception) as e:
            print(f"[llm_service] öneri parse hatası (temp={temp}): {e}")

    print("[llm_service] 3 retry başarısız, None döndürülüyor")
    return None
