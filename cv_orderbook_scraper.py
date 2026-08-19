import time
import mss
import cv2
import numpy as np
import pytesseract
import pyautogui

# --- KONFIGURASI PENTING ---
# Anda WAJIB mengganti path ini sesuai dengan lokasi Tesseract-OCR terinstal di Windows Anda!
# Secara default biasanya berada di C:\Program Files\Tesseract-OCR\tesseract.exe
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

def kalibrasi_koordinat():
    print("="*70)
    print("FASE KALIBRASI")
    print("Kita perlu memberi tahu bot area mana di layar yang harus dibaca.")
    print("Arahkan kursor mouse Anda ke POJOK KIRI ATAS dari salah satu kotak saham (misal BBCA).")
    print("Tahan mouse Anda di sana selama 4 detik...")
    time.sleep(4)
    x1, y1 = pyautogui.position()
    print(f"[*] Titik Pertama terekam di koordinat: X={x1}, Y={y1}")
    
    print("\nSekarang, arahkan kursor mouse Anda ke POJOK KANAN BAWAH dari tabel tersebut.")
    print("Tahan mouse Anda di sana selama 4 detik...")
    time.sleep(4)
    x2, y2 = pyautogui.position()
    print(f"[*] Titik Kedua terekam di koordinat: X={x2}, Y={y2}")
    print("="*70)
    
    w = x2 - x1
    h = y2 - y1
    
    if w <= 0 or h <= 0:
        print("[!] Kesalahan kalibrasi: Area terlalu kecil. Pastikan Anda bergerak dari Kiri-Atas ke Kanan-Bawah.")
        return None
        
    return {"top": y1, "left": x1, "width": w, "height": h}

def perjelas_gambar(image):
    # Ubah gambar ke abu-abu (grayscale)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    
    # Karena Ajaib memakai tema gelap (teks putih, background hitam),
    # Tesseract lebih suka teks hitam background putih. Jadi kita lakukan "Inversi" warna
    _, threshold_img = cv2.threshold(gray, 100, 255, cv2.THRESH_BINARY_INV)
    return threshold_img

def jalankan_pemantau():
    try:
        pytesseract.get_tesseract_version()
    except Exception:
        print("\n[!] ERROR FATAL: Tesseract OCR TIDAK DITEMUKAN!")
        print("Anda wajib mendownload dan menginstal software Tesseract OCR di Windows Anda.")
        print("Link Download: https://github.com/UB-Mannheim/tesseract/wiki")
        print("Jika sudah diinstal, pastikan path di baris 10 script ini sudah benar.\n")
        return

    area_tabel = kalibrasi_koordinat()
    if not area_tabel:
        return
        
    print("\n[+] Kalibrasi berhasil! Bot akan mulai mengambil screenshot layar Anda...")
    print("Tekan Ctrl+C di terminal ini untuk berhenti.\n")
    
    # Konfigurasi Tesseract (Hanya membaca angka dan titik/koma)
    # psm 6 = Asumsikan teks adalah satu blok kalimat yang beraturan
    custom_config = r'--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789.,'
    
    with mss.mss() as sct:
        try:
            while True:
                # Ambil screenshot di bagian yang sudah ditentukan
                screenshot = sct.grab(area_tabel)
                
                # Konversi ke format matrix OpenCV
                img = np.array(screenshot)
                
                # Perjelas gambar (Hitam Putih)
                img_bersih = perjelas_gambar(img)
                
                # --- OPSIONAL ---
                # Hapus tanda pagar di bawah ini jika Anda ingin melihat hasil jepretan layarnya secara langsung
                # cv2.imshow("Hasil Tangkapan Layar", img_bersih)
                # cv2.waitKey(1)
                
                # Proses gambar menjadi teks
                teks_terbaca = pytesseract.image_to_string(img_bersih, config=custom_config)
                
                waktu = time.strftime('%H:%M:%S')
                print(f"--- Hasil Bacaan OCR ({waktu}) ---")
                
                # Membersihkan teks kosong
                baris_teks = [b.strip() for b in teks_terbaca.split('\n') if b.strip()]
                for b in baris_teks:
                    print(b)
                
                print("-" * 50)
                time.sleep(3)
                
        except KeyboardInterrupt:
            print("\n[!] Bot pemantau dihentikan.")
            cv2.destroyAllWindows()

if __name__ == "__main__":
    jalankan_pemantau()
