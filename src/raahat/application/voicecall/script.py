"""What the voice agent says, in each supported language.

Prompts are fixed sentences so each is synthesised once and cached. Display
text uses digits; the spoken form replaces "112" with words because the
speech engine expects numbers written out.

Translations need review by native speakers before wide use.
"""
from __future__ import annotations

from dataclasses import dataclass

DEFAULT_LANGUAGE = "hi"

LANGUAGE_NAMES = {
    "hi": "हिन्दी", "en": "English", "ml": "മലയാളം", "mr": "मराठी", "ta": "தமிழ்",
    "te": "తెలుగు", "kn": "ಕನ್ನಡ", "bn": "বাংলা", "gu": "ગુજરાતી", "pa": "ਪੰਜਾਬੀ",
}

STEPS = ("situation", "location", "people", "safety", "callback", "name")

_T: dict[str, dict[str, str]] = {
    "hi": {
        "greeting": "नमस्ते, यह आपातकालीन सहायता है। आप किसी भी भाषा में बोल सकते हैं। बताइए, क्या हुआ है?",
        "situation": "कृपया बताइए, क्या हुआ है?",
        "location": "ठीक है। आप ठीक कहाँ हैं? पास का कोई निशान, सड़क या इलाके का नाम बताइए।",
        "people": "ठीक है। आपके साथ कितने लोग हैं?",
        "safety": "ठीक है। क्या कोई घायल है, फँसा हुआ है, या अभी खतरे में है?",
        "callback": "ठीक है। बचाव दल आपको किस फ़ोन नंबर पर कॉल कर सकता है?",
        "name": "ठीक है। आपका नाम क्या है? चाहें तो इसे छोड़ सकते हैं।",
        "done": "धन्यवाद। आपकी रिपोर्ट नियंत्रण कक्ष को भेज दी गई है। अगर सुरक्षित हो, तो वहीं रहिए। हो सके तो 112 पर भी कॉल कीजिए।",
        "retry": "माफ़ कीजिए, मैं सुन नहीं पाई। कृपया फिर से बोलिए, या अपना जवाब लिखिए।",
        "112": "एक एक दो",
    },
    "en": {
        "greeting": "This is emergency help. You can speak in any language. Please tell us what has happened.",
        "situation": "Please tell us what has happened.",
        "location": "Okay. Where exactly are you? Tell us the nearest landmark, road, or area name.",
        "people": "Okay. How many people are with you?",
        "safety": "Okay. Is anyone injured, trapped, or in immediate danger?",
        "callback": "Okay. Which phone number can the rescue team call you on?",
        "name": "Okay. What is your name? You can skip this.",
        "done": "Thank you. Your report has been sent to the control room. If it is safe, stay where you are. If you can, also call 112.",
        "retry": "Sorry, I could not hear you. Please say that again, or type your answer.",
        "112": "one one two",
    },
    "ml": {
        "situation": "എന്താണ് സംഭവിച്ചതെന്ന് ദയവായി പറയൂ.",
        "location": "ശരി. നിങ്ങൾ കൃത്യമായി എവിടെയാണ്? അടുത്തുള്ള ഒരു അടയാളം, റോഡ്, അല്ലെങ്കിൽ സ്ഥലത്തിന്റെ പേര് പറയൂ.",
        "people": "ശരി. നിങ്ങളുടെ കൂടെ എത്ര പേരുണ്ട്?",
        "safety": "ശരി. ആർക്കെങ്കിലും പരിക്കുണ്ടോ, ആരെങ്കിലും കുടുങ്ങിക്കിടക്കുന്നുണ്ടോ, അല്ലെങ്കിൽ ഇപ്പോൾ അപകടത്തിലാണോ?",
        "callback": "ശരി. രക്ഷാസംഘത്തിന് നിങ്ങളെ ഏത് ഫോൺ നമ്പറിൽ വിളിക്കാം?",
        "name": "ശരി. നിങ്ങളുടെ പേര് എന്താണ്? വേണമെങ്കിൽ ഇത് ഒഴിവാക്കാം.",
        "done": "നന്ദി. നിങ്ങളുടെ റിപ്പോർട്ട് കൺട്രോൾ റൂമിലേക്ക് അയച്ചു. സുരക്ഷിതമാണെങ്കിൽ, അവിടെത്തന്നെ നിൽക്കൂ. കഴിയുമെങ്കിൽ 112-ലും വിളിക്കൂ.",
        "retry": "ക്ഷമിക്കണം, എനിക്ക് കേൾക്കാൻ കഴിഞ്ഞില്ല. ദയവായി വീണ്ടും പറയൂ, അല്ലെങ്കിൽ മറുപടി ടൈപ്പ് ചെയ്യൂ.",
        "112": "ഒന്ന് ഒന്ന് രണ്ട്",
    },
    "mr": {
        "situation": "कृपया सांगा, काय झाले आहे?",
        "location": "ठीक आहे. तुम्ही नेमके कुठे आहात? जवळची एखादी खूण, रस्ता किंवा भागाचे नाव सांगा.",
        "people": "ठीक आहे. तुमच्यासोबत किती लोक आहेत?",
        "safety": "ठीक आहे. कोणी जखमी आहे का, अडकले आहे का, किंवा आत्ता धोक्यात आहे का?",
        "callback": "ठीक आहे. बचाव पथक तुम्हाला कोणत्या फोन नंबरवर कॉल करू शकते?",
        "name": "ठीक आहे. तुमचे नाव काय आहे? हवे असल्यास हे वगळू शकता.",
        "done": "धन्यवाद. तुमचा अहवाल नियंत्रण कक्षाकडे पाठवला आहे. सुरक्षित असल्यास, तिथेच थांबा. शक्य असल्यास 112 वरही कॉल करा.",
        "retry": "माफ करा, मला ऐकू आले नाही. कृपया पुन्हा सांगा, किंवा तुमचे उत्तर टाइप करा.",
        "112": "एक एक दोन",
    },
    "ta": {
        "situation": "என்ன நடந்தது என்று தயவுசெய்து சொல்லுங்கள்.",
        "location": "சரி. நீங்கள் சரியாக எங்கே இருக்கிறீர்கள்? அருகிலுள்ள அடையாளம், சாலை அல்லது பகுதியின் பெயரைச் சொல்லுங்கள்.",
        "people": "சரி. உங்களுடன் எத்தனை பேர் இருக்கிறார்கள்?",
        "safety": "சரி. யாராவது காயமடைந்திருக்கிறார்களா, சிக்கிக்கொண்டிருக்கிறார்களா, அல்லது இப்போது ஆபத்தில் இருக்கிறார்களா?",
        "callback": "சரி. மீட்புக் குழு உங்களை எந்த தொலைபேசி எண்ணில் அழைக்கலாம்?",
        "name": "சரி. உங்கள் பெயர் என்ன? விரும்பினால் இதைத் தவிர்க்கலாம்.",
        "done": "நன்றி. உங்கள் புகார் கட்டுப்பாட்டு அறைக்கு அனுப்பப்பட்டது. பாதுகாப்பாக இருந்தால், அங்கேயே இருங்கள். முடிந்தால் 112-க்கும் அழையுங்கள்.",
        "retry": "மன்னிக்கவும், எனக்குக் கேட்கவில்லை. தயவுசெய்து மீண்டும் சொல்லுங்கள், அல்லது உங்கள் பதிலைத் தட்டச்சு செய்யுங்கள்.",
        "112": "ஒன்று ஒன்று இரண்டு",
    },
    "te": {
        "situation": "ఏం జరిగిందో దయచేసి చెప్పండి.",
        "location": "సరే. మీరు సరిగ్గా ఎక్కడ ఉన్నారు? దగ్గరలోని గుర్తు, రోడ్డు లేదా ప్రాంతం పేరు చెప్పండి.",
        "people": "సరే. మీతో ఎంత మంది ఉన్నారు?",
        "safety": "సరే. ఎవరైనా గాయపడ్డారా, చిక్కుకుపోయారా, లేదా ఇప్పుడు ప్రమాదంలో ఉన్నారా?",
        "callback": "సరే. రక్షణ బృందం మీకు ఏ ఫోన్ నంబర్‌కు కాల్ చేయవచ్చు?",
        "name": "సరే. మీ పేరు ఏమిటి? కావాలంటే దీన్ని వదిలేయవచ్చు.",
        "done": "ధన్యవాదాలు. మీ నివేదిక కంట్రోల్ రూమ్‌కు పంపబడింది. సురక్షితంగా ఉంటే, అక్కడే ఉండండి. వీలైతే 112కు కూడా కాల్ చేయండి.",
        "retry": "క్షమించండి, నాకు వినిపించలేదు. దయచేసి మళ్ళీ చెప్పండి, లేదా మీ సమాధానం టైప్ చేయండి.",
        "112": "ఒకటి ఒకటి రెండు",
    },
    "kn": {
        "situation": "ಏನಾಯಿತು ಎಂದು ದಯವಿಟ್ಟು ಹೇಳಿ.",
        "location": "ಸರಿ. ನೀವು ನಿಖರವಾಗಿ ಎಲ್ಲಿದ್ದೀರಿ? ಹತ್ತಿರದ ಗುರುತು, ರಸ್ತೆ ಅಥವಾ ಪ್ರದೇಶದ ಹೆಸರು ಹೇಳಿ.",
        "people": "ಸರಿ. ನಿಮ್ಮ ಜೊತೆ ಎಷ್ಟು ಜನ ಇದ್ದಾರೆ?",
        "safety": "ಸರಿ. ಯಾರಾದರೂ ಗಾಯಗೊಂಡಿದ್ದಾರಾ, ಸಿಲುಕಿಕೊಂಡಿದ್ದಾರಾ, ಅಥವಾ ಈಗ ಅಪಾಯದಲ್ಲಿದ್ದಾರಾ?",
        "callback": "ಸರಿ. ರಕ್ಷಣಾ ತಂಡ ನಿಮಗೆ ಯಾವ ಫೋನ್ ಸಂಖ್ಯೆಗೆ ಕರೆ ಮಾಡಬಹುದು?",
        "name": "ಸರಿ. ನಿಮ್ಮ ಹೆಸರೇನು? ಬೇಕಾದರೆ ಇದನ್ನು ಬಿಡಬಹುದು.",
        "done": "ಧನ್ಯವಾದಗಳು. ನಿಮ್ಮ ವರದಿಯನ್ನು ನಿಯಂತ್ರಣ ಕೊಠಡಿಗೆ ಕಳುಹಿಸಲಾಗಿದೆ. ಸುರಕ್ಷಿತವಾಗಿದ್ದರೆ, ಅಲ್ಲೇ ಇರಿ. ಸಾಧ್ಯವಾದರೆ 112ಕ್ಕೂ ಕರೆ ಮಾಡಿ.",
        "retry": "ಕ್ಷಮಿಸಿ, ನನಗೆ ಕೇಳಿಸಲಿಲ್ಲ. ದಯವಿಟ್ಟು ಮತ್ತೆ ಹೇಳಿ, ಅಥವಾ ನಿಮ್ಮ ಉತ್ತರವನ್ನು ಟೈಪ್ ಮಾಡಿ.",
        "112": "ಒಂದು ಒಂದು ಎರಡು",
    },
    "bn": {
        "situation": "কী হয়েছে, দয়া করে বলুন।",
        "location": "ঠিক আছে। আপনি ঠিক কোথায় আছেন? কাছের কোনো চিহ্ন, রাস্তা বা এলাকার নাম বলুন।",
        "people": "ঠিক আছে। আপনার সঙ্গে কতজন আছেন?",
        "safety": "ঠিক আছে। কেউ কি আহত, আটকে পড়েছেন, বা এখন বিপদে আছেন?",
        "callback": "ঠিক আছে। উদ্ধারকারী দল আপনাকে কোন ফোন নম্বরে ফোন করতে পারে?",
        "name": "ঠিক আছে। আপনার নাম কী? চাইলে এটা বাদ দিতে পারেন।",
        "done": "ধন্যবাদ। আপনার রিপোর্ট নিয়ন্ত্রণ কক্ষে পাঠানো হয়েছে। নিরাপদ হলে, সেখানেই থাকুন। সম্ভব হলে 112-তেও ফোন করুন।",
        "retry": "দুঃখিত, আমি শুনতে পাইনি। দয়া করে আবার বলুন, অথবা আপনার উত্তর লিখুন।",
        "112": "এক এক দুই",
    },
    "gu": {
        "situation": "કૃપા કરીને કહો, શું થયું છે?",
        "location": "ઠીક છે. તમે બરાબર ક્યાં છો? નજીકની કોઈ નિશાની, રસ્તો કે વિસ્તારનું નામ કહો.",
        "people": "ઠીક છે. તમારી સાથે કેટલા લોકો છે?",
        "safety": "ઠીક છે. શું કોઈ ઘાયલ છે, ફસાયેલું છે, કે અત્યારે જોખમમાં છે?",
        "callback": "ઠીક છે. બચાવ ટીમ તમને કયા ફોન નંબર પર કૉલ કરી શકે?",
        "name": "ઠીક છે. તમારું નામ શું છે? ઇચ્છો તો આ છોડી શકો છો.",
        "done": "આભાર. તમારો અહેવાલ નિયંત્રણ ખંડને મોકલી દેવાયો છે. સલામત હોય તો, ત્યાં જ રહો. શક્ય હોય તો 112 પર પણ કૉલ કરો.",
        "retry": "માફ કરશો, મને સંભળાયું નહીં. કૃપા કરીને ફરીથી કહો, અથવા તમારો જવાબ લખો.",
        "112": "એક એક બે",
    },
    "pa": {
        "situation": "ਕਿਰਪਾ ਕਰਕੇ ਦੱਸੋ, ਕੀ ਹੋਇਆ ਹੈ?",
        "location": "ਠੀਕ ਹੈ। ਤੁਸੀਂ ਠੀਕ ਕਿੱਥੇ ਹੋ? ਨੇੜੇ ਦੀ ਕੋਈ ਨਿਸ਼ਾਨੀ, ਸੜਕ ਜਾਂ ਇਲਾਕੇ ਦਾ ਨਾਂ ਦੱਸੋ।",
        "people": "ਠੀਕ ਹੈ। ਤੁਹਾਡੇ ਨਾਲ ਕਿੰਨੇ ਲੋਕ ਹਨ?",
        "safety": "ਠੀਕ ਹੈ। ਕੀ ਕੋਈ ਜ਼ਖਮੀ ਹੈ, ਫਸਿਆ ਹੋਇਆ ਹੈ, ਜਾਂ ਇਸ ਵੇਲੇ ਖ਼ਤਰੇ ਵਿੱਚ ਹੈ?",
        "callback": "ਠੀਕ ਹੈ। ਬਚਾਅ ਟੀਮ ਤੁਹਾਨੂੰ ਕਿਸ ਫ਼ੋਨ ਨੰਬਰ 'ਤੇ ਕਾਲ ਕਰ ਸਕਦੀ ਹੈ?",
        "name": "ਠੀਕ ਹੈ। ਤੁਹਾਡਾ ਨਾਂ ਕੀ ਹੈ? ਚਾਹੋ ਤਾਂ ਇਹ ਛੱਡ ਸਕਦੇ ਹੋ।",
        "done": "ਧੰਨਵਾਦ। ਤੁਹਾਡੀ ਰਿਪੋਰਟ ਕੰਟਰੋਲ ਰੂਮ ਨੂੰ ਭੇਜ ਦਿੱਤੀ ਗਈ ਹੈ। ਜੇ ਸੁਰੱਖਿਅਤ ਹੋਵੇ, ਤਾਂ ਉੱਥੇ ਹੀ ਰਹੋ। ਹੋ ਸਕੇ ਤਾਂ 112 'ਤੇ ਵੀ ਕਾਲ ਕਰੋ।",
        "retry": "ਮਾਫ਼ ਕਰਨਾ, ਮੈਨੂੰ ਸੁਣਾਈ ਨਹੀਂ ਦਿੱਤਾ। ਕਿਰਪਾ ਕਰਕੇ ਦੁਬਾਰਾ ਦੱਸੋ, ਜਾਂ ਆਪਣਾ ਜਵਾਬ ਲਿਖੋ।",
        "112": "ਇੱਕ ਇੱਕ ਦੋ",
    },
}

SUPPORTED = frozenset(_T)


@dataclass(frozen=True)
class Line:
    language: str
    text: str  # shown on screen
    spoken: str  # sent to the speech engine


def supported(language: str | None) -> str:
    """The language to use: the given one if supported, otherwise the default (Hindi)."""
    code = (language or "").split("-")[0].lower()
    return code if code in SUPPORTED else DEFAULT_LANGUAGE


def line(language: str, key: str) -> Line:
    table = _T[supported(language)]
    text = table.get(key) or _T[DEFAULT_LANGUAGE][key]
    return Line(supported(language), text, text.replace("112", table["112"]))


def opening() -> list[Line]:
    """The first thing a caller hears: Hindi, then English, inviting any language."""
    return [line("hi", "greeting"), line("en", "greeting")]


_SCRIPTS = (
    ("ml", 0x0D00, 0x0D7F), ("ta", 0x0B80, 0x0BFF), ("te", 0x0C00, 0x0C7F),
    ("kn", 0x0C80, 0x0CFF), ("bn", 0x0980, 0x09FF), ("gu", 0x0A80, 0x0AFF),
    ("pa", 0x0A00, 0x0A7F), ("hi", 0x0900, 0x097F),
)


def language_of_text(text: str) -> str | None:
    """Guess the language of typed text from its script. Latin script reads as English.

    Devanagari is reported as Hindi: Marathi and Konkani share the script and
    cannot be told apart this way.
    """
    counts: dict[str, int] = {}
    latin = 0
    for ch in text:
        cp = ord(ch)
        if ch.isascii() and ch.isalpha():
            latin += 1
            continue
        for code, lo, hi in _SCRIPTS:
            if lo <= cp <= hi:
                counts[code] = counts.get(code, 0) + 1
                break
    if counts:
        return max(counts, key=lambda k: counts[k])
    return "en" if latin >= 3 else None
