import streamlit as st
from PIL import Image
import cv2
import numpy as np
import segno
import io
from pdf417decoder import PDF417Decoder
from pdf2image import convert_from_bytes

st.set_page_config(page_title="HUB3 u Revolut", page_icon="🇭🇷")

st.title("🇭🇷 HUB3 u Revolut")
st.markdown("Pretvorite hrvatske uplatnice (slike ili PDF) u QR kodove za mobilne banke.")

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
        
        # --- PAMETNA EKSTRAKCIJA ---
        iban = ""
        model = ""
        poziv = ""
        primatelj_lines = []
        
        # A. Traženje IBAN-a
        for d in data:
            clean_d = d.replace(" ", "")
            if clean_d.startswith("HR") and len(clean_d) > 15:
                iban = clean_d
                break
        
        # B. Traženje Modela (HRxx) i Poziva na broj
        for i, d in enumerate(data):
            if d.startswith("HR") and len(d) == 4:
                model = d
                if i + 1 < len(data):
                    poziv = data[i+1]
                break
        
        # C. Iznos (3. red u HUB3, index 2)
        iznos_str = data[2] if len(data) > 2 else "0"
        iznos = float(iznos_str) / 100 if iznos_str.isdigit() else 0.00
        
        # D. Primatelj
        if len(data) > 6:
            primatelj_lines = [data[6]]
            if len(data) > 7 and not data[7].startswith("HR"):
                primatelj_lines.append(data[7])
        
        primatelj = ", ".join(primatelj_lines)
        referenca = f"{model} {poziv}".strip()

        # 4. Generiranje EPC QR podataka
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
        
        with col2:
            st.image(out_img, caption="Skenirajte mobitelom")
            st.download_button("Spremi QR kod", out_img.getvalue(), "uplatnica_qr.png")

    except Exception as e:
        st.error(f"Greška pri obradi: {e}")

# --- GLAVNI PROGRAM ---
uploaded_file = st.file_uploader("Učitajte uplatnicu (JPG, PNG ili PDF)", type=['jpg', 'jpeg', 'png', 'pdf'])

if uploaded_file:
    file_extension = uploaded_file.name.split('.')[-1].lower()
    
    # Obrada ovisno o tipu datoteke
    if file_extension == 'pdf':
        try:
            # Pretvaramo prvu stranicu PDF-a u sliku visoke rezolucije (300 DPI)
            images = convert_from_bytes(uploaded_file.read(), dpi=300, first_page=1, last_page=1)
            if images:
                img = images[0].convert('RGB')
            else:
                st.error("Nije moguće pretvoriti PDF u sliku.")
                st.stop()
        except Exception as e:
            st.error(f"Greška pri čitanju PDF-a: {e}. Provjerite je li poppler instaliran.")
            st.stop()
    else:
        # Standardno učitavanje slike
        img = Image.open(uploaded_file)
        # Fix za prozirne PNG-ove (zamjena prozirnosti bijelom pozadinom)
        if img.mode in ('RGBA', 'LA'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[-1])
            img = background
        else:
            img = img.convert('RGB')

    st.image(img, caption="Učitani dokument", use_container_width=True)
    
    # Procesiranje bar koda
    decoder = PDF417Decoder(img)
    
    if decoder.decode() == 0:
        # Poboljšanje slike ako osnovni pokušaj ne uspije (grayscale + resize + threshold)
        cv_img = np.array(img)
        gray = cv2.cvtColor(cv_img, cv2.COLOR_RGB2GRAY)
        gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_LANCZOS4)
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        decoder = PDF417Decoder(Image.fromarray(thresh))
        decoder.decode()

    final_data = None
    if hasattr(decoder, 'barcodes_data') and decoder.barcodes_data:
        final_data = decoder.barcodes_data[0]
    elif hasattr(decoder, 'barcode_binary_data'):
        final_data = decoder.barcode_binary_data

    if final_data:
        parse_and_generate(final_data)
    else:
        st.error("❌ Bar kod nije pronađen. Ako je PDF, provjerite je li bar kod na prvoj stranici.")

with st.expander("Ručni unos teksta"):
    manual_text = st.text_area("Zalijepite sirovi tekst iz bar koda:")
    if st.button("Generiraj"):
        parse_and_generate(manual_text)
