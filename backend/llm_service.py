import json
import os
from typing import AsyncGenerator

from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic import ValidationError

from models import JobRecommendation, OptimalWindow

load_dotenv()

_client: AsyncOpenAI | None = None

MODEL = "meta/llama-3.3-70b-instruct"        # chat + function calling
MODEL_SMALL = "meta/llama-3.1-8b-instruct"  # structured JSON output
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
        "description": "Verilen iş yükü için en düşük karbonlu çalışma zamanını hesaplar ve önerir",
        "parameters": {"type": "object", "properties": {
            "duration_hours": {"type": "number", "description": "İşin süresi saat cinsinden"},
            "power_kw": {"type": "number", "description": "İşin güç tüketimi kW cinsinden"},
        }, "required": ["duration_hours", "power_kw"]},
    }},
]


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=os.getenv("NVIDIA_API_KEY"),
        )
    return _client


_ALLOWED_TOOLS = {t["function"]["name"] for t in TOOLS}


async def _execute_tool(name: str, arguments: str) -> dict:
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
        duration = float(args.get("duration_hours", 1))
        power = float(args.get("power_kw", 100))
        current = await get_current_carbon()
        forecast = await get_forecast(24)
        window = find_optimal_window(forecast, duration, None, power, current.carbon_intensity)
        return {
            "start_time": window.start_time.strftime("%d.%m %H:%M"),
            "end_time": window.end_time.strftime("%H:%M"),
            "avg_carbon_intensity": window.avg_carbon_intensity,
            "estimated_savings_pct": window.estimated_savings_pct,
            "reasoning": window.reasoning,
        }

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
    "Elinde 4 araç var: anlık karbon verisi, 24 saatlik tahmin, şebeke durumu ve en iyi pencere hesaplama. "
    "Kullanıcı soru sorduğunda önce gerekli araçları çağır, sonra gerçek verilerle yanıt ver.\n\n"
    "Yanıtlarında:\n"
    "- Somut sayılar ver (gCO2/kWh, kg tasarruf, saat)\n"
    "- Maksimum 3 kısa paragraf yaz\n"
    "- Her zaman Türkçe yanıt ver\n\n"
    "KRİTİK KURAL: Araç sonuçlarından ve sana verilen verilerden gelen sayısal değerleri "
    "(gCO₂/kWh, kg CO₂, %, saat) TAM OLARAK kullan. Yuvarlama, tahmin veya değiştirme yapma. "
    "Bilmediğin bir değer varsa araç çağır, uydurma."
)


async def get_chat_response_with_tools(
    message: str,
    history: list[dict],
) -> str:
    messages = [{"role": "system", "content": _SYSTEM_PROMPT}]
    messages += history[-6:]
    messages.append({"role": "user", "content": message})

    try:
        for _ in range(5):
            response = await _get_client().chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                max_tokens=MAX_TOKENS,
                temperature=0.7,
            )
            choice = response.choices[0]

            if choice.finish_reason == "tool_calls":
                messages.append(choice.message)
                for tool_call in choice.message.tool_calls:
                    result = await _execute_tool(
                        tool_call.function.name,
                        tool_call.function.arguments,
                    )
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    })
            else:
                return choice.message.content.strip()

    except Exception as e:
        print(f"[llm_service] tool-calling hatası: {e}")

    return "Şu anda yapay zeka servisi kullanılamıyor. Lütfen daha sonra tekrar deneyin."


async def get_chat_response(
    message: str,
    history: list[dict],
    carbon_context: dict,
    grid_context: dict | None = None,
) -> str:
    return await get_chat_response_with_tools(message, history)


async def stream_chat_response(
    message: str,
    history: list[dict],
    carbon_context: dict,
    grid_context: dict | None = None,
) -> AsyncGenerator[str, None]:
    # Halüsinasyon önlemi: gerçek EPİAŞ verisini sistem promptuna ekle
    live_context = ""
    try:
        from carbon_service import get_current_carbon
        current = await get_current_carbon()
        live_context = (
            f"\n\nAnlık EPİAŞ verisi ({current.timestamp.strftime('%d.%m.%Y %H:%M')} itibarıyla):\n"
            f"- Karbon yoğunluğu: {current.carbon_intensity:.1f} gCO₂/kWh\n"
            f"- Yenilenebilir oran: %{current.renewable_ratio * 100:.1f}\n"
            f"- Kaynak: {current.source}\n"
            "Bu değerleri yanıtında olduğu gibi kullan."
        )
    except Exception:
        pass

    messages = [{"role": "system", "content": _SYSTEM_PROMPT + live_context}]
    messages += history[-6:]
    messages.append({"role": "user", "content": message})

    try:
        stream = await _get_client().chat.completions.create(
            model=MODEL,
            messages=messages,
            max_tokens=MAX_TOKENS,
            temperature=0.7,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content or ""
            if delta:
                yield f"data: {json.dumps({'token': delta})}\n\n"
    except Exception as e:
        print(f"[llm_service] streaming hatası: {e}")
        yield f"data: {json.dumps({'error': 'Yapay zeka servisi şu anda kullanılamıyor.'})}\n\n"
    finally:
        yield "data: [DONE]\n\n"


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

    grid_block = _grid_context_block(grid_context)

    safe_name = job_name.replace("\n", " ").replace("\r", " ")[:80]
    prompt = (
        f"Sen bir veri merkezi karbon optimizasyon uzmanısın.\n\n"
        f"İş: {safe_name} | Süre: {duration_hours} sa | Güç: {power_kw} kW\n"
        f"Şu an: {current_co2:.2f} kg CO2 | Önerilen pencerede: {optimal_co2:.2f} kg CO2\n"
        f"Tasarruf: {saving_kg:.2f} kg CO2 (%{optimal_window.estimated_savings_pct:.0f})\n"
        f"Önerilen pencere: {date_str} {start_str}–{end_str}"
        f"{grid_block}\n\n"
        "Yanıtını SADECE aşağıdaki JSON formatında ver, başka hiçbir şey yazma:\n"
        '{"window":"HH:MM–HH:MM","date":"DD.MM","savings_kg":X.X,"savings_pct":X.X,'
        '"reasoning":"kısa açıklama","action":"eylem cümlesi"}'
    )

    temperatures = [0.3, 0.5, 0.7]
    for temp in temperatures:
        try:
            response = await _get_client().chat.completions.create(
                model=MODEL_SMALL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=512,
                temperature=temp,
            )
            text = response.choices[0].message.content.strip()
            # JSON bloğu varsa çıkar
            if "```" in text:
                text = text.split("```")[1].lstrip("json").strip()
            start = text.find("{")
            end = text.rfind("}") + 1
            if start != -1 and end > start:
                text = text[start:end]
            rec = JobRecommendation.model_validate_json(text)
            # Sayı tutarlılığı: LLM'in ürettiği savings değerleri
            # hesaplananlardan ±5 puan veya ±%10 kg sapıyorsa override et
            pct_drift = abs(rec.savings_pct - optimal_window.estimated_savings_pct)
            kg_drift = abs(rec.savings_kg - saving_kg)
            if pct_drift > 5.0 or kg_drift > max(0.5, abs(saving_kg) * 0.10):
                print(
                    f"[llm_service] sayı sapması düzeltildi — "
                    f"savings_pct: {rec.savings_pct:.1f}→{optimal_window.estimated_savings_pct:.1f}, "
                    f"savings_kg: {rec.savings_kg:.2f}→{saving_kg:.2f}"
                )
                rec = rec.model_copy(update={
                    "savings_pct": round(optimal_window.estimated_savings_pct, 1),
                    "savings_kg": round(saving_kg, 2),
                })
            return rec
        except (ValidationError, Exception) as e:
            print(f"[llm_service] öneri parse hatası (temp={temp}): {e}")

    print(f"[llm_service] 3 retry başarısız, None döndürülüyor")
    return None
