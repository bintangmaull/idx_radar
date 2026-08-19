// --- PENGATURAN BOT ---
let isBotEnabled = true; 

// Variabel untuk menyimpan data detik sebelumnya (untuk menghitung momentum)
const previousData = {};

// Cache untuk Support & Resistance historis (supaya tidak spam fetch API)
const srCache = {};
const scanCache = {};
const signalState = {}; // Mencegah sinyal berkedip (flicker) terlalu cepat

// Fungsi untuk membersihkan teks dan mengubahnya menjadi angka
function cleanNumber(text) {
    if (!text) return 0;
    const cleaned = text.replace(/\./g, '').replace(/,/g, '').trim();
    return parseInt(cleaned, 10) || 0;
}

// Membuat Tombol ON/OFF Mengambang di Layar
function createToggleButton() {
    if (document.getElementById('ajaib-bot-toggle')) return;

    const btn = document.createElement('button');
    btn.id = 'ajaib-bot-toggle';
    btn.innerHTML = '🤖 Bot: <b>ON</b>';
    
    // Styling tombol
    btn.style.position = 'fixed';
    btn.style.bottom = '20px';
    btn.style.right = '20px';
    btn.style.zIndex = '999999';
    btn.style.padding = '10px 16px';
    btn.style.borderRadius = '50px';
    btn.style.border = 'none';
    btn.style.backgroundColor = '#10B981'; // Hijau jika ON
    btn.style.color = 'white';
    btn.style.fontFamily = 'Inter, sans-serif';
    btn.style.fontSize = '14px';
    btn.style.fontWeight = '600';
    btn.style.boxShadow = '0 4px 12px rgba(0,0,0,0.3)';
    btn.style.cursor = 'pointer';
    btn.style.transition = 'all 0.3s ease';

    // Logika saat tombol diklik
    btn.addEventListener('click', () => {
        isBotEnabled = !isBotEnabled; 
        
        if (isBotEnabled) {
            btn.innerHTML = '🤖 Bot: <b>ON</b>';
            btn.style.backgroundColor = '#10B981'; 
        } else {
            btn.innerHTML = '🤖 Bot: <b>OFF</b>';
            btn.style.backgroundColor = '#EF4444'; 
            document.querySelectorAll('.ajaib-scalping-badge').forEach(b => b.remove());
        }
    });

    btn.addEventListener('mouseenter', () => btn.style.transform = 'scale(1.05)');
    btn.addEventListener('mouseleave', () => btn.style.transform = 'scale(1)');

    document.body.appendChild(btn);
}

// Fungsi utama untuk memantau orderbook dan memberikan sinyal
function evaluateOrderbook() {
    createToggleButton(); 
    if (!isBotEnabled) return;

    const widgets = document.querySelectorAll('div[data-testid="orderbook-table"]');
    
    widgets.forEach((widget) => {
        if (!widget.classList.contains('ajaib-scalping-container')) {
            widget.classList.add('ajaib-scalping-container');
            widget.style.position = 'relative'; 
            
            if (!widget.querySelector(`.ajaib-scalping-badge`)) {
                const badge = document.createElement('div');
                badge.className = 'ajaib-scalping-badge ajaib-scalping-neutral';
                widget.appendChild(badge);
            }
        }
        
        const badge = widget.querySelector('.ajaib-scalping-badge');
        if (!badge) return;

        let stockCode = "UNKNOWN";
        let pricePercentage = 0; // Untuk menyimpan tren harga (%)
        let currentPrice = 0; // Menyimpan harga riil saat ini

        // ALGORITMA PENCARIAN DOM SUPER AKURAT (V5 - Isolasi Widget)
        // Berjalan ke atas dari tabel Orderbook lapis demi lapis.
        let wrapper = widget;
        for (let i = 0; i < 15; i++) {
            if (!wrapper || wrapper.tagName === 'BODY') break;
            
            // CEGAH BOCOR: Jika wrapper sudah mencakup orderbook lain, kita naik terlalu tinggi! Hentikan.
            if (wrapper.querySelectorAll('div[data-testid="orderbook-table"]').length > 1) {
                break; 
            }
            
            // METODE 1: Cari elemen <a> yang mengarah ke halaman saham
            const stockLink = wrapper.querySelector('a[href*="/stock/"]');
            if (stockLink) {
                const match = stockLink.getAttribute('href').match(/\/stock\/([A-Z]{4})/);
                if (match) stockCode = match[1];
            }
            
            // METODE 2: Jika tidak ada link, cari kata 4 huruf kapital murni
            if (stockCode === "UNKNOWN") {
                let textToParse = wrapper.textContent || "";
                // Hapus teks dari badge kita sendiri agar kata seperti "FAST" (FAST BUY) tidak terbaca sbg kode saham
                const badgeEl = wrapper.querySelector('.ajaib-scalping-badge');
                if (badgeEl && badgeEl.textContent) {
                    textToParse = textToParse.replace(badgeEl.textContent, "");
                }
                
                // Pisahkan teks berdasarkan karakter yang bukan huruf kapital (A-Z)
                const words = textToParse.split(/[^A-Z]+/); 
                for (let word of words) {
                    if (word.length === 4 && !["FREQ", "PREV", "HIGH", "OPEN", "NONE", "SELL", "IHSG", "IDR"].includes(word)) {
                        stockCode = word;
                        break;
                    }
                }
            }

            // Jika kode saham sudah ditemukan, ektrak harga dan hentikan pencarian ke atas
            if (stockCode !== "UNKNOWN") {
                const textInfo = wrapper.textContent;
                // Ekstrak harga terakhir dan persentase secara bersamaan
                // Format Ajaib: 4770 -20 (-0.42%) atau 6.325 25 (+0.40%)
                const priceMatch = textInfo.match(/([\d\.]+)\s+[-+]?[\d\.]+\s*\(([-+]\d+[\.,]\d+)%\)/);
                if (priceMatch) {
                    currentPrice = parseInt(priceMatch[1].replace(/\./g, ''), 10) || 0;
                    pricePercentage = parseFloat(priceMatch[2].replace(',', '.'));
                } else {
                    // Fallback jika hanya persentase yang terbaca
                    const pctMatch = textInfo.match(/\(([-+]\d+[\.,]\d+)%\)/);
                    if (pctMatch) {
                        pricePercentage = parseFloat(pctMatch[1].replace(',', '.'));
                    }
                }
                break; // Hentikan pencarian ke atas
            }
            
            wrapper = wrapper.parentElement;
        }

        // Mencari baris Total dengan fallback yang kuat
        let totalText = "";
        const totalRow = widget.querySelector('.ob-total');
        if (totalRow) {
            totalText = totalRow.innerText; 
        } else {
            const divs = widget.querySelectorAll('div');
            for (let d of divs) {
                if (d.innerText && d.innerText.includes("Total") && d.innerText.length < 50 && /\d/.test(d.innerText)) {
                    totalText = d.innerText;
                    break;
                }
            }
        }
            
        if (totalText.includes("Total")) {
            const parts = totalText.split("Total");
            const bidSideNumbers = parts[0].match(/[\d\.,]+/g);
            const askSideNumbers = parts[1].match(/[\d\.,]+/g);
            
            let bidLot = 0, bidFreq = 0;
            let askLot = 0, askFreq = 0;
            
            if (bidSideNumbers && bidSideNumbers.length >= 2) {
                bidLot = cleanNumber(bidSideNumbers[bidSideNumbers.length - 1]); 
                bidFreq = cleanNumber(bidSideNumbers[0]); // Angka pertama biasanya Freq
            }
            if (askSideNumbers && askSideNumbers.length >= 2) {
                askLot = cleanNumber(askSideNumbers[0]); 
                askFreq = cleanNumber(askSideNumbers[askSideNumbers.length - 1]); // Angka terakhir Freq
            }
            
            if ((bidLot > 0 || askLot > 0) && (bidFreq > 0 || askFreq > 0)) {
                    
                    // --- MENGIRIM DATA KE DATABASE LOKAL (Via Background Script) ---
                    try {
                        chrome.runtime.sendMessage({
                            action: "fetchAPI",
                            url: 'http://127.0.0.1:5000/record',
                            options: {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({
                                    stock_code: stockCode,
                                    total_bid_lot: bidLot,
                                    total_ask_lot: askLot
                                })
                            }
                        }, response => {});
                    } catch (e) {
                        // Jika muncul error "Extension context invalidated", hentikan interval lama
                        if (e.message && e.message.includes("Extension context invalidated")) {
                            console.log("Ekstensi telah di-reload. Mematikan script lama...");
                            if (typeof scalpingIntervalId !== 'undefined') clearInterval(scalpingIntervalId);
                            return; 
                        }
                    }
                    
                    // ========================================================
                    // ALGORITMA SCALPING LANJUTAN (MULTIPLE PARAMETERS)
                    // ========================================================
                    
                    // Parameter 1: Average Lot per Order (Deteksi Big Player)
                    const avgBidLot = bidLot / bidFreq;
                    const avgAskLot = askLot / askFreq;
                    
                    // Inisialisasi history untuk melacak perubahan (Delta)
                    if (!previousData[stockCode]) {
                        previousData[stockCode] = [];
                    }
                    
                    // Simpan data detik ini ke history array
                    previousData[stockCode].push({ bidLot, askLot, bidFreq, askFreq });
                    
                    // Batasi history maksimal 5 detik
                    if (previousData[stockCode].length > 5) {
                        previousData[stockCode].shift();
                    }

                    // Parameter 2: Delta Momentum (Perubahan Lot dalam 1-5 Detik Terakhir)
                    let isHAKA = false; // Hajar Kanan (Ask dimakan)
                    let isAkumulasi = false; // Bid ditebalkan
                    let isGuyur = false; // Hajar Kiri (Bid dimakan) atau Ask ditebalkan
                    
                    const history = previousData[stockCode];
                    if (history.length > 1) {
                        const prev1s = history[history.length - 2];
                        const oldest = history[0];
                        
                        // Hitung dinamis persentase perubahan (mencegah kedip karena fluktuasi kecil)
                        const hakaThreshold = Math.max(2000, askLot * 0.02); // Minimal 2000 lot atau 2% dari total ask
                        const akumulasiThreshold = Math.max(5000, bidLot * 0.03); // Minimal 5000 lot atau 3% dari total bid
                        const guyurThreshold = Math.max(4000, bidLot * 0.025); // Minimal 4000 lot atau 2.5% dari total bid
                        
                        // HAKA: Lot Ask berkurang signifikan (dimakan buyer)
                        if (prev1s.askLot > askLot && (prev1s.askLot - askLot) > hakaThreshold) {
                            isHAKA = true;
                        }
                        
                        // Akumulasi: Lot Bid bertambah dalam 5 detik terakhir (tembok support dibangun)
                        if (bidLot > oldest.bidLot && (bidLot - oldest.bidLot) > akumulasiThreshold) {
                            isAkumulasi = true;
                        }
                        
                        // Guyur/Distribusi: Lot Bid dimakan (berkurang) ATAU Lot Ask bertambah tajam (tembok resisten dibangun)
                        if ((prev1s.bidLot > bidLot && (prev1s.bidLot - bidLot) > guyurThreshold) || (askLot > oldest.askLot && (askLot - oldest.askLot) > akumulasiThreshold)) {
                            isGuyur = true;
                        }
                    }

                    // --- MENGAMBIL HARGA SUPPORT & RESISTANCE DARI BACKEND ---
                    let supportPrice = "N/A";
                    let resistancePrice = "N/A";
                    
                    if (!srCache[stockCode] && stockCode !== "UNKNOWN") {
                        srCache[stockCode] = { status: 'fetching', support: '...', resistance: '...' };
                        try {
                            chrome.runtime.sendMessage({
                                action: "fetchAPI",
                                url: `http://127.0.0.1:5000/api/sr/${stockCode}`,
                                options: { method: 'GET' }
                            }, response => {
                                if (chrome.runtime.lastError) {
                                    srCache[stockCode].status = 'error';
                                    srCache[stockCode].support = 'ERR1';
                                    srCache[stockCode].resistance = 'ERR1';
                                    setTimeout(() => { delete srCache[stockCode]; }, 5000);
                                    return;
                                }
                                if (response && response.success && response.data && response.data.status === 'success') {
                                    srCache[stockCode] = response.data;
                                } else {
                                    srCache[stockCode].status = 'error';
                                    srCache[stockCode].support = 'ERR2';
                                    srCache[stockCode].resistance = 'ERR2';
                                    setTimeout(() => { delete srCache[stockCode]; }, 5000);
                                }
                            });
                        } catch (e) {
                            if (e.message && e.message.includes("Extension context invalidated")) {
                                if (typeof scalpingIntervalId !== 'undefined') clearInterval(scalpingIntervalId);
                                return;
                            }
                        }
                    } else if (srCache[stockCode] && srCache[stockCode].status === 'success') {
                        supportPrice = srCache[stockCode].support;
                        resistancePrice = srCache[stockCode].resistance;
                    }
                    
                    // --- MENGAMBIL HASIL SCREENER (RADAR) DARI BACKEND ---
                    if (!scanCache[stockCode] && stockCode !== "UNKNOWN") {
                        scanCache[stockCode] = { status: 'fetching' };
                        try {
                            chrome.runtime.sendMessage({
                                action: "fetchAPI",
                                url: `http://127.0.0.1:5000/api/screener/latest/${stockCode}`,
                                options: { method: 'GET' }
                            }, response => {
                                if (response && response.success && response.data && response.data.status === 'success') {
                                    scanCache[stockCode] = response.data;
                                } else {
                                    scanCache[stockCode] = { status: 'not_found' };
                                    setTimeout(() => { delete scanCache[stockCode]; }, 30000); // Coba lagi dalam 30 detik
                                }
                            });
                        } catch (e) {
                            // Abaikan error ekstensi
                        }
                    }

                    let scanPrefix = "";
                    if (scanCache[stockCode] && scanCache[stockCode].status === 'success') {
                        const entry = scanCache[stockCode].entry;
                        const tp = scanCache[stockCode].tp;
                        scanPrefix = `🌟 RADAR [E:${entry} T:${tp}] | `;
                    }

                    const srText = ` | S:${supportPrice} R:${resistancePrice}`;

                    // ========================================================
                    // LOGIKA KEPUTUSAN ENTRY (ANTI FLICKER)
                    // ========================================================
                    
                    let newText = `${scanPrefix}👁️ PANTAU (Neutral)${srText}`;
                    let newClass = 'ajaib-scalping-badge ajaib-scalping-neutral';
                    let priority = 0; // Prioritas sinyal (makin tinggi makin dipertahankan)
                    
                    // 1. KONDISI MOMENTUM RUN! (Ada HAKA dan Harga Naik)
                    if (pricePercentage > 0 && isHAKA && !isGuyur) {
                        newText = `${scanPrefix}🚀 FAST BUY! (Ada HAKA)${srText}`;
                        newClass = 'ajaib-scalping-badge ajaib-scalping-buy';
                        priority = 4;
                    }
                    // 2. KONDISI AKUMULASI (Tembok Bid Tebal + Rata-rata Bid Lot Besar + Tembok Bid Bertambah)
                    else if (bidLot > (1.2 * askLot) && avgBidLot > avgAskLot && isAkumulasi) {
                        newText = `${scanPrefix}🔥 BUY KAWAL! (Akumulasi Aktif)${srText}`;
                        newClass = 'ajaib-scalping-badge ajaib-scalping-buy';
                        priority = 3;
                    }
                    // 3. KONDISI BUY ON WEAKNESS (Harga di area Support dan Bid dijaga)
                    else if (currentPrice > 0 && typeof supportPrice === 'number' && currentPrice <= (supportPrice * 1.02) && currentPrice >= (supportPrice * 0.98)) {
                        if (bidLot > askLot && !isGuyur) {
                            newText = `${scanPrefix}🎯 BUY ON SUPPORT (${supportPrice})${srText}`;
                            newClass = 'ajaib-scalping-badge ajaib-scalping-buy';
                            priority = 3;
                        } else {
                            newText = `${scanPrefix}⚠️ RAWAN JEBOL (Di Support tapi diguyur)${srText}`;
                            newClass = 'ajaib-scalping-badge ajaib-scalping-sell';
                            priority = 5;
                        }
                    }
                    // 4. KONDISI DISTRIBUSI / SELL (Tembok Ask Super Tebal ATAU Sedang Diguyur)
                    else if (askLot > (1.5 * bidLot) || isGuyur) {
                        newText = `${scanPrefix}⚠️ SELL NOW (Distribusi/Guyur)${srText}`;
                        newClass = 'ajaib-scalping-badge ajaib-scalping-sell';
                        priority = 5;
                    } 
                    
                    // Logika Anti-Flicker: Pertahankan sinyal setidaknya selama 4 detik kecuali ada sinyal darurat (SELL)
                    const nowTime = Date.now();
                    if (!signalState[stockCode]) {
                        signalState[stockCode] = { text: newText, class: newClass, time: nowTime, priority: priority };
                    }
                    
                    const lastState = signalState[stockCode];
                    const timePassed = nowTime - lastState.time;
                    
                    // Jika belum lewat 4 detik, dan sinyal baru lebih lemah prioritasnya, abaikan sinyal baru (tahan sinyal lama)
                    if (timePassed < 4000 && priority < lastState.priority && newText !== lastState.text) {
                        // Tahan sinyal lama
                    } else if (newText !== lastState.text) {
                        // Sinyal benar-benar berubah (sudah lewat 4 detik atau sinyal darurat muncul)
                        signalState[stockCode] = { text: newText, class: newClass, time: nowTime, priority: priority };
                    }
                    
                    // Render sinyal ke layar
                    badge.textContent = signalState[stockCode].text;
                    badge.className = signalState[stockCode].class;
                }
            }
    });
}

let scalpingIntervalId;

console.log("[Ajaib Scalping Ext] Memulai dengan tombol ON/OFF...");
scalpingIntervalId = setInterval(evaluateOrderbook, 1000);
