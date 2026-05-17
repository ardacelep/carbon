"""İş yükü güç profilleri — gücün tek doğruluk kaynağı.

Veri merkezi iş tipleri için tipik güç tüketimi (kW). Değerler main.py'deki
JOB_TEMPLATES ile uyumludur. LLM iş tipini sınıflandırır (sınıflandırma onun
güçlü yanı); güç tüketimini bu profil belirler — LLM ham kW uydurmaz.
"""

WORKLOAD_PROFILES: dict[str, dict] = {
    "ml_training":      {"power_kw": 300.0, "label": "ML model eğitimi"},
    "fine_tuning":      {"power_kw": 250.0, "label": "model fine-tuning"},
    "inference":        {"power_kw": 120.0, "label": "model çıkarımı (inference)"},
    "batch_processing": {"power_kw": 150.0, "label": "toplu veri işleme"},
    "database":         {"power_kw": 100.0, "label": "veritabanı işlemi"},
    "backup":           {"power_kw": 80.0,  "label": "yedekleme"},
    "log_processing":   {"power_kw": 50.0,  "label": "log işleme"},
    "sync":             {"power_kw": 30.0,  "label": "veri senkronizasyonu"},
    "other":            {"power_kw": 100.0, "label": "genel iş yükü"},
}

DEFAULT_WORKLOAD = "other"
WORKLOAD_TYPES = list(WORKLOAD_PROFILES.keys())

# İş adından tip çıkarımı — sıralama önemli, spesifik kelimeler üstte.
_KEYWORD_RULES: list[tuple[tuple[str, ...], str]] = [
    (("fine-tun", "fine tun", "finetun", "ince ayar"), "fine_tuning"),
    (("eğit", "egit", "training", "ml model", "model eğit", "model egit"), "ml_training"),
    (("inference", "çıkarım", "cikarim", "serving", "model servis"), "inference"),
    (("yedek", "backup", "back up", "snapshot"), "backup"),
    (("log",), "log_processing"),
    (("senkron", "sync", "replikasyon", "replication", "mirror"), "sync"),
    (("batch", "toplu", "etl", "veri işle", "veri isle", "dönüşüm", "donusum"), "batch_processing"),
    (("veritaban", "database", "sql", "indeks", "index", "sorgu", "query"), "database"),
]


def infer_workload_type(name: str | None) -> str:
    """İş adındaki anahtar kelimelerden iş tipini tahmin eder."""
    low = (name or "").lower()
    for keywords, wtype in _KEYWORD_RULES:
        if any(k in low for k in keywords):
            return wtype
    return DEFAULT_WORKLOAD


def resolve_power_kw(
    name: str | None,
    explicit_power_kw: float | None = None,
    workload_type: str | None = None,
) -> dict:
    """İşin güç tüketimini çözümler.

    Öncelik: kullanıcının açıkça verdiği kW > LLM'in seçtiği workload_type
    > iş adından çıkarım > varsayılan.

    Döner: {"power_kw", "workload_type", "label", "source"}
      source ∈ {"explicit", "workload_type", "inferred"}
    """
    if explicit_power_kw is not None:
        try:
            val = float(explicit_power_kw)
        except (TypeError, ValueError):
            val = 0.0
        if val > 0:
            wtype = workload_type if workload_type in WORKLOAD_PROFILES else infer_workload_type(name)
            return {
                "power_kw": val,
                "workload_type": wtype,
                "label": WORKLOAD_PROFILES[wtype]["label"],
                "source": "explicit",
            }

    if workload_type in WORKLOAD_PROFILES:
        wtype = workload_type
        source = "workload_type"
    else:
        wtype = infer_workload_type(name)
        source = "inferred"

    return {
        "power_kw": WORKLOAD_PROFILES[wtype]["power_kw"],
        "workload_type": wtype,
        "label": WORKLOAD_PROFILES[wtype]["label"],
        "source": source,
    }
