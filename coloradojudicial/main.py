import requests, time, csv, io, re
import datetime
import pytz

# ==========================================
# DECODO CONFIG
# ==========================================
API_URL = "https://scraper-api.decodo.com/v2/scrape"
TOKEN   = ""

api_headers = {
    "accept": "application/json",
    "content-type": "application/json",
    "authorization": f"Basic {TOKEN}",
}

# ==========================================
# SITE CONFIG — sadece bu bölüm değişecek
# ==========================================
SITE_NAME          = "Colorado Judicial Branch"
JUDICIAL_DISTRICT  = 4   # El Paso County → 4th District
COURT_LOCATION     = 21  # El Paso County Courthouse ID
CASE_CLASSES       = ['PR', 'DR', 'CV', 'C', 'M', 'CW', 'S']
CSV_OUTPUT         = "colorado_dockets.csv"

MAX_RETRIES = 5

# ==========================================
# TARİH HESAPLAMA (Colorado saati)
# ==========================================
colorado_tz = pytz.timezone('America/Denver')
today_co    = datetime.datetime.now(colorado_tz)
today_str   = today_co.strftime('%Y%m%d')   # export URL formatı: 20260512
scraped_at  = today_co.strftime('%m/%d/%Y %I:%M %p')

print(f"Tarih: {today_co.strftime('%m/%d/%Y')} | Site: {SITE_NAME}")
print(f"Case Classes: {', '.join(CASE_CLASSES)}")
print()


# ==========================================
# YARDIMCI: Decodo ile URL çek
# ==========================================
def fetch_url(url, use_headless=False):
    """
    Decodo ile URL'yi çeker.
    CSV endpoint'leri için use_headless=False tercih edilir.
    HTML sayfalar için use_headless=True.
    """
    payload = {"url": url}
    if use_headless:
        payload["headless"] = "html"

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.post(API_URL, json=payload, headers=api_headers, timeout=60)
            if r.ok:
                result = r.json().get("results", [{}])[0]
                content = result.get("content")
                status  = result.get("status_code", "?")
                if content:
                    return content, status
                print(f"  Deneme {attempt}: İçerik boş (status={status})")
            else:
                print(f"  Deneme {attempt}: HTTP {r.status_code}")
        except Exception as e:
            print(f"  Deneme {attempt}: Hata — {e}")
        time.sleep(15)
    return None, None


# ==========================================
# ANA DÖNGÜ: Her case class için CSV indir
# ==========================================
all_records = []

for cc in CASE_CLASSES:
    print(f"[{cc}] İndiriliyor...")

    export_url = (
        f"https://www.coloradojudicial.gov/dockets/export"
        f"?judicialDistrict={JUDICIAL_DISTRICT}"
        f"&datesEventScheduled%5B0%5D=20260201"     #{today_str}
        f"&datesEventScheduled%5B1%5D={today_str}"
        f"&caseClass={cc}"
        f"&courtLocations%5B0%5D={COURT_LOCATION}"
    )

    content, status_code = fetch_url(export_url, use_headless=False)

    if not content:
        print(f"  [{cc}] BAŞARISIZ — atlanıyor.\n")
        time.sleep(5)
        continue

    # İçerik CSV mi yoksa HTML mi kontrol et
    content_stripped = content.strip()
    is_csv = (
        not content_stripped.startswith('<') and
        (',' in content_stripped[:200] or '\t' in content_stripped[:200])
    )

    if is_csv:
        # CSV parse
        try:
            reader = csv.DictReader(io.StringIO(content_stripped))
            rows = list(reader)
            for row in rows:
                row['case_class']  = cc
                row['county']      = 'El Paso, CO'
                row['scraped_at']  = scraped_at
            all_records.extend(rows)
            print(f"  [{cc}] ✓ {len(rows)} kayıt")
        except Exception as e:
            print(f"  [{cc}] CSV parse hatası: {e}")
            print(f"  İçerik başlangıcı: {content_stripped[:300]}")
    else:
        # HTML döndü — headless ile tekrar dene
        print(f"  [{cc}] HTML döndü, headless ile tekrar deneniyor...")
        content2, _ = fetch_url(export_url, use_headless=True)
        if content2:
            # HTML içinden veri çıkarmayı dene (tablo var mı?)
            content2_stripped = content2.strip()
            if not content2_stripped.startswith('<'):
                # CSV geldi
                try:
                    reader = csv.DictReader(io.StringIO(content2_stripped))
                    rows = list(reader)
                    for row in rows:
                        row['case_class'] = cc
                        row['county']     = 'El Paso, CO'
                        row['scraped_at'] = scraped_at
                    all_records.extend(rows)
                    print(f"  [{cc}] ✓ {len(rows)} kayıt (headless)")
                except Exception as e:
                    print(f"  [{cc}] Headless CSV parse hatası: {e}")
            else:
                print(f"  [{cc}] Headless ile de HTML döndü — manuel inceleme gerekli")
                # İlk 500 karakteri kaydet
                with open(f"debug_{cc}.html", "w", encoding="utf-8") as f:
                    f.write(content2)
                print(f"  Debug dosyası kaydedildi: debug_{cc}.html")
        else:
            print(f"  [{cc}] Headless denemesi de başarısız.")

    print()
    time.sleep(5)  # Rate limiting


# ==========================================
# CSV KAYDET
# ==========================================
print("=" * 50)
if all_records:
    # Tüm sütunları topla (farklı case class'larda farklı sütun olabilir)
    all_keys = list(dict.fromkeys(
        key for record in all_records for key in record.keys()
    ))
    # scraped_at ve case_class'ı sona taşı
    for col in ['county', 'case_class', 'scraped_at']:
        if col in all_keys:
            all_keys.remove(col)
            all_keys.append(col)

    with open(CSV_OUTPUT, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=all_keys, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(all_records)

    print(f"CSV kaydedildi: {CSV_OUTPUT}")
    print(f"Toplam kayıt: {len(all_records)}")
    print(f"Sütunlar: {', '.join(all_keys)}")
else:
    print("Hiç kayıt toplanamadı.")