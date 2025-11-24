import streamlit as st
import pandas as pd
import re

# Ünvan hiyerarşisi
unvan_priority = {
    "prof dr": "Prof. Dr.",
    "prof. dr": "Prof. Dr.",
    "doç dr": "Doç. Dr.",
    "doç. dr": "Doç. Dr.",
    "dr öğretim üyesi": "Dr. Öğr. Üyesi",
    "dr. öğretim üyesi": "Dr. Öğr. Üyesi",
    "dr öğrt üyesi": "Dr. Öğr. Üyesi",
    "dr. öğrt. üyesi": "Dr. Öğr. Üyesi",
    "öğr gör dr": "Öğr. Gör. Dr.",
    "öğr. gör. dr": "Öğr. Gör. Dr.",
    "öğr gör": "Öğr. Gör.",
    "öğr. gör": "Öğr. Gör."
}

def extract_unvan_and_name(raw):
    """
    Metinden unvanı ayıklar. En büyük unvanı seçer.
    Eğer unvan yoksa yalnızca ismi döner.
    """
    text = raw.lower().strip()

    found_unvan = None
    for key in unvan_priority:
        if key in text:
            if found_unvan is None:
                found_unvan = key
            else:
                # En büyük unvanı seçme
                if list(unvan_priority.keys()).index(key) < list(unvan_priority.keys()).index(found_unvan):
                    found_unvan = key

    # Ünvanı silip sadece ismi al
    clean_name = raw
    for key in unvan_priority:
        clean_name = re.sub(key, "", clean_name, flags=re.IGNORECASE)

    clean_name = clean_name.replace(".", "").strip()
    
    if found_unvan:
        final_unvan = unvan_priority[found_unvan]
        return final_unvan, clean_name
    else:
        return None, clean_name

st.set_page_config(page_title="Ders Saati Analiz Aracı", layout="wide")

st.title("🏫 Tıp Fakültesi Ders Saati Analiz Aracı")
st.write(
    "Bu arayüz, yüklediğiniz **Dönem 1–2–3 Excel dosyalarındaki** "
    "Kurul sayfalarından her hocanın **hangi kurulda kaç saat** derse girdiğini, "
    "bu derslerin neler olduğunu ve **ders bazlı filtrelemeyi** sağlar."
)

# --------------------------------------------------- #
#   1) Dosya yükleme                                   #
# --------------------------------------------------- #

st.sidebar.header("1️⃣ Excel dosyalarını yükle")

uploaded_files = st.sidebar.file_uploader(
    "Dönem Excel dosyalarını seçin (örn. Dönem 1, Dönem 2, Dönem 3)",
    type=["xlsx"],
    accept_multiple_files=True,
)

if not uploaded_files:
    st.info("Soldan en az bir Excel dosyası yüklemeden analiz yapılamaz.")
    st.stop()

# Her dosyaya bir dönem etiketi verelim (varsayılan: dosya adı)
st.sidebar.header("2️⃣ Dönem isimlerini kontrol et")
period_labels = {}
for uf in uploaded_files:
    default_label = uf.name.replace(".xlsx", "")
    period_labels[uf.name] = st.sidebar.text_input(
        f"'{uf.name}' için dönem adı", value=default_label
    )

# --------------------------------------------------- #
#   Yardımcı fonksiyon: Excel'den dersleri çekme      #
# --------------------------------------------------- #

def extract_from_excel(file_obj, period_label: str) -> pd.DataFrame:
    """
    Verilen Excel dosyasından 'kurul' içeren sayfaları tarar.
    Her sayfada:
      - A sütunu: Saat
      - B sütunu: Ders Kodu
      - C sütunu: Ders Adı
      - D sütunu: Ders Başlığı
      - E sütunu: Öğretim Üyesi
    yapısına göre hoca bazlı satırları çıkarır.
    """
    try:
        xls = pd.ExcelFile(file_obj)
    except Exception as e:
        st.error(f"{file_obj.name} okunamadı: {e}")
        return pd.DataFrame(
            columns=["saat", "ders_kodu", "ders_adi", "ders_basligi",
                     "ogretim_uyesi", "donem", "kurul"]
        )

    lectures_list = []

    for sheet in xls.sheet_names:
        sname_lower = sheet.lower()

        # Sadece Kurul sayfalarını al (toplam / SKT olanları at)
        if "kurul" not in sname_lower:
            continue
        if "skt" in sname_lower or "toplam" in sname_lower:
            continue

        df_sheet = xls.parse(sheet)

        # En az 5 sütun olmalı (Saat, Ders kodu, Ders adı, Ders başlığı, Öğretim üyesi)
        if df_sheet.shape[1] < 5:
            continue

        col_time, col_code, col_course, col_title, col_teacher = df_sheet.columns[:5]

        # Tamamen boşsa at
        if df_sheet[col_teacher].isna().all():
            continue

        mask = (
            df_sheet[col_teacher].notna()
            & df_sheet[col_code].notna()
            & df_sheet[col_course].notna()
        )

        # Başlık satırlarını ele (Öğretim Üyesi yazan satırları alma)
        mask &= df_sheet[col_teacher].astype(str).str.strip().ne("Öğretim Üyesi")

        sub = df_sheet.loc[mask, [col_time, col_code, col_course, col_title, col_teacher]].copy()
        if sub.empty:
            continue

        sub.columns = ["saat", "ders_kodu", "ders_adi", "ders_basligi", "ogretim_uyesi"]
        sub["donem"] = period_label
        sub["kurul"] = sheet

        lectures_list.append(sub)

    if lectures_list:
        out = pd.concat(lectures_list, ignore_index=True)
    else:
        out = pd.DataFrame(
            columns=["saat", "ders_kodu", "ders_adi", "ders_basligi",
                     "ogretim_uyesi", "donem", "kurul"]
        )
    return out

# --------------------------------------------------- #
#   2) Tüm dosyaları birleştir + isim normalize       #
# --------------------------------------------------- #

all_lectures = []

for uf in uploaded_files:
    period_label = period_labels.get(uf.name, uf.name.replace(".xlsx", ""))
    df_period = extract_from_excel(uf, period_label)
    all_lectures.append(df_period)

if not all_lectures:
    st.error("Hiç ders satırı bulunamadı. Kurul sayfaları yapısını kontrol edin.")
    st.stop()

df = pd.concat(all_lectures, ignore_index=True)

# Hoca adını temizle, 'raw' alanı sakla
df["ogretim_uyesi_raw"] = df["ogretim_uyesi"].astype(str).str.strip()
df = df[~df["ogretim_uyesi_raw"].isin(["", "0", "nan", "NaN"])]

if df.empty:
    st.error("Hoca satırı bulunamadı. Lütfen dosya içeriklerini kontrol edin.")
    st.stop()

# Küçük/büyük harf farklarını birleştirmek için anahtar üret
# Örn: "muammer özdemir" → hepsi tek kişi
name_key = df["ogretim_uyesi_raw"].str.lower()

# Aynı anahtar için ilk görülen yazımı 'kanonik' isim yapalım
name_map = {}
for raw_name, key in zip(df["ogretim_uyesi_raw"], name_key):
    if key not in name_map:
        name_map[key] = raw_name  # ilk görüleni kabul et

df["ogretim_uyesi"] = name_key.map(name_map)

# --------------------------------------------------- #
#   3) Filtre alanları (dönem, kurul, hoca, ders)     #
# --------------------------------------------------- #

st.sidebar.markdown("---")
st.sidebar.header("3️⃣ Filtreler")

# Hoca listesi (normalize edilmiş)
teacher_list = sorted(df["ogretim_uyesi"].unique())
secili_hoca = st.sidebar.selectbox(
    "Hoca filtresi",
    options=["(Tümü)"] + teacher_list,
)

# Dönem filtresi
secili_donem = st.sidebar.multiselect(
    "Dönem filtresi",
    options=sorted(df["donem"].unique()),
    default=sorted(df["donem"].unique()),
)

# Kurul filtresi
secili_kurul = st.sidebar.multiselect(
    "Kurul filtresi",
    options=sorted(df["kurul"].unique()),
    default=sorted(df["kurul"].unique()),
)

# Ders filtresi (ders adı bazlı)
ders_list = sorted(df["ders_adi"].dropna().astype(str).unique())
secili_ders = st.sidebar.multiselect(
    "Ders filtresi (Ders adı)",
    options=ders_list,
    default=ders_list,  # başlangıçta tüm dersler dahil
)

# --------------------------------------------------- #
#   4) Filtreleri df üzerine uygula                   #
# --------------------------------------------------- #

df_filtered = df.copy()

# Dönem & kurul filtresi
df_filtered = df_filtered[
    df_filtered["donem"].isin(secili_donem) & df_filtered["kurul"].isin(secili_kurul)
]

# Ders filtresi
if secili_ders:
    df_filtered = df_filtered[df_filtered["ders_adi"].astype(str).isin(secili_ders)]

# Hoca filtresi
if secili_hoca != "(Tümü)":
    df_filtered = df_filtered[df_filtered["ogretim_uyesi"] == secili_hoca]

if df_filtered.empty:
    st.warning("Seçili filtrelere göre kayıt bulunamadı.")
    st.stop()

# --------------------------------------------------- #
#   5) Özet tabloları filtrelenmiş df'den üret        #
# --------------------------------------------------- #

# Hoca bazında genel özet (filtrelenmiş veri üzerinden)
per_hoca_goster = (
    df_filtered.groupby("ogretim_uyesi", as_index=False)
    .agg(
        toplam_ders_saati=("saat", "count"),  # her satırı 1 ders saati kabul ettik
        komite_sayisi=("kurul", lambda x: x.nunique()),
        donem_sayisi=("donem", lambda x: x.nunique()),
    )
    .sort_values("toplam_ders_saati", ascending=False)
)

# Hoca / Dönem / Kurul bazında detay
per_kurul_goster = (
    df_filtered.groupby(["ogretim_uyesi", "donem", "kurul"], as_index=False)
    .agg(
        ders_sayisi=("saat", "count"),
        ders_kodlari=(
            "ders_kodu",
            lambda x: ", ".join(sorted(set(x.dropna().astype(str)))),
        ),
        ders_basliklari=(
            "ders_basligi",
            lambda x: " | ".join(sorted(set(x.dropna().astype(str)))),
        ),
        ders_adlari=(
            "ders_adi",
            lambda x: " | ".join(sorted(set(x.dropna().astype(str)))),
        ),
    )
)

per_kurul_goster["toplam_ders_saati"] = per_kurul_goster["ders_sayisi"]

# --------------------------------------------------- #
#   6) Görünüm                                       #
# --------------------------------------------------- #

st.subheader("👨‍🏫 Hocaların Toplam Ders Saatleri (Filtrelere Göre)")

st.dataframe(
    per_hoca_goster.reset_index(drop=True),
    use_container_width=True,
)

st.download_button(
    "⬇️ Hoca bazlı özeti CSV olarak indir",
    data=per_hoca_goster.to_csv(index=False).encode("utf-8-sig"),
    file_name="hoca_ozetleri.csv",
    mime="text/csv",
)

st.markdown("---")

st.subheader("📚 Hoca / Dönem / Kurul / Ders bazında detay (Filtrelere Göre)")

st.dataframe(
    per_kurul_goster.reset_index(drop=True),
    use_container_width=True,
)

st.download_button(
    "⬇️ Kurul bazlı detaylı tabloyu CSV olarak indir",
    data=per_kurul_goster.to_csv(index=False).encode("utf-8-sig"),
    file_name="hoca_donem_kurul_ders_detay.csv",
    mime="text/csv",
)

st.markdown("---")

st.subheader("🔍 Satır bazında ham veriler (Filtrelenmiş)")
with st.expander("Ham ders satırlarını göster"):
    st.dataframe(df_filtered.reset_index(drop=True), use_container_width=True)
