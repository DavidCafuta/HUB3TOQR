import streamlit as st
from PIL import Image
import cv2
import numpy as np
import segno
import io
from pdf417decoder import PDF417Decoder

st.set_page_config(page_title="HUB3 u Revolut", page_icon="🇭🇷")

st.title("🇭🇷 HUB3 u Revolut")
st.markdown("Pretvorite hrvatske uplatnice u QR kodove za Revolut, Wise i ostale banke.")

def parse_and_generate(raw_data):
    """Parsira podatke i generira ispravan EPC QR kod."""
    try:
        # 1. Dekodiranje bytearray u UTF-8 string
        if isinstance(raw_data, (bytearray, bytes)):
            raw_data = raw_data.decode('utf-8', errors='ignore')
        
        # 2. Čišćenje redova
        lines = [line.strip() for line in raw_data.split('\n') if line.strip()]
        
        # 3. Pronalaženje početka HUB3 formata
        start_idx = -1
        for i, line in enumerate(lines):
            if "HRVHUB30" in line:
                start_idx = i
                break
        
        if start_idx == -1:
            st.error("Format nije prepoznat kao HRVHUB30.")
            st.code(raw_data)
            return

        data = lines[start_idx:]
        
        # --- PAMETNA EKSTRAKCIJA (Pretraživanje po uzorcima) ---
        iban = ""
        model = ""
        poziv = ""
        primatelj_lines = []
        
        # A. Traženje IBAN-a (HR + 19 znamenki)
        for d in data:
            clean_d = d.replace(" ", "")
            if clean_d.startswith("HR") and len(clean_d) > 15:
                iban = clean_d
                break
        
        # B. Traženje Modela (HRxx) i Poziva na broj
        for i, d in enumerate(data):
            if d.startswith("HR") and len(d) == 4: # npr. HR68, HR01
                model = d
                if i + 1 < len(data):
                    poziv = data[i+1]
                break
        
        # C. Iznos (uvijek 3. red u HUB3, index 2)
        iznos_str = data[2] if len(data) > 2 else "0"
        iznos = float(iznos_str) / 100 if iznos_str.isdigit() else 0.00
        
        # D. Primatelj (skupljamo redove koji nisu IBAN, iznos ili marker)
        # Obično su to redovi 4, 5 i 6 unutar HUB3 bloka
        if len(data) > 6:
            primatelj_lines = [data[6]]
            # Ako 7. red nije IBAN, vjerojatno je drugi dio adrese primatelja
            if len(data) > 7 and not data[7].startswith("HR"):
                primatelj_lines.append(data[7])
        
        primatelj = ", ".join(primatelj_lines)
        referenca = f"{model} {poziv}".strip()

        # 4. Generiranje EPC QR podataka
        # Revolut zahtijeva točan redoslijed: Service, Version, Encoding, Type, BIC, Name, IBAN, Amount, Purpose, Ref...
        epc_data = (
            f"BCD\n002\n1\nSCT\n\n"
            f"{primatelj[:70]}\n{iban}\n"
            f"EUR{iznos:.2f}\n"
            f"\n{referenca}\n\n"
            f"Uplata"
        )

        qr = segno.make(epc_data, error='M')
        out_img = io.BytesIO()
        qr.save(out_img, kind='png', scale=10)
        
        # --- PRIKAZ REZULTATA ---
        st.success(f"✅ Očitano: {iznos:.2f} EUR")
        
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("### Podaci za provjeru:")
            st.write(f"**Primatelj:** {primatelj}")
            st.write(f"**IBAN:** {iban}")
            st.write(f"**Poziv na broj:** {referenca}")
            st.info("💡 Ako je iznos 0.00, upišite ga ručno u bankovnoj aplikaciji.")
        
        with col2:
            st.image(out_img, caption="Skenirajte mobitelom (Revolut/Wise)")
            st.download_button("Spremi QR kod", out_img.getvalue(), "uplatnica_qr.png")

    except Exception as e:
        st.error(f"Greška pri obradi: {e}")
        st.info("Sirovi podaci za debugiranje:")
        st.code(raw_data)

# --- GLAVNI PROGRAM ---
uploaded_file = st.file_uploader("Učitajte sliku uplatnice (JPG ili PNG)", type=['jpg', 'jpeg', 'png'])

if uploaded_file:
    img = Image.open(uploaded_file).convert('RGB')
    st.image(img, caption="Učitana slika", use_container_width=True)
    
    decoder = PDF417Decoder(img)
    
    # Prvi pokušaj dekodiranja
    if decoder.decode() == 0:
        # Drugi pokušaj s procesiranjem slike ako prvi ne uspije
        cv_img = np.array(img)
        gray = cv2.cvtColor(cv_img, cv2.COLOR_RGB2GRAY)
        gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_LANCZOS4)
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        decoder = PDF417Decoder(Image.fromarray(thresh))
        decoder.decode()

    # Dohvat podataka iz dekodera
    final_data = None
    if hasattr(decoder, 'barcodes_data') and decoder.barcodes_data:
        final_data = decoder.barcodes_data[0]
    elif hasattr(decoder, '_decoded_results') and decoder._decoded_results:
        final_data = decoder._decoded_results[0]
    elif hasattr(decoder, 'barcode_binary_data'):
        final_data = decoder.barcode_binary_data

    if final_data:
        parse_and_generate(final_data)
    else:
        st.error("❌ Bar kod nije pronađen. Probajte bolje osvijetliti uplatnicu ili napraviti screenshot.")

# Opcija za ručni unos ako skener baš nikako ne radi
with st.expander("Ručni unos teksta (ako skener zakaže)"):
    manual_text = st.text_area("Zalijepite tekst ovdje:")
    if st.button("Generiraj iz teksta"):
        parse_and_generate(manual_text)
