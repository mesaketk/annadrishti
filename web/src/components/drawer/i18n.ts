// Small UI string map for the farmer view. en/hi/mr/te are written; other languages fall back to English.
// Translations are machine-drafted and have not been reviewed by native speakers.
import type { Lang } from '../../types'
import { EXTRA } from './i18n.extra'

type Dict = Record<string, string>
const en: Dict = {
  'tab.advice': 'Advice', 'tab.why': 'Why', 'tab.trends': 'Trends',
  'season.this': 'This {season}', 'season.next': 'Next {season}', 'season.rabi': 'Rabi', 'season.kharif': 'Kharif', 'season.none': 'This season',
  'light.low': 'Low', 'light.watch': 'Watch', 'light.act': 'Act now', 'light.none': 'No estimate',
  'light.low.say': 'Low risk for farmers', 'light.watch.say': 'Be careful, risk is moderate', 'light.act.say': 'High risk, act now', 'light.none.say': 'No estimate available yet',
  'form.title': 'Tell us about your farm', 'form.holding': 'Land you farm', 'form.water': 'Water', 'form.crop': 'Main crop',
  'holding.marginal': 'Less than 1 ha', 'holding.small': '1 to 2 ha', 'holding.medium_large': 'More than 2 ha',
  'water.rainfed': 'Only rain', 'water.partial': 'Some irrigation', 'water.irrigated': 'Fully irrigated',
  'crop.other': 'Other', 'form.livestock': 'I keep cattle or goats', 'form.tenant': 'I farm on rented land', 'yes': 'Yes', 'no': 'No',
  'btn.get': 'Get advice', 'btn.getting': 'Preparing your advice…', 'btn.listen': 'Listen', 'btn.loading': 'Loading audio…', 'btn.share': 'Share on WhatsApp', 'btn.copy': 'Copy', 'btn.copied': 'Copied', 'btn.again': 'Get new advice',
  'lang.label': 'Language', 'advice.for': 'Advice for your farm', 'err.generic': 'Could not get advice. Please try again.', 'err.audio': 'Audio is not available right now.',
  'help.title': 'Where to get help', 'help.kvk': 'Krishi Vigyan Kendra (farm science centre)', 'help.kvk.d': 'Free advice on seeds, sowing and pests',
  'help.office': 'District agriculture office', 'help.office.d': 'Seed, subsidies and drought schemes (Kisan Call Centre 1800-180-1551)',
  'help.pmfby': 'Crop insurance (PMFBY)', 'help.pmfby.d': 'Check the last date and enrol', 'help.pds': 'Nearest ration (PDS) shop', 'help.pds.d': 'Find your shop and entitlements',
  'why.title': 'Why this level?', 'why.past': 'In past El Niño years here, rain was about {rain} % below normal and harvests about {yield} % lower.', 'why.none': 'No explanation available yet.',
  'trends.yield.title': 'Grain harvest each year', 'trends.yield.cap': 'Tonnes of grain per hectare. Pink bands are El Niño years. In those years harvests were usually lower.',
  'trends.yield.cap.n': 'Tonnes of grain per hectare. Pink bands are El Niño years, when harvests were about {n} % lower than usual.',
  'trends.rain.title': 'Monsoon rain each year', 'trends.rain.cap': 'Bars below the line mean less rain than normal. Outlined bars are El Niño years.',
  'trends.rain.cap.n': 'Bars below the line mean less rain than normal. In El Niño years rain was about {n} % below normal.',
  'trends.none': 'Year-by-year history is not available yet.', 'loading': 'Loading…',
}
const hi: Dict = {
  'tab.advice': 'सलाह', 'tab.why': 'क्यों', 'tab.trends': 'रुझान',
  'season.this': 'इस {season}', 'season.next': 'अगले {season}', 'season.rabi': 'रबी', 'season.kharif': 'खरीफ', 'season.none': 'इस मौसम',
  'light.low': 'कम', 'light.watch': 'सावधान', 'light.act': 'अभी कदम उठाएँ', 'light.none': 'अनुमान नहीं',
  'light.low.say': 'किसानों के लिए जोखिम कम है', 'light.watch.say': 'सावधान रहें, जोखिम मध्यम है', 'light.act.say': 'जोखिम ज़्यादा है, अभी कदम उठाएँ', 'light.none.say': 'अभी अनुमान उपलब्ध नहीं है',
  'form.title': 'अपने खेत के बारे में बताइए', 'form.holding': 'आपकी जोत', 'form.water': 'पानी', 'form.crop': 'मुख्य फसल',
  'holding.marginal': '1 हेक्टेयर से कम', 'holding.small': '1 से 2 हेक्टेयर', 'holding.medium_large': '2 हेक्टेयर से ज़्यादा',
  'water.rainfed': 'सिर्फ़ बारिश', 'water.partial': 'थोड़ी सिंचाई', 'water.irrigated': 'पूरी सिंचाई',
  'crop.other': 'अन्य', 'form.livestock': 'मेरे पास पशु हैं', 'form.tenant': 'मैं बटाई/किराये की ज़मीन पर खेती करता/करती हूँ', 'yes': 'हाँ', 'no': 'नहीं',
  'btn.get': 'सलाह पाएँ', 'btn.getting': 'आपकी सलाह तैयार हो रही है…', 'btn.listen': 'सुनें', 'btn.loading': 'ऑडियो आ रहा है…', 'btn.share': 'व्हाट्सऐप पर भेजें', 'btn.copy': 'कॉपी करें', 'btn.copied': 'कॉपी हो गया', 'btn.again': 'नई सलाह पाएँ',
  'lang.label': 'भाषा', 'advice.for': 'आपके खेत के लिए सलाह', 'err.generic': 'सलाह नहीं मिल पाई। कृपया फिर कोशिश करें।', 'err.audio': 'अभी ऑडियो उपलब्ध नहीं है।',
  'help.title': 'मदद कहाँ मिलेगी', 'help.kvk': 'कृषि विज्ञान केंद्र (KVK)', 'help.kvk.d': 'बीज, बुवाई और कीट पर मुफ़्त सलाह',
  'help.office': 'ज़िला कृषि कार्यालय', 'help.office.d': 'बीज, अनुदान और सूखा योजनाएँ (किसान कॉल सेंटर 1800-180-1551)',
  'help.pmfby': 'फसल बीमा (PMFBY)', 'help.pmfby.d': 'अंतिम तारीख देखें और नामांकन करें', 'help.pds': 'नज़दीकी राशन (PDS) दुकान', 'help.pds.d': 'अपनी दुकान और हक़ देखें',
  'why.title': 'यह स्तर क्यों?', 'why.past': 'यहाँ पिछले एल नीनो वर्षों में बारिश सामान्य से लगभग {rain} % कम रही और पैदावार लगभग {yield} % कम हुई।', 'why.none': 'अभी कारण उपलब्ध नहीं है।',
  'trends.yield.title': 'हर साल अनाज की पैदावार', 'trends.yield.cap': 'प्रति हेक्टेयर अनाज (टन)। गुलाबी पट्टियाँ एल नीनो वर्ष हैं। उन वर्षों में पैदावार आम तौर पर कम रही।',
  'trends.yield.cap.n': 'प्रति हेक्टेयर अनाज (टन)। गुलाबी पट्टियाँ एल नीनो वर्ष हैं, जब पैदावार सामान्य से लगभग {n} % कम रही।',
  'trends.rain.title': 'हर साल मानसून की बारिश', 'trends.rain.cap': 'रेखा के नीचे की पट्टी यानी सामान्य से कम बारिश। बाहरी रेखा वाली पट्टियाँ एल नीनो वर्ष हैं।',
  'trends.rain.cap.n': 'रेखा के नीचे की पट्टी यानी सामान्य से कम बारिश। एल नीनो वर्षों में बारिश सामान्य से लगभग {n} % कम रही।',
  'trends.none': 'साल-दर-साल का इतिहास अभी उपलब्ध नहीं है।', 'loading': 'लोड हो रहा है…',
}
const mr: Dict = {
  'tab.advice': 'सल्ला', 'tab.why': 'का', 'tab.trends': 'कल',
  'season.this': 'यंदाचा {season}', 'season.next': 'पुढील {season}', 'season.rabi': 'रब्बी', 'season.kharif': 'खरीप', 'season.none': 'या हंगामात',
  'light.low': 'कमी', 'light.watch': 'सावध राहा', 'light.act': 'आत्ताच कृती करा', 'light.none': 'अंदाज नाही',
  'light.low.say': 'शेतकऱ्यांसाठी धोका कमी आहे', 'light.watch.say': 'सावध राहा, धोका मध्यम आहे', 'light.act.say': 'धोका जास्त आहे, आत्ताच कृती करा', 'light.none.say': 'अजून अंदाज उपलब्ध नाही',
  'form.title': 'तुमच्या शेताबद्दल सांगा', 'form.holding': 'तुमची जमीन', 'form.water': 'पाणी', 'form.crop': 'मुख्य पीक',
  'holding.marginal': '१ हेक्टरपेक्षा कमी', 'holding.small': '१ ते २ हेक्टर', 'holding.medium_large': '२ हेक्टरपेक्षा जास्त',
  'water.rainfed': 'फक्त पाऊस', 'water.partial': 'थोडी सिंचन सोय', 'water.irrigated': 'पूर्ण सिंचन',
  'crop.other': 'इतर', 'form.livestock': 'माझ्याकडे जनावरे आहेत', 'form.tenant': 'मी भाड्याच्या/बटाईच्या जमिनीत शेती करतो/करते', 'yes': 'होय', 'no': 'नाही',
  'btn.get': 'सल्ला मिळवा', 'btn.getting': 'तुमचा सल्ला तयार होत आहे…', 'btn.listen': 'ऐका', 'btn.loading': 'ऑडिओ येत आहे…', 'btn.share': 'व्हॉट्सॲपवर पाठवा', 'btn.copy': 'कॉपी करा', 'btn.copied': 'कॉपी झाले', 'btn.again': 'नवीन सल्ला मिळवा',
  'lang.label': 'भाषा', 'advice.for': 'तुमच्या शेतासाठी सल्ला', 'err.generic': 'सल्ला मिळाला नाही. कृपया पुन्हा प्रयत्न करा.', 'err.audio': 'सध्या ऑडिओ उपलब्ध नाही.',
  'help.title': 'मदत कुठे मिळेल', 'help.kvk': 'कृषी विज्ञान केंद्र (KVK)', 'help.kvk.d': 'बियाणे, पेरणी आणि किडींबाबत मोफत सल्ला',
  'help.office': 'जिल्हा कृषी कार्यालय', 'help.office.d': 'बियाणे, अनुदान आणि दुष्काळ योजना (किसान कॉल सेंटर 1800-180-1551)',
  'help.pmfby': 'पीक विमा (PMFBY)', 'help.pmfby.d': 'शेवटची तारीख पाहा आणि नोंदणी करा', 'help.pds': 'जवळचे रेशन (PDS) दुकान', 'help.pds.d': 'तुमचे दुकान आणि हक्क पाहा',
  'why.title': 'ही पातळी का?', 'why.past': 'येथे मागील एल निनो वर्षांत पाऊस सामान्यपेक्षा सुमारे {rain} % कमी होता आणि उत्पादन सुमारे {yield} % घटले.', 'why.none': 'अजून कारण उपलब्ध नाही.',
  'trends.yield.title': 'दरवर्षी धान्य उत्पादन', 'trends.yield.cap': 'हेक्टरी धान्य (टन). गुलाबी पट्टे एल निनो वर्षे आहेत. त्या वर्षांत उत्पादन साधारणपणे कमी होते.',
  'trends.yield.cap.n': 'हेक्टरी धान्य (टन). गुलाबी पट्टे एल निनो वर्षे आहेत, तेव्हा उत्पादन नेहमीपेक्षा सुमारे {n} % कमी होते.',
  'trends.rain.title': 'दरवर्षी मान्सूनचा पाऊस', 'trends.rain.cap': 'रेषेखालील पट्टा म्हणजे सामान्यपेक्षा कमी पाऊस. बाह्यरेषा असलेले पट्टे एल निनो वर्षे आहेत.',
  'trends.rain.cap.n': 'रेषेखालील पट्टा म्हणजे सामान्यपेक्षा कमी पाऊस. एल निनो वर्षांत पाऊस सामान्यपेक्षा सुमारे {n} % कमी होता.',
  'trends.none': 'वर्षानुवर्षांचा इतिहास अजून उपलब्ध नाही.', 'loading': 'लोड होत आहे…',
}
const te: Dict = {
  'tab.advice': 'సలహా', 'tab.why': 'ఎందుకు', 'tab.trends': 'ధోరణులు',
  'season.this': 'ఈ {season}', 'season.next': 'వచ్చే {season}', 'season.rabi': 'రబీ', 'season.kharif': 'ఖరీఫ్', 'season.none': 'ఈ సీజన్',
  'light.low': 'తక్కువ', 'light.watch': 'జాగ్రత్త', 'light.act': 'ఇప్పుడే చర్య తీసుకోండి', 'light.none': 'అంచనా లేదు',
  'light.low.say': 'రైతులకు ప్రమాదం తక్కువ', 'light.watch.say': 'జాగ్రత్తగా ఉండండి, ప్రమాదం మధ్యస్థం', 'light.act.say': 'ప్రమాదం ఎక్కువ, ఇప్పుడే చర్య తీసుకోండి', 'light.none.say': 'ఇంకా అంచనా అందుబాటులో లేదు',
  'form.title': 'మీ పొలం గురించి చెప్పండి', 'form.holding': 'మీ భూమి', 'form.water': 'నీరు', 'form.crop': 'ప్రధాన పంట',
  'holding.marginal': '1 హెక్టారు కంటే తక్కువ', 'holding.small': '1 నుండి 2 హెక్టార్లు', 'holding.medium_large': '2 హెక్టార్లకు పైగా',
  'water.rainfed': 'వర్షం మాత్రమే', 'water.partial': 'కొంత సాగునీరు', 'water.irrigated': 'పూర్తి సాగునీరు',
  'crop.other': 'ఇతర', 'form.livestock': 'నాకు పశువులు ఉన్నాయి', 'form.tenant': 'నేను కౌలు భూమిలో సాగు చేస్తున్నాను', 'yes': 'అవును', 'no': 'కాదు',
  'btn.get': 'సలహా పొందండి', 'btn.getting': 'మీ సలహా సిద్ధమవుతోంది…', 'btn.listen': 'వినండి', 'btn.loading': 'ఆడియో వస్తోంది…', 'btn.share': 'వాట్సాప్‌లో పంపండి', 'btn.copy': 'కాపీ', 'btn.copied': 'కాపీ అయింది', 'btn.again': 'కొత్త సలహా పొందండి',
  'lang.label': 'భాష', 'advice.for': 'మీ పొలానికి సలహా', 'err.generic': 'సలహా రాలేదు. దయచేసి మళ్లీ ప్రయత్నించండి.', 'err.audio': 'ప్రస్తుతం ఆడియో అందుబాటులో లేదు.',
  'help.title': 'సహాయం ఎక్కడ దొరుకుతుంది', 'help.kvk': 'కృషి విజ్ఞాన కేంద్రం (KVK)', 'help.kvk.d': 'విత్తనాలు, విత్తడం, చీడపీడలపై ఉచిత సలహా',
  'help.office': 'జిల్లా వ్యవసాయ కార్యాలయం', 'help.office.d': 'విత్తనాలు, సబ్సిడీలు, కరువు పథకాలు (కిసాన్ కాల్ సెంటర్ 1800-180-1551)',
  'help.pmfby': 'పంటల బీమా (PMFBY)', 'help.pmfby.d': 'చివరి తేదీ చూసి నమోదు చేసుకోండి', 'help.pds': 'సమీప రేషన్ (PDS) దుకాణం', 'help.pds.d': 'మీ దుకాణం, హక్కులు చూడండి',
  'why.title': 'ఈ స్థాయి ఎందుకు?', 'why.past': 'ఇక్కడ గత ఎల్ నినో సంవత్సరాల్లో వర్షం సాధారణం కంటే సుమారు {rain} % తక్కువగా ఉంది, దిగుబడి సుమారు {yield} % తగ్గింది.', 'why.none': 'ఇంకా వివరణ అందుబాటులో లేదు.',
  'trends.yield.title': 'ప్రతి సంవత్సరం ధాన్యం దిగుబడి', 'trends.yield.cap': 'హెక్టారుకు ధాన్యం (టన్నులు). గులాబీ పట్టీలు ఎల్ నినో సంవత్సరాలు. ఆ సంవత్సరాల్లో దిగుబడి సాధారణంగా తక్కువ.',
  'trends.yield.cap.n': 'హెక్టారుకు ధాన్యం (టన్నులు). గులాబీ పట్టీలు ఎల్ నినో సంవత్సరాలు, అప్పుడు దిగుబడి సాధారణం కంటే సుమారు {n} % తక్కువ.',
  'trends.rain.title': 'ప్రతి సంవత్సరం రుతుపవన వర్షం', 'trends.rain.cap': 'గీత కింద పట్టీ అంటే సాధారణం కంటే తక్కువ వర్షం. అంచు గీతలున్న పట్టీలు ఎల్ నినో సంవత్సరాలు.',
  'trends.rain.cap.n': 'గీత కింద పట్టీ అంటే సాధారణం కంటే తక్కువ వర్షం. ఎల్ నినో సంవత్సరాల్లో వర్షం సాధారణం కంటే సుమారు {n} % తక్కువ.',
  'trends.none': 'సంవత్సరాల వారీ చరిత్ర ఇంకా అందుబాటులో లేదు.', 'loading': 'లోడ్ అవుతోంది…',
}
const DICTS: Partial<Record<Lang, Dict>> = { en: { ...en, ...EXTRA.en }, hi: { ...hi, ...EXTRA.hi }, mr: { ...mr, ...EXTRA.mr }, te: { ...te, ...EXTRA.te } }
export const SUPPORTED_UI: Lang[] = ['en', 'hi', 'mr', 'te']

export function t(lang: Lang, key: string, params?: Record<string, string | number>): string {
  let s = DICTS[lang]?.[key] ?? DICTS.en?.[key] ?? key
  if (params) for (const [k, v] of Object.entries(params)) s = s.replace(new RegExp(`\\{${k}\\}`, 'g'), String(v))
  return s.replace(/(\d) %/g, '$1\u00a0%')
}
export const hasLocal = (lang: Lang) => !!DICTS[lang] && lang !== 'en'

// ---- farmer "Why" sentences (subset of drivers; others fall back to the English sentence)
type DrvDict = Record<string, string>
const DRV: Partial<Record<Lang, DrvDict>> = {
  hi: {
    expected_yield_loss: 'इस मौसम में पैदावार सामान्य साल से लगभग {n} % कम रहने का अनुमान है।',
    rain_deficit_risk: 'मानसून की बारिश 10 % से ज़्यादा कम रहने की लगभग {n} % संभावना है।',
    rainfed_share: 'लगभग {n} % खेती सिर्फ़ बारिश पर निर्भर है, सिंचाई नहीं है।',
    child_stunting: '5 साल से कम उम्र के {n} % बच्चे उम्र के हिसाब से कद में छोटे हैं।',
    terminal_heat_risk: 'ऐसे {n} % सर्दियों में फरवरी–मार्च की गर्मी से गेहूँ और चने की फसल कमज़ोर हुई।',
    'ndvi_stress.neg': 'उपग्रह तस्वीरों में अभी फसलें सामान्य से कम हरी दिख रही हैं।',
    'ndvi_stress.norm': 'उपग्रह तस्वीरों में अभी फसलें लगभग सामान्य दिख रही हैं।',
    'ndvi_stress.pos': 'उपग्रह तस्वीरों में अभी फसलें सामान्य से ज़्यादा हरी दिख रही हैं।',
    dry_antecedent_season: 'पिछले मानसून ({year}) में सामान्य से {n} % कम बारिश हुई, इसलिए मिट्टी में नमी कम है।',
    top_crop_share: '{n} % खेती एक ही फसल ({crop}) की है, इसलिए एक खराब मौसम भारी पड़ता है।',
    weak_kharif_carryover: 'पिछले खरीफ ({year}) की पैदावार सामान्य से {n} % कम थी, इसलिए रबी में बीज और आमदनी कम है।',
    small_marginal_share: '{n} % खेत 2 हेक्टेयर से छोटे हैं, इसलिए परिवारों के पास सहारा कम है।',
    yield_cv: 'पैदावार हर साल लगभग {n} % ऊपर-नीचे होती है।',
    low_self_sufficiency: 'ज़िले में लोगों की ज़रूरत का सिर्फ़ लगभग {n} % अनाज उगता है।',
  },
  mr: {
    expected_yield_loss: 'या हंगामात उत्पादन सामान्य वर्षापेक्षा सुमारे {n} % कमी राहण्याचा अंदाज आहे.',
    rain_deficit_risk: 'मान्सूनचा पाऊस १० % पेक्षा जास्त कमी पडण्याची सुमारे {n} % शक्यता आहे.',
    rainfed_share: 'सुमारे {n} % शेती फक्त पावसावर अवलंबून आहे, सिंचन नाही.',
    child_stunting: '५ वर्षांखालील {n} % मुले वयाच्या मानाने खुजी आहेत.',
    terminal_heat_risk: 'अशा {n} % हिवाळ्यांत फेब्रुवारी–मार्चच्या उष्णतेने गहू आणि हरभरा पिकाला फटका बसला.',
    'ndvi_stress.neg': 'उपग्रह छायाचित्रांत सध्या पिके सामान्यपेक्षा कमी हिरवी दिसत आहेत.',
    'ndvi_stress.norm': 'उपग्रह छायाचित्रांत सध्या पिके साधारण सामान्य दिसत आहेत.',
    'ndvi_stress.pos': 'उपग्रह छायाचित्रांत सध्या पिके सामान्यपेक्षा जास्त हिरवी दिसत आहेत.',
    dry_antecedent_season: 'मागील मान्सूनमध्ये ({year}) सामान्यपेक्षा {n} % कमी पाऊस झाला, त्यामुळे जमिनीत ओलावा कमी आहे.',
    top_crop_share: '{n} % शेती एकाच पिकाची ({crop}) आहे, त्यामुळे एक वाईट हंगामही जड जातो.',
    weak_kharif_carryover: 'मागील खरिपाचे ({year}) उत्पादन सामान्यपेक्षा {n} % कमी होते, त्यामुळे रब्बीत बियाणे आणि उत्पन्न कमी आहे.',
    small_marginal_share: '{n} % शेते २ हेक्टरपेक्षा लहान आहेत, त्यामुळे कुटुंबांना आधार कमी आहे.',
    yield_cv: 'उत्पादन दरवर्षी सुमारे {n} % ने वर-खाली होते.',
    low_self_sufficiency: 'जिल्ह्यात लोकांच्या गरजेच्या फक्त सुमारे {n} % धान्य पिकते.',
  },
  te: {
    expected_yield_loss: 'ఈ సీజన్‌లో దిగుబడి సాధారణ సంవత్సరం కంటే సుమారు {n} % తక్కువగా ఉండవచ్చని అంచనా.',
    rain_deficit_risk: 'రుతుపవన వర్షం 10 % కంటే ఎక్కువ తగ్గే అవకాశం సుమారు {n} % ఉంది.',
    rainfed_share: 'సుమారు {n} % సాగు వర్షంపైనే ఆధారపడి ఉంది, సాగునీరు లేదు.',
    child_stunting: '5 ఏళ్లలోపు పిల్లల్లో {n} % మంది వయసుకు తగిన ఎత్తు లేరు.',
    terminal_heat_risk: 'ఇలాంటి {n} % చలికాలాల్లో ఫిబ్రవరి–మార్చి వేడి వల్ల గోధుమ, శనగ పంట దెబ్బతింది.',
    'ndvi_stress.neg': 'ఉపగ్రహ చిత్రాల్లో ప్రస్తుతం పంటలు సాధారణం కంటే తక్కువ పచ్చగా కనిపిస్తున్నాయి.',
    'ndvi_stress.norm': 'ఉపగ్రహ చిత్రాల్లో ప్రస్తుతం పంటలు దాదాపు సాధారణంగా కనిపిస్తున్నాయి.',
    'ndvi_stress.pos': 'ఉపగ్రహ చిత్రాల్లో ప్రస్తుతం పంటలు సాధారణం కంటే ఎక్కువ పచ్చగా కనిపిస్తున్నాయి.',
    dry_antecedent_season: 'గత రుతుపవనాల్లో ({year}) సాధారణం కంటే {n} % తక్కువ వర్షం పడింది, అందుకే నేలలో తేమ తక్కువ.',
    top_crop_share: '{n} % సాగు ఒకే పంట ({crop}), కాబట్టి ఒక చెడ్డ సీజన్ తీవ్రంగా దెబ్బతీస్తుంది.',
    weak_kharif_carryover: 'గత ఖరీఫ్ ({year}) దిగుబడి సాధారణం కంటే {n} % తక్కువ, అందుకే రబీలో విత్తనాలు, ఆదాయం తక్కువ.',
    small_marginal_share: '{n} % పొలాలు 2 హెక్టార్ల కంటే చిన్నవి, కాబట్టి కుటుంబాలకు ఆసరా తక్కువ.',
    yield_cv: 'దిగుబడి ప్రతి సంవత్సరం సుమారు {n} % పైకీ కిందికీ మారుతుంది.',
    low_self_sufficiency: 'జిల్లాలో ప్రజల అవసరంలో సుమారు {n} % ధాన్యం మాత్రమే పండుతుంది.',
  },
}
/** Local-language sentence for a driver, or null when only English exists. */
export function driverLocal(lang: Lang, key: string, params: { n?: number; crop?: string; year?: string }): string | null {
  const tpl = DRV[lang]?.[key]
  if (!tpl) return null
  return tpl.replace('{n}', String(params.n ?? '')).replace('{crop}', params.crop ?? '').replace('{year}', params.year ?? '').replace(/(\d) %/g, '$1\u00a0%')
}
