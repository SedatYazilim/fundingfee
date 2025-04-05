import telebot
from telebot import types
import requests
import matplotlib.pyplot as plt
import io
import pandas as pd
import google.generativeai as genai
import logging
import time
import json
import re
from matplotlib.ticker import MaxNLocator
import matplotlib.gridspec as gridspec

# Loglama yapılandırması
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# API anahtarları (doğrudan kodun içinde)
TELEGRAM_TOKEN = "8167782240:AAGUVpU9UKo3pIb6QUIthOlI1T4B1u1cVtw"
GEMINI_API_KEY = "AIzaSyCFdnKSgx-0MFs4neTu76OQdC91z3fLqkw"

# Gemini AI yapılandırması
genai.configure(api_key=GEMINI_API_KEY)

# Desteklenen borsalar
SUPPORTED_EXCHANGES = ["Binance", "Bybit", "OKX", "Huobi", "Gate.io", "Bitget"]

# Bot oluşturma
bot = telebot.TeleBot(TELEGRAM_TOKEN)

# Gemini modelleri - hata durumunda sırayla denenecek
GEMINI_MODELS = ['gemini-1.5-pro', 'gemini-1.5-flash', 'gemini-1.0-pro', 'gemini-pro']

# Timeout değerleri
REQUEST_TIMEOUT = 10  # saniye

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message,
        "Merhaba! Çoklu Borsa Funding Fee ve Long/Short Oranları botuna hoş geldiniz.\n\n"
        "Kullanmak için bir kripto para birimi sembolü gönderin (örneğin: BTC, ETH).\n"
        "Size farklı borsalardaki güncel funding fee oranlarını, long/short oranlarını ve grafiklerini göstereceğim.\n\n"
        "Desteklenen borsalar: " + ", ".join(SUPPORTED_EXCHANGES) + "\n\n"
        "'/analyze SYMBOL' komutuyla yapay zeka destekli analiz alabilirsiniz."
    )

@bot.message_handler(commands=['analyze'])
def analyze_command(message):
    command_args = message.text.split()
    if len(command_args) < 2:
        bot.reply_to(message, "Lütfen analiz etmek istediğiniz sembolü belirtin. Örnek: /analyze BTC")
        return
    
    symbol = command_args[1].upper()
    status_message = bot.send_message(message.chat.id, f"🔍 {symbol} için veri toplama başlatıldı...")
    get_ai_analysis(message, symbol, status_message=status_message)

@bot.message_handler(func=lambda message: True)
def get_funding_rates(message):
    symbol = message.text.upper().strip()
    
    # Komut değilse işlem yap
    if symbol.startswith('/'):
        return
    
    # Sembolde USD, USDT gibi ekler varsa temizle
    for suffix in ['USD', 'USDT', 'BUSD', 'USDC']:
        if symbol.endswith(suffix):
            symbol = symbol.replace(suffix, '')
    
    # Durum mesajını gönder ve mesaj nesnesini sakla
    status_message = bot.send_message(message.chat.id, f"🔍 {symbol} için veri toplama başlatıldı...")
    
    try:
        # Her aşamada durum mesajını güncelle
        bot.edit_message_text(f"⏳ {symbol} için Binance verileri alınıyor...", 
                              message.chat.id, status_message.message_id)
        binance_data = get_binance_funding(symbol)
        binance_ls_ratio = get_binance_long_short_ratio(symbol)
        
        bot.edit_message_text(f"⏳ {symbol} için Bybit verileri alınıyor...", 
                              message.chat.id, status_message.message_id)
        bybit_data = get_bybit_funding(symbol)
        bybit_ls_ratio = get_bybit_long_short_ratio(symbol)
        
        bot.edit_message_text(f"⏳ {symbol} için OKX verileri alınıyor...", 
                              message.chat.id, status_message.message_id)
        okx_data = get_okx_funding(symbol)
        okx_ls_ratio = get_okx_long_short_ratio(symbol)
        
        bot.edit_message_text(f"⏳ {symbol} için Huobi verileri alınıyor...", 
                              message.chat.id, status_message.message_id)
        huobi_data = get_huobi_funding(symbol)
        
        bot.edit_message_text(f"⏳ {symbol} için Gate.io verileri alınıyor...", 
                              message.chat.id, status_message.message_id)
        gateio_data = get_gateio_funding(symbol)
        
        bot.edit_message_text(f"⏳ {symbol} için Bitget verileri alınıyor...", 
                              message.chat.id, status_message.message_id)
        bitget_data = get_bitget_funding(symbol)
        
        bot.edit_message_text(f"⏳ {symbol} için veriler toplanıyor ve grafikler hazırlanıyor...", 
                              message.chat.id, status_message.message_id)
        
        funding_data = {}
        ls_ratio_data = {}
        
        if binance_data:
            funding_data.update(binance_data)
        if binance_ls_ratio:
            ls_ratio_data.update(binance_ls_ratio)
            
        if bybit_data:
            funding_data.update(bybit_data)
        if bybit_ls_ratio:
            ls_ratio_data.update(bybit_ls_ratio)
            
        if okx_data:
            funding_data.update(okx_data)
        if okx_ls_ratio:
            ls_ratio_data.update(okx_ls_ratio)
            
        if huobi_data:
            funding_data.update(huobi_data)
            
        if gateio_data:
            funding_data.update(gateio_data)
            
        if bitget_data:
            funding_data.update(bitget_data)
        
        if not funding_data and not ls_ratio_data:
            bot.edit_message_text(f"❌ Üzgünüm, {symbol} için hiçbir borsada veri bulunamadı.", 
                                 message.chat.id, status_message.message_id)
            return
        
        # Funding Rate Metin Yanıtı
        reply_text = f"📊 *{symbol} için Funding Fee Oranları:*\n\n"
        
        if funding_data:
            for exchange, rate in sorted(funding_data.items(), key=lambda x: x[0]):
                emoji = "🔴" if rate < 0 else "🟢"
                reply_text += f"{emoji} *{exchange}:* `{rate:.6f}%`\n"
        else:
            reply_text += "Funding fee verisi bulunamadı.\n"
        
        # Long/Short Ratio Metin Yanıtı
        reply_text += f"\n📈 *{symbol} için Long/Short Oranları:*\n\n"
        
        if ls_ratio_data:
            for exchange, ratio in sorted(ls_ratio_data.items(), key=lambda x: x[0]):
                emoji = "🔴" if ratio < 1 else "🟢"
                long_percentage = (ratio / (ratio + 1)) * 100
                short_percentage = 100 - long_percentage
                reply_text += f"{emoji} *{exchange}:* `{ratio:.2f}` (Long: %{long_percentage:.1f}, Short: %{short_percentage:.1f})\n"
        else:
            reply_text += "Long/Short oranı verisi bulunamadı.\n"
        
        # Grafikler için veri hazırlama
        has_funding = len(funding_data) > 0
        has_ls_ratio = len(ls_ratio_data) > 0
        
        # Grafiği oluştur
        if has_funding or has_ls_ratio:
            plt.figure(figsize=(12, 10))
            plt.clf()  # Mevcut figürü temizle
            
            # Kaç grafik çizileceğini belirle
            num_plots = sum([has_funding, has_ls_ratio])
            gs = gridspec.GridSpec(num_plots, 1, height_ratios=[1] * num_plots)
            
            current_plot = 0
            
            # Funding Rate Grafiği
            if has_funding:
                ax1 = plt.subplot(gs[current_plot])
                
                # Veri hazırlama
                exchanges = list(funding_data.keys())
                rates = list(funding_data.values())
                
                # Borsa adları için kısaltmalar
                shortened_exchanges = []
                for ex in exchanges:
                    if "-" in ex:
                        parts = ex.split("-")
                        shortened_exchanges.append(parts[0])
                    else:
                        shortened_exchanges.append(ex)
                
                bars = ax1.bar(range(len(rates)), rates, color=['red' if r < 0 else 'green' for r in rates])
                ax1.set_title(f"{symbol} Funding Fee Rates", fontsize=14)
                ax1.set_xlabel("Exchange", fontsize=12)
                ax1.set_ylabel("Funding Rate (%)", fontsize=12)
                ax1.set_xticks(range(len(shortened_exchanges)))
                ax1.set_xticklabels(shortened_exchanges, rotation=45, ha='right')
                ax1.grid(axis='y', linestyle='--', alpha=0.7)
                
                # Değerleri çubukların üzerine yaz
                for bar, rate in zip(bars, rates):
                    height = bar.get_height()
                    if rate < 0:
                        ax1.text(bar.get_x() + bar.get_width()/2., -0.001, f'{rate:.4f}%',
                                ha='center', va='top', rotation=90, color='white', fontsize=9)
                    else:
                        ax1.text(bar.get_x() + bar.get_width()/2., 0.001, f'{rate:.4f}%',
                                ha='center', va='bottom', rotation=90, color='white', fontsize=9)
                
                # Eksen limitlerini ayarla
                max_rate = max(rates) if rates else 0
                min_rate = min(rates) if rates else 0
                padding = max(0.0005, abs(max_rate - min_rate) * 0.1)
                ax1.set_ylim(min_rate - padding if min_rate < 0 else -padding, max_rate + padding)
                
                current_plot += 1
            
            # Long/Short Ratio Grafiği
            if has_ls_ratio:
                ax2 = plt.subplot(gs[current_plot])
                
                # Veri hazırlama
                ls_exchanges = list(ls_ratio_data.keys())
                ls_ratios = list(ls_ratio_data.values())
                
                # Borsa adları için kısaltmalar
                ls_shortened_exchanges = []
                for ex in ls_exchanges:
                    if "-" in ex:
                        parts = ex.split("-")
                        ls_shortened_exchanges.append(parts[0])
                    else:
                        ls_shortened_exchanges.append(ex)
                
                # Long ve Short yüzdeleri
                long_percentages = [(ratio / (ratio + 1)) * 100 for ratio in ls_ratios]
                short_percentages = [100 - p for p in long_percentages]
                
                # Çift çubuk grafik
                width = 0.35
                x = range(len(ls_exchanges))
                ax2.bar([i - width/2 for i in x], long_percentages, width, label='Long %', color='green', alpha=0.7)
                ax2.bar([i + width/2 for i in x], short_percentages, width, label='Short %', color='red', alpha=0.7)
                
                # Grafik özellikleri
                ax2.set_title(f"{symbol} Long/Short Ratio", fontsize=14)
                ax2.set_xlabel("Exchange", fontsize=12)
                ax2.set_ylabel("Percentage (%)", fontsize=12)
                ax2.set_xticks(range(len(ls_shortened_exchanges)))
                ax2.set_xticklabels(ls_shortened_exchanges, rotation=45, ha='right')
                ax2.grid(axis='y', linestyle='--', alpha=0.7)
                ax2.legend()
                
                # Oranları çubukların üzerine yaz
                for i, (l_pct, s_pct, ratio) in enumerate(zip(long_percentages, short_percentages, ls_ratios)):
                    ax2.text(i - width/2, l_pct + 1, f"{l_pct:.1f}%", ha='center', va='bottom', fontsize=9)
                    ax2.text(i + width/2, s_pct + 1, f"{s_pct:.1f}%", ha='center', va='bottom', fontsize=9)
                    ax2.text(i, 50, f"Ratio: {ratio:.2f}", ha='center', va='center', fontsize=10, 
                            bbox=dict(facecolor='white', alpha=0.7, boxstyle='round,pad=0.3'))
                
                # Y eksenini 0-100 arası ayarla
                ax2.set_ylim(0, 100)
            
            plt.tight_layout()
            
            # Grafiği byte array'e dönüştürme
            buf = io.BytesIO()
            plt.savefig(buf, format='png', dpi=100)
            buf.seek(0)
            
            # Durum mesajını sil
            bot.delete_message(message.chat.id, status_message.message_id)
            
            try:
                # Mesajı parçalara böl (Telegram sınırı 4096 karakter)
                if len(reply_text) > 4000:
                    chunks = split_message(reply_text, 4000)
                    for chunk in chunks:
                        bot.send_message(message.chat.id, chunk, parse_mode="Markdown")
                else:
                    # Markdown formatında metin gönder
                    bot.send_message(message.chat.id, reply_text, parse_mode="Markdown")
                
                # Grafiği gönderme
                bot.send_photo(message.chat.id, photo=buf, caption=f"*{symbol} Funding Fee ve Long/Short Grafiği*", parse_mode="Markdown")
            except Exception as e:
                logger.error(f"Error sending messages: {str(e)}", exc_info=True)
                # Alternatif olarak normal metin ve grafik gönder
                plain_text = reply_text.replace('*', '').replace('`', '')
                
                # Düz metni parçalar halinde gönder
                if len(plain_text) > 4000:
                    chunks = split_message(plain_text, 4000)
                    for chunk in chunks:
                        bot.send_message(message.chat.id, chunk)
                else:
                    bot.send_message(message.chat.id, plain_text)
                    
                buf.seek(0)
                bot.send_photo(message.chat.id, photo=buf, caption=f"{symbol} Funding Fee ve Long/Short Grafiği")
            
            # Analiz butonu ekleme
            markup = types.InlineKeyboardMarkup()
            analyze_button = types.InlineKeyboardButton("AI Analizi İste", callback_data=f"analyze_{symbol}")
            markup.add(analyze_button)
            bot.send_message(message.chat.id, "Yapay zeka analizi için butona tıklayabilirsiniz:", reply_markup=markup)
        else:
            bot.edit_message_text(f"❌ Üzgünüm, {symbol} için grafiklendirilecek veri bulunamadı.", 
                                message.chat.id, status_message.message_id)
        
    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=True)
        try:
            bot.edit_message_text(f"❌ Bir hata oluştu: {str(e)}", message.chat.id, status_message.message_id)
        except:
            bot.send_message(message.chat.id, f"❌ Bir hata oluştu: {str(e)}")

def get_binance_funding(symbol):
    """Binance'den funding rate verilerini çeker"""
    try:
        url = "https://fapi.binance.com/fapi/v1/premiumIndex"
        response = requests.get(url, timeout=REQUEST_TIMEOUT)
        
        if response.status_code != 200:
            return {}
            
        data = response.json()
        
        # Sembol için filtreleme
        funding_data = {}
        for item in data:
            if symbol in item['symbol']:
                contract = item['symbol']
                rate = float(item['lastFundingRate']) * 100  # Yüzde olarak
                funding_data[f"Binance-{contract}"] = rate
                
        return funding_data
    except Exception as e:
        logger.warning(f"Binance API error: {str(e)}")
        return {}

def get_binance_long_short_ratio(symbol):
    """Binance'den long/short oranını çeker"""
    try:
        url = f"https://fapi.binance.com/futures/data/globalLongShortAccountRatio?symbol={symbol}USDT&period=5m"
        response = requests.get(url, timeout=REQUEST_TIMEOUT)
        
        if response.status_code != 200:
            # USD çiftini dene
            url = f"https://fapi.binance.com/futures/data/globalLongShortAccountRatio?symbol={symbol}USD&period=5m"
            response = requests.get(url, timeout=REQUEST_TIMEOUT)
            
            if response.status_code != 200:
                return {}
        
        data = response.json()
        
        if not data or len(data) == 0:
            return {}
        
        # En son veriyi al
        latest = data[0]
        ratio = float(latest['longShortRatio'])  # Long/Short oranı
        
        ls_data = {f"Binance-{symbol}": ratio}
        return ls_data
    except Exception as e:
        logger.warning(f"Binance L/S API error: {str(e)}")
        return {}

def get_bybit_funding(symbol):
    """Bybit'ten funding rate verilerini çeker"""
    try:
        # Önce USDT çiftini dene
        url = f"https://api.bybit.com/v5/market/funding/history?category=linear&symbol={symbol}USDT"
        response = requests.get(url, timeout=REQUEST_TIMEOUT)
        
        if response.status_code != 200:
            return {}
            
        data = response.json()
        
        funding_data = {}
        if data.get('result') and data['result'].get('list'):
            for item in data['result']['list']:
                contract = item['symbol']
                if 'fundingRate' in item:
                    rate = float(item['fundingRate']) * 100
                    funding_data[f"Bybit-{contract}"] = rate
        
        # USD çiftini de dene
        url = f"https://api.bybit.com/v5/market/funding/history?category=linear&symbol={symbol}USD"
        response = requests.get(url, timeout=REQUEST_TIMEOUT)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('result') and data['result'].get('list'):
                for item in data['result']['list']:
                    contract = item['symbol']
                    if 'fundingRate' in item:
                        rate = float(item['fundingRate']) * 100
                        funding_data[f"Bybit-{contract}"] = rate
                
        return funding_data
    except Exception as e:
        logger.warning(f"Bybit API error: {str(e)}")
        return {}

def get_bybit_long_short_ratio(symbol):
    """Bybit'ten long/short oranını çeker"""
    try:
        # USDT çifti
        url = f"https://api.bybit.com/v5/market/account-ratio?category=linear&symbol={symbol}USDT&period=5min"
        response = requests.get(url, timeout=REQUEST_TIMEOUT)
        
        ls_data = {}
        
        if response.status_code == 200:
            data = response.json()
            if data.get('result') and data['result'].get('list') and len(data['result']['list']) > 0:
                latest = data['result']['list'][0]
                if 'longRatio' in latest and 'shortRatio' in latest:
                    long_ratio = float(latest['longRatio'])
                    short_ratio = float(latest['shortRatio'])
                    if short_ratio > 0:  # Sıfıra bölünmeyi önle
                        ratio = long_ratio / short_ratio
                        ls_data[f"Bybit-{symbol}USDT"] = ratio
        
        # USD çifti
        url = f"https://api.bybit.com/v5/market/account-ratio?category=linear&symbol={symbol}USD&period=5min"
        response = requests.get(url, timeout=REQUEST_TIMEOUT)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('result') and data['result'].get('list') and len(data['result']['list']) > 0:
                latest = data['result']['list'][0]
                if 'longRatio' in latest and 'shortRatio' in latest:
                    long_ratio = float(latest['longRatio'])
                    short_ratio = float(latest['shortRatio'])
                    if short_ratio > 0:  # Sıfıra bölünmeyi önle
                        ratio = long_ratio / short_ratio
                        ls_data[f"Bybit-{symbol}USD"] = ratio
                
        return ls_data
    except Exception as e:
        logger.warning(f"Bybit L/S API error: {str(e)}")
        return {}

def get_okx_funding(symbol):
    """OKX'ten funding rate verilerini çeker"""
    try:
        # USDT ve USD çiftlerini dene
        funding_data = {}
        
        for quote in ['USDT', 'USD']:
            url = f"https://www.okx.com/api/v5/public/funding-rate?instId={symbol}-{quote}-SWAP"
            response = requests.get(url, timeout=REQUEST_TIMEOUT)
            
            if response.status_code != 200:
                continue
                
            data = response.json()
            
            if data.get('data'):
                for item in data['data']:
                    contract = item['instId']
                    rate = float(item['fundingRate']) * 100
                    funding_data[f"OKX-{contract}"] = rate
        
        return funding_data
    except Exception as e:
        logger.warning(f"OKX API error: {str(e)}")
        return {}

def get_okx_long_short_ratio(symbol):
    """OKX'ten long/short oranını çeker"""
    try:
        ls_data = {}
        
        for quote in ['USDT', 'USD']:
            url = f"https://www.okx.com/api/v5/rubik/stat/contracts/long-short-account-ratio?ccy={symbol}&period=5m"
            response = requests.get(url, timeout=REQUEST_TIMEOUT)
            
            if response.status_code != 200:
                continue
                
            data = response.json()
            
            if data.get('data') and len(data['data']) > 0:
                latest = data['data'][0]
                if 'longShortRatio' in latest:
                    ratio = float(latest['longShortRatio'])
                    ls_data[f"OKX-{symbol}-{quote}"] = ratio
        
        return ls_data
    except Exception as e:
        logger.warning(f"OKX L/S API error: {str(e)}")
        return {}

def get_huobi_funding(symbol):
    """Huobi/HTEX'ten funding rate verilerini çeker"""
    try:
        funding_data = {}
        
        # USDT çifti
        url = f"https://api.hbdm.com/linear-swap-api/v1/swap_funding_rate?contract_code={symbol}-USDT"
        response = requests.get(url, timeout=REQUEST_TIMEOUT)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('data') and isinstance(data['data'], list) and len(data['data']) > 0:
                for item in data['data']:
                    if isinstance(item, dict):
                        contract = item.get('contract_code')
                        if contract and 'funding_rate' in item:
                            rate = float(item['funding_rate']) * 100
                            funding_data[f"Huobi-{contract}"] = rate
        
        # USD çifti
        url = f"https://api.hbdm.com/linear-swap-api/v1/swap_funding_rate?contract_code={symbol}-USD"
        response = requests.get(url, timeout=REQUEST_TIMEOUT)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('data') and isinstance(data['data'], list) and len(data['data']) > 0:
                for item in data['data']:
                    if isinstance(item, dict):
                        contract = item.get('contract_code')
                        if contract and 'funding_rate' in item:
                            rate = float(item['funding_rate']) * 100
                            funding_data[f"Huobi-{contract}"] = rate
                
        return funding_data
    except Exception as e:
        logger.warning(f"Huobi API error: {str(e)}")
        return {}

def get_gateio_funding(symbol):
    """Gate.io'dan funding rate verilerini çeker"""
    try:
        funding_data = {}
        
        # USDT çifti
        url = f"https://api.gateio.ws/api/v4/futures/usdt/contracts/{symbol}_USDT"
        response = requests.get(url, timeout=REQUEST_TIMEOUT)
        
        if response.status_code == 200:
            data = response.json()
            if data and isinstance(data, dict) and 'funding_rate' in data:
                contract = data.get('name', f"{symbol}_USDT")
                rate = float(data['funding_rate']) * 100
                funding_data[f"Gate.io-{contract}"] = rate
                
        return funding_data
    except Exception as e:
        logger.warning(f"Gate.io API error: {str(e)}")
        return {}

def get_bitget_funding(symbol):
    """Bitget'ten funding rate verilerini çeker"""
    try:
        funding_data = {}
        
        # USDT çifti
        url = f"https://api.bitget.com/api/mix/v1/market/current-fundRate?symbol={symbol}USDT_UMCBL"
        response = requests.get(url, timeout=REQUEST_TIMEOUT)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('data'):
                contract = f"{symbol}USDT"
                rate = float(data['data'].get('fundingRate', 0)) * 100
                funding_data[f"Bitget-{contract}"] = rate
                
        # USD çifti
        url = f"https://api.bitget.com/api/mix/v1/market/current-fundRate?symbol={symbol}USD_UMCBL"
        response = requests.get(url, timeout=REQUEST_TIMEOUT)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('data'):
                contract = f"{symbol}USD"
                rate = float(data['data'].get('fundingRate', 0)) * 100
                funding_data[f"Bitget-{contract}"] = rate
                
        return funding_data
    except Exception as e:
        logger.warning(f"Bitget API error: {str(e)}")
        return {}

@bot.callback_query_handler(func=lambda call: True)
def button_callback(call):
    data = call.data
    if data.startswith("analyze_"):
        symbol = data.split("_")[1]
        status_message = bot.send_message(call.message.chat.id, f"🔍 {symbol} için AI analizi hazırlanıyor...")
        get_ai_analysis(call.message, symbol, is_callback=True, status_message=status_message)

def format_ai_response(text):
    """AI yanıtındaki markdown formatlamalarını Telegram formatına dönüştürür"""
    # ** ile kalın yapma
    text = re.sub(r'\*\*(.*?)\*\*', r'*\1*', text)
    
    # Başlıkları kalın yapma
    text = re.sub(r'^# (.*?)$', r'*\1*', text, flags=re.MULTILINE)
    text = re.sub(r'^## (.*?)$', r'*\1*', text, flags=re.MULTILINE)
    text = re.sub(r'^### (.*?)$', r'*\1*', text, flags=re.MULTILINE)
    
    return text

def split_message(text, limit=4000):
    """Uzun mesajları belirtilen limite göre böler"""
    if len(text) <= limit:
        return [text]
    
    # Paragraflardan bölmeye çalış
    parts = []
    current_part = ""
    
    paragraphs = text.split('\n\n')
    
    for paragraph in paragraphs:
        # Eğer paragraf tek başına limiti aşıyorsa, onu cümlelere böl
        if len(paragraph) > limit:
            sentences = paragraph.split('. ')
            for sentence in sentences:
                if len(current_part + sentence + '. ') > limit:
                    parts.append(current_part)
                    current_part = sentence + '. '
                else:
                    current_part += sentence + '. '
        # Normal durumda paragrafları ekle
        elif len(current_part + paragraph + '\n\n') > limit:
            parts.append(current_part)
            current_part = paragraph + '\n\n'
        else:
            current_part += paragraph + '\n\n'
    
    # Son parçayı ekle
    if current_part:
        parts.append(current_part)
    
    return parts

def get_ai_analysis(message, symbol, is_callback=False, status_message=None):
    try:
        # Durum mesajını güncelle
        if status_message:
            bot.edit_message_text(f"⏳ {symbol} için veriler toplanıyor...", 
                                message.chat.id, status_message.message_id)
        
        # Tüm borsalardan veri topla
        funding_data = {}
        ls_ratio_data = {}
        
        binance_data = get_binance_funding(symbol)
        binance_ls_ratio = get_binance_long_short_ratio(symbol)
        
        bybit_data = get_bybit_funding(symbol)
        bybit_ls_ratio = get_bybit_long_short_ratio(symbol)
        
        okx_data = get_okx_funding(symbol)
        okx_ls_ratio = get_okx_long_short_ratio(symbol)
        
        huobi_data = get_huobi_funding(symbol)
        gateio_data = get_gateio_funding(symbol)
        bitget_data = get_bitget_funding(symbol)
        
        funding_data.update(binance_data)
        funding_data.update(bybit_data)
        funding_data.update(okx_data)
        funding_data.update(huobi_data)
        funding_data.update(gateio_data)
        funding_data.update(bitget_data)
        
        ls_ratio_data.update(binance_ls_ratio)
        ls_ratio_data.update(bybit_ls_ratio)
        ls_ratio_data.update(okx_ls_ratio)
        
        if not funding_data and not ls_ratio_data:
            if status_message:
                bot.edit_message_text(f"❌ Üzgünüm, {symbol} için hiçbir borsada veri bulunamadı.", 
                                     message.chat.id, status_message.message_id)
            else:
                bot.send_message(message.chat.id, f"❌ Üzgünüm, {symbol} için hiçbir borsada veri bulunamadı.")
            return
        
        if status_message:
            bot.edit_message_text(f"⏳ {symbol} için AI analizi hazırlanıyor...", 
                                message.chat.id, status_message.message_id)
        
        # Güncel funding fee özeti hazırlama
        funding_summary = ""
        if funding_data:
            funding_summary = "\n\n*Güncel Funding Fee Oranları:*\n"
            for exchange, rate in sorted(funding_data.items(), key=lambda x: x[0]):
                emoji = "🔴" if rate < 0 else "🟢"
                funding_summary += f"{emoji} *{exchange}:* `{rate:.6f}%`\n"
        
        # Güncel Long/Short oranları özeti
        ls_summary = ""
        if ls_ratio_data:
            ls_summary = "\n\n*Güncel Long/Short Oranları:*\n"
            for exchange, ratio in sorted(ls_ratio_data.items(), key=lambda x: x[0]):
                emoji = "🔴" if ratio < 1 else "🟢"
                long_percentage = (ratio / (ratio + 1)) * 100
                short_percentage = 100 - long_percentage
                ls_summary += f"{emoji} *{exchange}:* `{ratio:.2f}` (Long: %{long_percentage:.1f}, Short: %{short_percentage:.1f})\n"
        
        # Grafiği hazırla
        has_funding = len(funding_data) > 0
        has_ls_ratio = len(ls_ratio_data) > 0
        
        if has_funding or has_ls_ratio:
            plt.figure(figsize=(12, 10))
            plt.clf()  # Mevcut figürü temizle
            
            # Kaç grafik çizileceğini belirle
            num_plots = sum([has_funding, has_ls_ratio])
            gs = gridspec.GridSpec(num_plots, 1, height_ratios=[1] * num_plots)
            
            current_plot = 0
            
            # Funding Rate Grafiği
            if has_funding:
                ax1 = plt.subplot(gs[current_plot])
                
                # Veri hazırlama
                exchanges = list(funding_data.keys())
                rates = list(funding_data.values())
                
                # Borsa adları için kısaltmalar
                shortened_exchanges = []
                for ex in exchanges:
                    if "-" in ex:
                        parts = ex.split("-")
                        shortened_exchanges.append(parts[0])
                    else:
                        shortened_exchanges.append(ex)
                
                bars = ax1.bar(range(len(rates)), rates, color=['red' if r < 0 else 'green' for r in rates])
                ax1.set_title(f"{symbol} Funding Fee Rates", fontsize=14)
                ax1.set_xlabel("Exchange", fontsize=12)
                ax1.set_ylabel("Funding Rate (%)", fontsize=12)
                ax1.set_xticks(range(len(shortened_exchanges)))
                ax1.set_xticklabels(shortened_exchanges, rotation=45, ha='right')
                ax1.grid(axis='y', linestyle='--', alpha=0.7)
                
                # Değerleri çubukların üzerine yaz
                for bar, rate in zip(bars, rates):
                    height = bar.get_height()
                    if rate < 0:
                        ax1.text(bar.get_x() + bar.get_width()/2., -0.001, f'{rate:.4f}%',
                                ha='center', va='top', rotation=90, color='white', fontsize=9)
                    else:
                        ax1.text(bar.get_x() + bar.get_width()/2., 0.001, f'{rate:.4f}%',
                                ha='center', va='bottom', rotation=90, color='white', fontsize=9)
                
                # Eksen limitlerini ayarla
                max_rate = max(rates) if rates else 0
                min_rate = min(rates) if rates else 0
                padding = max(0.0005, abs(max_rate - min_rate) * 0.1)
                ax1.set_ylim(min_rate - padding if min_rate < 0 else -padding, max_rate + padding)
                
                current_plot += 1
            
            # Long/Short Ratio Grafiği
            if has_ls_ratio:
                ax2 = plt.subplot(gs[current_plot])
                
                # Veri hazırlama
                ls_exchanges = list(ls_ratio_data.keys())
                ls_ratios = list(ls_ratio_data.values())
                
                # Borsa adları için kısaltmalar
                ls_shortened_exchanges = []
                for ex in ls_exchanges:
                    if "-" in ex:
                        parts = ex.split("-")
                        ls_shortened_exchanges.append(parts[0])
                    else:
                        ls_shortened_exchanges.append(ex)
                
                # Long ve Short yüzdeleri
                long_percentages = [(ratio / (ratio + 1)) * 100 for ratio in ls_ratios]
                short_percentages = [100 - p for p in long_percentages]
                
                # Çift çubuk grafik
                width = 0.35
                x = range(len(ls_exchanges))
                ax2.bar([i - width/2 for i in x], long_percentages, width, label='Long %', color='green', alpha=0.7)
                ax2.bar([i + width/2 for i in x], short_percentages, width, label='Short %', color='red', alpha=0.7)
                
                # Grafik özellikleri
                ax2.set_title(f"{symbol} Long/Short Ratio", fontsize=14)
                ax2.set_xlabel("Exchange", fontsize=12)
                ax2.set_ylabel("Percentage (%)", fontsize=12)
                ax2.set_xticks(range(len(ls_shortened_exchanges)))
                ax2.set_xticklabels(ls_shortened_exchanges, rotation=45, ha='right')
                ax2.grid(axis='y', linestyle='--', alpha=0.7)
                ax2.legend()
                
                # Oranları çubukların üzerine yaz
                for i, (l_pct, s_pct, ratio) in enumerate(zip(long_percentages, short_percentages, ls_ratios)):
                    ax2.text(i - width/2, l_pct + 1, f"{l_pct:.1f}%", ha='center', va='bottom', fontsize=9)
                    ax2.text(i + width/2, s_pct + 1, f"{s_pct:.1f}%", ha='center', va='bottom', fontsize=9)
                    ax2.text(i, 50, f"Ratio: {ratio:.2f}", ha='center', va='center', fontsize=10, 
                            bbox=dict(facecolor='white', alpha=0.7, boxstyle='round,pad=0.3'))
                
                # Y eksenini 0-100 arası ayarla
                ax2.set_ylim(0, 100)
            
            plt.tight_layout()
            
            # Grafiği byte array'e dönüştürme
            buf = io.BytesIO()
            plt.savefig(buf, format='png', dpi=100)
            buf.seek(0)
        
        # AI prompt hazırlama
        prompt = f"""
        {symbol} kripto para birimi için farklı borsalardaki veriler aşağıdaki gibidir:
        
        """
        
        if funding_data:
            prompt += "Funding Fee Oranları:\n"
            for exchange, rate in sorted(funding_data.items(), key=lambda x: x[0]):
                prompt += f"{exchange}: {rate:.6f}%\n"
            prompt += "\n"
        
        if ls_ratio_data:
            prompt += "Long/Short Oranları:\n"
            for exchange, ratio in sorted(ls_ratio_data.items(), key=lambda x: x[0]):
                long_percentage = (ratio / (ratio + 1)) * 100
                short_percentage = 100 - long_percentage
                prompt += f"{exchange}: {ratio:.2f} (Long: %{long_percentage:.1f}, Short: %{short_percentage:.1f})\n"
            prompt += "\n"
        
        prompt += """
        Bu verileri analiz et ve şunları açıkla:
        1. Funding fee oranları ve long/short oranları ne anlama geliyor?
        2. Borsalar arasındaki farklar ne ifade ediyor?
        3. Bu verilere dayanarak piyasa eğilimi nedir?
        4. Arbitraj fırsatları var mı?
        5. Yatırımcılar için öneriler neler olabilir?
        
        Açıklamaları basit ve anlaşılır şekilde yap. Türkçe yanıt ver.
        Önemli noktaları vurgulamak için ** işaretlerini kullanarak kalın yazı yapabilirsin.
        """
        
        # Farklı Gemini modelleri deneyerek AI'dan yanıt alma
        analysis = None
        for model_name in GEMINI_MODELS:
            try:
                if status_message:
                    bot.edit_message_text(f"⏳ {symbol} için {model_name} modeli ile analiz yapılıyor...", 
                                        message.chat.id, status_message.message_id)
                
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(prompt)
                analysis = response.text
                logger.info(f"Başarılı AI yanıtı: {model_name} modeli kullanıldı")
                break
            except Exception as model_error:
                logger.warning(f"{model_name} modeli hatası: {str(model_error)}")
                continue
        
        if not analysis:
            if status_message:
                bot.edit_message_text("❌ Üzgünüm, AI analizi oluşturulamadı. Tüm modeller denendi ancak başarısız oldu.", 
                                     message.chat.id, status_message.message_id)
            else:
                bot.send_message(message.chat.id, "❌ Üzgünüm, AI analizi oluşturulamadı. Tüm modeller denendi ancak başarısız oldu.")
            return
        
        # Yanıtı Telegram markdown formatına dönüştür
        formatted_analysis = format_ai_response(analysis)
        
        # Durum mesajını sil
        if status_message:
            bot.delete_message(message.chat.id, status_message.message_id)
        
        try:
            # Önce grafiği gönder (eğer varsa)
            if has_funding or has_ls_ratio:
                bot.send_photo(message.chat.id, photo=buf, caption=f"*{symbol} Funding Fee ve Long/Short Grafiği*", parse_mode="Markdown")
            
            # Başlık mesajı
            header = f"🤖 *{symbol} Analizi:*\n\n"
            bot.send_message(message.chat.id, header, parse_mode="Markdown")
            
            # Analiz metnini böl ve gönder
            analysis_parts = split_message(formatted_analysis, 3800)  # Güvenli bir sınır
            for part in analysis_parts:
                bot.send_message(message.chat.id, part, parse_mode="Markdown")
            
            # Funding özeti gönder
            if funding_summary:
                bot.send_message(message.chat.id, funding_summary, parse_mode="Markdown")
            
            # Long/Short özeti gönder
            if ls_summary:
                bot.send_message(message.chat.id, ls_summary, parse_mode="Markdown")
            
        except Exception as e:
            logger.error(f"Error sending analysis: {str(e)}", exc_info=True)
            # Alternatif olarak formatsız gönder
            if has_funding or has_ls_ratio:
                bot.send_photo(message.chat.id, photo=buf, caption=f"{symbol} Funding Fee ve Long/Short Grafiği")
            
            # Analiz metnini düz metin olarak böl ve gönder
            plain_analysis = analysis.replace('**', '').replace('*', '')
            analysis_parts = split_message(plain_analysis, 3800)
            
            bot.send_message(message.chat.id, f"🤖 {symbol} Analizi:")
            for part in analysis_parts:
                bot.send_message(message.chat.id, part)
            
            # Funding özeti düz metin olarak gönder
            if funding_summary:
                plain_funding = funding_summary.replace('*', '').replace('`', '')
                bot.send_message(message.chat.id, plain_funding)
            
            # Long/Short özeti düz metin olarak gönder
            if ls_summary:
                plain_ls = ls_summary.replace('*', '').replace('`', '')
                bot.send_message(message.chat.id, plain_ls)
            
    except Exception as e:
        logger.error(f"AI analysis error: {str(e)}", exc_info=True)
        if status_message:
            bot.edit_message_text(f"❌ Analiz sırasında bir hata oluştu: {str(e)}", 
                                 message.chat.id, status_message.message_id)
        else:
            bot.send_message(message.chat.id, f"❌ Analiz sırasında bir hata oluştu: {str(e)}")

# Botu başlat
if __name__ == "__main__":
    logger.info("Bot başlatılıyor...")
    bot.polling(none_stop=True)
