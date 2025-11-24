import streamlit as st
import pandas as pd

st.set_page_config(page_title="Ders Saati Analiz Aracı", layout="wide")

st.title("🏫 Tıp Fakültesi Ders Saati Analiz Aracı")
st.write(
    "Bu arayüz, yüklediğiniz **Dönem 1–2–3 Excel dosyalarındaki** "
    "Kurul sayfalarından her hocanın **hangi kurulda kaç saat** derse girdiğini "
    "ve bu derslerin hangileri olduğunu hesaplar."
)

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

st.sidebar.markdown("---")
st.sidebar.header("3️⃣ Filtreler")

# ------------------------------- #
#   Yardımcı fonksiyonlar         #
# ------------------------------- #

def extract_from_excel(file_obj, period_label: str) -> pd.DataFrame:
    """
    Verilen Excel dosyasından 'kurul' içeren sayfaları tarar.
    Her sayfada:
      - A sütunu: Saat
      - B sütunu: Ders Kodu
      - C sütunu: Ders Adı
      - D sütunu: Ders Başlığı
      - E sütunu: Öğretim Üyesi
      - F sütunu: Öğrenim Hedefi
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

        df = xls.parse(sheet)

        # En az 5 sütun olmalı (Saat, Ders kodu, Ders adı, Ders başlığı, Öğretim üyesi)
        if df.shape[1] < 5:
            continue

        col_time, col_code, col_course, col_title, col_teacher = df.columns[:5]

        # Tamamen boşsa at
        if df[col_teacher].isna().all():
            continue

        mask = (
            df[col_teacher].notna()
            & df[col_code].notna()
            & df[col_course].notna()
        )

        # Başlık satırlarını ele (Öğretim Üyesi yazan satırları alma)
        mask &= df[col_teacher].astype(str).str.strip().ne("Öğretim Üyesi")

        sub = df.loc[mask, [col_time, col_code, col_course, col_title, col_teacher]].copy()
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


# ------------------------------- #
#   Tüm dosyaları birleştirme     #
# ------------------------------- #

all_lectures = []

for uf in uploaded_files:
    period_label = period_labels.get(uf.name, uf.name.replace(".xlsx", ""))
    df_period = extract_from_excel(uf, period_label)
    all_lectures.append(df_period)

if not all_lectures:
    st.error("Hiç ders satırı bulunamadı. Kurul sayfaları yapısını kontrol edin.")
    st.stop()

df = pd.concat(all_lectures, ignore_index=True)

# Hoca adını temizle
df["ogretim_uyesi"] = df["ogretim_uyesi"].astype(str).str.strip()
# Tamamen saçma olanları (örn. 0) ele
df = df[~df["ogretim_uyesi"].isin(["0", "nan"])]

if df.empty:
    st.error("Hoca satırı bulunamadı. Lütfen dosya içeriklerini kontrol edin.")
    st.stop()

# ------------------------------- #
#   Özet tablolar                 #
# ------------------------------- #

# Hoca / Dönem / Kurul bazında
per_kurul = (
    df.groupby(["ogretim_uyesi", "donem", "kurul"], as_index=False)
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
    )
)

# Her satır 1 ders saati olduğu varsayımıyla:
per_kurul["toplam_ders_saati"] = per_kurul["ders_sayisi"]

# Sadece hoca bazında genel özet
per_hoca = (
    df.groupby("ogretim_uyesi", as_index=False)
    .agg(
        toplam_ders_saati=("saat", "count"),
        komite_sayisi=("kurul", lambda x: x.nunique()),
        donem_sayisi=("donem", lambda x: x.nunique()),
    )
    .sort_values("toplam_ders_saati", ascending=False)
)

# ------------------------------- #
#   Filtreler                     #
# ------------------------------- #

secili_hoca = st.sidebar.selectbox(
    "Hoca filtresi",
    options=["(Tümü)"] + sorted(per_hoca["ogretim_uyesi"].unique()),
)

secili_donem = st.sidebar.multiselect(
    "Dönem filtresi",
    options=sorted(df["donem"].unique()),
    default=sorted(df["donem"].unique()),
)

secili_kurul = st.sidebar.multiselect(
    "Kurul filtresi",
    options=sorted(df["kurul"].unique()),
    default=sorted(df["kurul"].unique()),
)

# Filtreleri uygula
mask_kurul = per_kurul["donem"].isin(secili_donem) & per_kurul["kurul"].isin(secili_kurul)
per_kurul_filtreli = per_kurul[mask_kurul].copy()

if secili_hoca != "(Tümü)":
    per_hoca_goster = per_hoca[per_hoca["ogretim_uyesi"] == secili_hoca]
    per_kurul_goster = per_kurul_filtreli[per_kurul_filtreli["ogretim_uyesi"] == secili_hoca]
else:
    per_hoca_goster = per_hoca.copy()
    per_kurul_goster = per_kurul_filtreli.copy()

# ------------------------------- #
#   Görünüm                       #
# ------------------------------- #

st.subheader("👨‍🏫 Hocaların Toplam Ders Saatleri")

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

st.subheader("📚 Hoca / Dönem / Kurul bazında detay")

st.dataframe(
    per_kurul_goster.reset_index(drop=True),
    use_container_width=True,
)

st.download_button(
    "⬇️ Kurul bazlı detaylı tabloyu CSV olarak indir",
    data=per_kurul_goster.to_csv(index=False).encode("utf-8-sig"),
    file_name="hoca_donem_kurul_detay.csv",
    mime="text/csv",
)

st.markdown("---")

st.subheader("🔍 Satır bazında ham veriler (isteğe bağlı)")
with st.expander("Ham ders satırlarını göster"):
    st.dataframe(df.reset_index(drop=True), use_container_width=True)
