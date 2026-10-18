// Addendum I strings (season outlook sentences, "Rain and heat" card, Gemini caption). Merged into the maps in i18n.ts.
// hi / mr / te are machine-drafted and have not been reviewed by native speakers.
type Dict = Record<string, string>
const fill = (pre: string, o: { vl: string; l: string; p: string }): Dict => ({ [`${pre}.vl`]: o.vl, [`${pre}.l`]: o.l, [`${pre}.p`]: o.p })

export const EXTRA: Record<'en' | 'hi' | 'mr' | 'te', Dict> = {
  en: {
    'outlook.neutral': 'A near-normal season is expected',
    ...fill('outlook.elnino.rabi', { vl: 'A dry, warm winter is very likely', l: 'A dry, warm winter is likely', p: 'A dry, warm winter is possible' }),
    ...fill('outlook.elnino.kharif', { vl: 'A weak monsoon is very likely', l: 'A weak monsoon is likely', p: 'A weak monsoon is possible' }),
    ...fill('outlook.lanina.kharif', { vl: 'Heavy rain and flooding are very likely', l: 'Heavy rain and flooding are likely', p: 'Heavy rain and flooding are possible' }),
    ...fill('outlook.lanina.rabi', { vl: 'A cool, wet winter is very likely', l: 'A cool, wet winter is likely', p: 'A cool, wet winter is possible' }),
    'rh.title': 'Rain and heat this season',
    'rh.rain.less': 'About {n} % less rain than normal ({win})', 'rh.rain.more': 'About {n} % more rain than normal ({win})', 'rh.rain.norm': 'Rain close to normal ({win})',
    'rh.deficit': '{k} in 10 chance of a serious rain shortage', 'rh.deficit.low': 'A serious rain shortage is unlikely',
    'rh.heat.hot': 'About {n} °C hotter than normal ({win})', 'rh.heat.cool': 'About {n} °C cooler than normal ({win})', 'rh.heat.norm': 'Temperatures close to normal ({win})',
    'rh.onset.late': 'Monsoon may arrive about {n} days late', 'rh.onset.ok': 'Monsoon expected on time',
    'why.outlook': 'Season outlook', 'econ.label': 'Rough costs and returns', 'brand.gemini': 'Powered by Gemini',
  },
  hi: {
    'outlook.neutral': 'मौसम लगभग सामान्य रहने की उम्मीद है',
    ...fill('outlook.elnino.rabi', { vl: 'सर्दी सूखी और गर्म रहने की बहुत ज़्यादा संभावना है', l: 'सर्दी सूखी और गर्म रहने की ज़्यादा संभावना है', p: 'सर्दी सूखी और गर्म रहने की संभावना है' }),
    ...fill('outlook.elnino.kharif', { vl: 'इस बार मानसून कमज़ोर रहने की बहुत ज़्यादा संभावना है', l: 'इस बार मानसून कमज़ोर रहने की ज़्यादा संभावना है', p: 'इस बार मानसून कमज़ोर रहने की संभावना है' }),
    ...fill('outlook.lanina.kharif', { vl: 'भारी बारिश और बाढ़ की बहुत ज़्यादा संभावना है', l: 'भारी बारिश और बाढ़ की ज़्यादा संभावना है', p: 'भारी बारिश और बाढ़ की संभावना है' }),
    ...fill('outlook.lanina.rabi', { vl: 'सर्दी ठंडी और नम रहने की बहुत ज़्यादा संभावना है', l: 'सर्दी ठंडी और नम रहने की ज़्यादा संभावना है', p: 'सर्दी ठंडी और नम रहने की संभावना है' }),
    'rh.title': 'इस मौसम में बारिश और गर्मी',
    'rh.rain.less': 'सामान्य से लगभग {n} % कम बारिश ({win})', 'rh.rain.more': 'सामान्य से लगभग {n} % ज़्यादा बारिश ({win})', 'rh.rain.norm': 'बारिश लगभग सामान्य ({win})',
    'rh.deficit': 'बारिश की गंभीर कमी की संभावना: 10 में से {k}', 'rh.deficit.low': 'बारिश की गंभीर कमी की संभावना कम है',
    'rh.heat.hot': 'सामान्य से लगभग {n} °C ज़्यादा गर्मी ({win})', 'rh.heat.cool': 'सामान्य से लगभग {n} °C ठंडा ({win})', 'rh.heat.norm': 'तापमान लगभग सामान्य ({win})',
    'rh.onset.late': 'मानसून लगभग {n} दिन देर से आ सकता है', 'rh.onset.ok': 'मानसून समय पर आने की उम्मीद है',
    'why.outlook': 'इस मौसम का अनुमान', 'econ.label': 'मोटा लागत और आमदनी अनुमान', 'brand.gemini': 'Gemini द्वारा संचालित',
  },
  mr: {
    'outlook.neutral': 'हंगाम साधारण सामान्य राहण्याची अपेक्षा आहे',
    ...fill('outlook.elnino.rabi', { vl: 'हिवाळा कोरडा आणि उबदार राहण्याची खूप जास्त शक्यता आहे', l: 'हिवाळा कोरडा आणि उबदार राहण्याची जास्त शक्यता आहे', p: 'हिवाळा कोरडा आणि उबदार राहण्याची शक्यता आहे' }),
    ...fill('outlook.elnino.kharif', { vl: 'यंदा मान्सून कमकुवत राहण्याची खूप जास्त शक्यता आहे', l: 'यंदा मान्सून कमकुवत राहण्याची जास्त शक्यता आहे', p: 'यंदा मान्सून कमकुवत राहण्याची शक्यता आहे' }),
    ...fill('outlook.lanina.kharif', { vl: 'जोरदार पाऊस आणि पुराची खूप जास्त शक्यता आहे', l: 'जोरदार पाऊस आणि पुराची जास्त शक्यता आहे', p: 'जोरदार पाऊस आणि पुराची शक्यता आहे' }),
    ...fill('outlook.lanina.rabi', { vl: 'हिवाळा थंड आणि ओलसर राहण्याची खूप जास्त शक्यता आहे', l: 'हिवाळा थंड आणि ओलसर राहण्याची जास्त शक्यता आहे', p: 'हिवाळा थंड आणि ओलसर राहण्याची शक्यता आहे' }),
    'rh.title': 'या हंगामातील पाऊस आणि उष्णता',
    'rh.rain.less': 'सामान्यपेक्षा सुमारे {n} % कमी पाऊस ({win})', 'rh.rain.more': 'सामान्यपेक्षा सुमारे {n} % जास्त पाऊस ({win})', 'rh.rain.norm': 'पाऊस जवळपास सामान्य ({win})',
    'rh.deficit': 'पावसाची गंभीर तूट पडण्याची शक्यता: 10 पैकी {k}', 'rh.deficit.low': 'पावसाची गंभीर तूट पडण्याची शक्यता कमी आहे',
    'rh.heat.hot': 'सामान्यपेक्षा सुमारे {n} °C जास्त उष्णता ({win})', 'rh.heat.cool': 'सामान्यपेक्षा सुमारे {n} °C थंड ({win})', 'rh.heat.norm': 'तापमान जवळपास सामान्य ({win})',
    'rh.onset.late': 'मान्सून सुमारे {n} दिवस उशिरा येऊ शकतो', 'rh.onset.ok': 'मान्सून वेळेवर येण्याची अपेक्षा आहे',
    'why.outlook': 'या हंगामाचा अंदाज', 'econ.label': 'ढोबळ खर्च आणि उत्पन्न', 'brand.gemini': 'Gemini द्वारे संचालित',
  },
  te: {
    'outlook.neutral': 'సీజన్ దాదాపు సాధారణంగా ఉండే అవకాశం ఉంది',
    ...fill('outlook.elnino.rabi', { vl: 'చలికాలం పొడిగా, వెచ్చగా ఉండే అవకాశం చాలా ఎక్కువగా ఉంది', l: 'చలికాలం పొడిగా, వెచ్చగా ఉండే అవకాశం ఎక్కువగా ఉంది', p: 'చలికాలం పొడిగా, వెచ్చగా ఉండే అవకాశం ఉంది' }),
    ...fill('outlook.elnino.kharif', { vl: 'ఈసారి రుతుపవనాలు బలహీనంగా ఉండే అవకాశం చాలా ఎక్కువగా ఉంది', l: 'ఈసారి రుతుపవనాలు బలహీనంగా ఉండే అవకాశం ఎక్కువగా ఉంది', p: 'ఈసారి రుతుపవనాలు బలహీనంగా ఉండే అవకాశం ఉంది' }),
    ...fill('outlook.lanina.kharif', { vl: 'భారీ వర్షాలు, వరదలు వచ్చే అవకాశం చాలా ఎక్కువగా ఉంది', l: 'భారీ వర్షాలు, వరదలు వచ్చే అవకాశం ఎక్కువగా ఉంది', p: 'భారీ వర్షాలు, వరదలు వచ్చే అవకాశం ఉంది' }),
    ...fill('outlook.lanina.rabi', { vl: 'చలికాలం చల్లగా, తడిగా ఉండే అవకాశం చాలా ఎక్కువగా ఉంది', l: 'చలికాలం చల్లగా, తడిగా ఉండే అవకాశం ఎక్కువగా ఉంది', p: 'చలికాలం చల్లగా, తడిగా ఉండే అవకాశం ఉంది' }),
    'rh.title': 'ఈ సీజన్‌లో వర్షం మరియు వేడి',
    'rh.rain.less': 'సాధారణం కంటే సుమారు {n} % తక్కువ వర్షం ({win})', 'rh.rain.more': 'సాధారణం కంటే సుమారు {n} % ఎక్కువ వర్షం ({win})', 'rh.rain.norm': 'వర్షం దాదాపు సాధారణం ({win})',
    'rh.deficit': 'తీవ్రమైన వర్షాభావం ఉండే అవకాశం: 10 లో {k}', 'rh.deficit.low': 'తీవ్రమైన వర్షాభావం ఉండే అవకాశం తక్కువ',
    'rh.heat.hot': 'సాధారణం కంటే సుమారు {n} °C ఎక్కువ వేడి ({win})', 'rh.heat.cool': 'సాధారణం కంటే సుమారు {n} °C చల్లగా ({win})', 'rh.heat.norm': 'ఉష్ణోగ్రతలు దాదాపు సాధారణం ({win})',
    'rh.onset.late': 'రుతుపవనాలు సుమారు {n} రోజులు ఆలస్యంగా రావచ్చు', 'rh.onset.ok': 'రుతుపవనాలు సమయానికి వస్తాయని అంచనా',
    'why.outlook': 'ఈ సీజన్ అంచనా', 'econ.label': 'సుమారు ఖర్చు, ఆదాయం', 'brand.gemini': 'Gemini ఆధారితం',
  },
}

const MONTHS: Record<'hi' | 'mr' | 'te', string[]> = {
  hi: ['जन', 'फ़र', 'मार्च', 'अप्रैल', 'मई', 'जून', 'जुल', 'अग', 'सित', 'अक्टू', 'नव', 'दिस'],
  mr: ['जाने', 'फेब्रु', 'मार्च', 'एप्रि', 'मे', 'जून', 'जुलै', 'ऑग', 'सप्टें', 'ऑक्टो', 'नोव्हें', 'डिसें'],
  te: ['జన', 'ఫిబ్ర', 'మార్చి', 'ఏప్రి', 'మే', 'జూన్', 'జులై', 'ఆగ', 'సెప్టెం', 'అక్టో', 'నవం', 'డిసెం'],
}
const EN_M = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
/** "Jun–Sep" -> local month names for hi / mr / te; unchanged otherwise. */
export function localWindow(lang: string, win: string): string {
  const m = MONTHS[lang as 'hi' | 'mr' | 'te']
  return m ? win.replace(/\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b/g, (x) => m[EN_M.indexOf(x)]) : win
}
